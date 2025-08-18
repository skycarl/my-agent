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
            List of tuples: (uid, raw_message_data)
        """
        if not self.client:
            raise RuntimeError("Not connected to IMAP server")

        try:
            # Select the inbox
            self.client.select_folder("INBOX")

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
                    # Fetch the raw message data
                    response = self.client.fetch([msg_id], ["RFC822"])
                    raw_data = response[msg_id][b"RFC822"]
                    messages.append((str(msg_id), raw_data))

                except Exception as e:
                    logger.error(f"Failed to fetch message {msg_id}: {e}")
                    continue

            return messages

        except Exception as e:
            logger.error(f"Error retrieving messages from {sender_pattern}: {e}")
            raise

    def mark_as_read(self, uid: str) -> None:
        """Mark a message as read."""
        if not self.client:
            raise RuntimeError("Not connected to IMAP server")

        try:
            self.client.add_flags([int(uid)], [b"\\Seen"])
            logger.debug(f"Marked message {uid} as read")
        except Exception as e:
            logger.error(f"Failed to mark message {uid} as read: {e}")

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
