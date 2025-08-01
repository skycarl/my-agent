"""
Email parser for extracting structured data from raw email messages.
"""

from datetime import datetime
from typing import Optional
from loguru import logger
import mailparser

from .models import EmailAlert


class EmailParser:
    """Parser for converting raw email data to structured EmailAlert objects."""

    @staticmethod
    def parse_raw_message(uid: str, raw_message: bytes) -> Optional[EmailAlert]:
        """
        Parse a raw email message into an EmailAlert object.

        Args:
            uid: Unique identifier from email server
            raw_message: Raw email message bytes

        Returns:
            EmailAlert object or None if parsing fails
        """
        try:
            # Use mailparser for robust email parsing
            mail = mailparser.parse_from_bytes(raw_message)

            # Extract basic fields
            subject = str(mail.subject) if mail.subject else "No Subject"

            # Handle sender - mail.from_ can be a list of tuples (name, email) or strings
            sender = "Unknown Sender"
            if mail.from_:
                first_sender = mail.from_[0]
                if isinstance(first_sender, tuple) and len(first_sender) >= 2:
                    # Format: ('Display Name', 'email@domain.com')
                    sender = first_sender[1]  # Use the email address
                elif isinstance(first_sender, str):
                    # Format: 'email@domain.com'
                    sender = first_sender
                else:
                    # Fallback: convert whatever we have to string
                    sender = str(first_sender)

            # Get the plain text body
            body = ""
            if mail.text_plain:
                body = "\n".join(mail.text_plain)
            elif mail.text_html:
                # If no plain text, use HTML (could strip HTML tags here if needed)
                body = "\n".join(mail.text_html)
            else:
                body = "No body content"

            # Parse date
            date = None
            if mail.date:
                try:
                    # mailparser returns datetime objects
                    date = mail.date
                except Exception as e:
                    logger.warning(f"Failed to parse email date: {e}")
                    date = datetime.now()
            else:
                date = datetime.now()

            # Extract raw headers for additional context
            raw_headers = {}
            if hasattr(mail, "headers") and mail.headers:
                raw_headers = dict(mail.headers)

            alert = EmailAlert(
                uid=uid,
                subject=subject,
                body=body.strip(),
                sender=sender,
                date=date,
                raw_headers=raw_headers,
            )

            logger.debug(f"Successfully parsed email {uid} from {sender}")
            return alert

        except Exception as e:
            logger.error(f"Failed to parse email message {uid}: {e}")
            return None

    @staticmethod
    def extract_commute_info(alert: EmailAlert) -> dict:
        """
        Extract commute-specific information from an email alert.
        This is a placeholder for commute-specific parsing logic.

        Args:
            alert: EmailAlert object

        Returns:
            Dictionary with extracted commute information
        """
        # This is where you would add domain-specific parsing
        # For now, return basic structure
        return {
            "alert_type": "commute",
            "raw_subject": alert.subject,
            "raw_body": alert.body,
            "timestamp": alert.date.isoformat(),
            "source": alert.sender,
        }
