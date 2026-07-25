"""
Email client for IMAP operations using imapclient.
"""

import ssl
from typing import List, Tuple
from imapclient import IMAPClient
from loguru import logger

from app.core.settings import config


class EmailClient:
    """Client for connecting to and monitoring email via IMAP."""

    def __init__(self):
        self.server = config.email_imap_server
        self.email = config.email_address
        self.password = config.email_password
        self.client = None

        if not self.email or not self.password:
            raise ValueError("Email address and password must be configured")

    def connect(self) -> None:
        """Connect to the IMAP server and login."""
        try:
            # Create SSL context with proper verification
            ssl_context = ssl.create_default_context()
            self.client = IMAPClient(self.server, ssl=True, ssl_context=ssl_context)
            self.client.login(self.email, self.password)

        except Exception as e:
            logger.error(f"Failed to connect to IMAP server: {e}")
            # If login failed after the socket was opened, close it — the
            # context manager's __exit__ never runs when __enter__ raises.
            if self.client:
                try:
                    self.client.shutdown()
                except Exception:
                    pass
                self.client = None
            raise

    def disconnect(self) -> None:
        """Disconnect from the IMAP server."""
        if self.client:
            try:
                self.client.logout()
            except Exception as e:
                logger.warning(f"Error during IMAP disconnect: {e}")
            finally:
                self.client = None

    def get_unread_messages_from_sender(
        self, sender_pattern: str
    ) -> List[Tuple[str, bytes]]:
        """
        Get unread messages from a specific sender.

        Args:
            sender_pattern: Email address or domain pattern to match

        Returns:
            List of tuples: ("{uidvalidity}-{message_id}", raw_message_data).
            UIDVALIDITY is included so dedup keys stay unique if the server
            ever resets its UID sequence.
        """
        if not self.client:
            raise RuntimeError("Not connected to IMAP server")

        try:
            # Select the inbox and capture UIDVALIDITY for dedup keys
            select_info = self.client.select_folder("INBOX")
            uidvalidity = select_info.get(b"UIDVALIDITY", 0)

            # Search for unread messages from the specified sender
            search_criteria = ["UNSEEN", "FROM", sender_pattern]
            message_ids = self.client.search(search_criteria)

            if not message_ids:
                return []

            logger.info(
                f"Found {len(message_ids)} unread messages from {sender_pattern}"
            )

            # Fetch the messages
            messages = []
            for msg_id in message_ids:
                try:
                    # Fetch with BODY.PEEK[] so the message is not implicitly
                    # marked \Seen; we only mark as read after a successful POST.
                    # The server responds under the BODY[] key.
                    response = self.client.fetch([msg_id], ["BODY.PEEK[]"])
                    raw_data = response[msg_id][b"BODY[]"]
                    messages.append((f"{uidvalidity}-{msg_id}", raw_data))

                except Exception as e:
                    logger.error(f"Failed to fetch message {msg_id}: {e}")
                    continue

            return messages

        except Exception as e:
            logger.error(f"Error retrieving messages from {sender_pattern}: {e}")
            raise

    def mark_as_read(self, uid: str) -> bool:
        """Mark a message as read. Returns True on success."""
        if not self.client:
            raise RuntimeError("Not connected to IMAP server")

        try:
            # uid is "{uidvalidity}-{message_id}"; the server only needs the
            # message id
            msg_id = int(uid.rsplit("-", 1)[-1])
            self.client.add_flags([msg_id], [b"\\Seen"])
            logger.debug(f"Marked message {uid} as read")
            return True
        except Exception as e:
            logger.error(f"Failed to mark message {uid} as read: {e}")
            return False

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
