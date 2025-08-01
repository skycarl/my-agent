"""
Unit tests for email_sink.parser module.
"""

from unittest.mock import Mock, patch
from datetime import datetime

from email_sink.parser import EmailParser
from email_sink.models import EmailAlert


class TestEmailParser:
    """Test EmailParser class."""

    def test_parse_raw_message_success(self):
        """Test successfully parsing a raw email message."""
        # Create a mock mailparser object
        mock_mail = Mock()
        mock_mail.subject = "Test Subject"
        mock_mail.from_ = ["test@example.com"]
        mock_mail.text_plain = ["This is the email body"]
        mock_mail.text_html = None
        mock_mail.date = datetime(2025, 1, 15, 10, 30, 0)
        mock_mail.headers = {"Message-ID": "123", "Content-Type": "text/plain"}

        with patch("email_sink.parser.mailparser") as mock_mailparser:
            mock_mailparser.parse_from_bytes.return_value = mock_mail

            raw_message = b"Raw email content"
            alert = EmailParser.parse_raw_message("12345", raw_message)

        assert alert is not None
        assert alert.uid == "12345"
        assert alert.subject == "Test Subject"
        assert alert.body == "This is the email body"
        assert alert.sender == "test@example.com"
        assert alert.date == datetime(2025, 1, 15, 10, 30, 0)
        assert alert.raw_headers == {"Message-ID": "123", "Content-Type": "text/plain"}

    def test_parse_raw_message_with_html_only(self):
        """Test parsing email with only HTML content."""
        mock_mail = Mock()
        mock_mail.subject = "HTML Subject"
        mock_mail.from_ = ["html@example.com"]
        mock_mail.text_plain = None
        mock_mail.text_html = ["<p>HTML content</p>"]
        mock_mail.date = datetime(2025, 1, 15, 10, 30, 0)
        mock_mail.headers = {}

        with patch("email_sink.parser.mailparser") as mock_mailparser:
            mock_mailparser.parse_from_bytes.return_value = mock_mail

            alert = EmailParser.parse_raw_message("12345", b"Raw email")

        assert alert is not None
        assert alert.body == "<p>HTML content</p>"

    def test_parse_raw_message_no_body(self):
        """Test parsing email with no body content."""
        mock_mail = Mock()
        mock_mail.subject = "No Body Subject"
        mock_mail.from_ = ["nobody@example.com"]
        mock_mail.text_plain = None
        mock_mail.text_html = None
        mock_mail.date = datetime(2025, 1, 15, 10, 30, 0)
        mock_mail.headers = {}

        with patch("email_sink.parser.mailparser") as mock_mailparser:
            mock_mailparser.parse_from_bytes.return_value = mock_mail

            alert = EmailParser.parse_raw_message("12345", b"Raw email")

        assert alert is not None
        assert alert.body == "No body content"

    def test_parse_raw_message_no_subject(self):
        """Test parsing email with no subject."""
        mock_mail = Mock()
        mock_mail.subject = None
        mock_mail.from_ = ["test@example.com"]
        mock_mail.text_plain = ["Body content"]
        mock_mail.text_html = None
        mock_mail.date = datetime(2025, 1, 15, 10, 30, 0)
        mock_mail.headers = {}

        with patch("email_sink.parser.mailparser") as mock_mailparser:
            mock_mailparser.parse_from_bytes.return_value = mock_mail

            alert = EmailParser.parse_raw_message("12345", b"Raw email")

        assert alert is not None
        assert alert.subject == "No Subject"

    def test_parse_raw_message_no_sender(self):
        """Test parsing email with no sender."""
        mock_mail = Mock()
        mock_mail.subject = "Test Subject"
        mock_mail.from_ = None
        mock_mail.text_plain = ["Body content"]
        mock_mail.text_html = None
        mock_mail.date = datetime(2025, 1, 15, 10, 30, 0)
        mock_mail.headers = {}

        with patch("email_sink.parser.mailparser") as mock_mailparser:
            mock_mailparser.parse_from_bytes.return_value = mock_mail

            alert = EmailParser.parse_raw_message("12345", b"Raw email")

        assert alert is not None
        assert alert.sender == "Unknown Sender"

    def test_parse_raw_message_sender_tuple(self):
        """Test parsing email with sender as tuple (display name, email)."""
        mock_mail = Mock()
        mock_mail.subject = "Test Subject"
        mock_mail.from_ = [("Sound Transit", "soundtransit@public.govdelivery.com")]
        mock_mail.text_plain = ["Body content"]
        mock_mail.text_html = None
        mock_mail.date = datetime(2025, 1, 15, 10, 30, 0)
        mock_mail.headers = {}

        with patch("email_sink.parser.mailparser") as mock_mailparser:
            mock_mailparser.parse_from_bytes.return_value = mock_mail

            alert = EmailParser.parse_raw_message("12345", b"Raw email")

        assert alert is not None
        assert alert.sender == "soundtransit@public.govdelivery.com"

    def test_parse_raw_message_sender_string(self):
        """Test parsing email with sender as string."""
        mock_mail = Mock()
        mock_mail.subject = "Test Subject"
        mock_mail.from_ = ["test@example.com"]
        mock_mail.text_plain = ["Body content"]
        mock_mail.text_html = None
        mock_mail.date = datetime(2025, 1, 15, 10, 30, 0)
        mock_mail.headers = {}

        with patch("email_sink.parser.mailparser") as mock_mailparser:
            mock_mailparser.parse_from_bytes.return_value = mock_mail

            alert = EmailParser.parse_raw_message("12345", b"Raw email")

        assert alert is not None
        assert alert.sender == "test@example.com"

    def test_parse_raw_message_sender_fallback(self):
        """Test parsing email with sender as unexpected format."""
        mock_mail = Mock()
        mock_mail.subject = "Test Subject"
        mock_mail.from_ = [123]  # Unexpected format
        mock_mail.text_plain = ["Body content"]
        mock_mail.text_html = None
        mock_mail.date = datetime(2025, 1, 15, 10, 30, 0)
        mock_mail.headers = {}

        with patch("email_sink.parser.mailparser") as mock_mailparser:
            mock_mailparser.parse_from_bytes.return_value = mock_mail

            alert = EmailParser.parse_raw_message("12345", b"Raw email")

        assert alert is not None
        assert alert.sender == "123"

    def test_parse_raw_message_no_date(self):
        """Test parsing email with no date."""
        mock_mail = Mock()
        mock_mail.subject = "Test Subject"
        mock_mail.from_ = ["test@example.com"]
        mock_mail.text_plain = ["Body content"]
        mock_mail.text_html = None
        mock_mail.date = None
        mock_mail.headers = {}

        with patch("email_sink.parser.mailparser") as mock_mailparser:
            mock_mailparser.parse_from_bytes.return_value = mock_mail

            with patch("email_sink.parser.datetime") as mock_datetime:
                mock_now = datetime(2025, 1, 15, 12, 0, 0)
                mock_datetime.now.return_value = mock_now

                alert = EmailParser.parse_raw_message("12345", b"Raw email")

        assert alert is not None
        assert alert.date == mock_now

    def test_parse_raw_message_parsing_error(self):
        """Test handling of parsing errors."""
        with patch("email_sink.parser.mailparser") as mock_mailparser:
            mock_mailparser.parse_from_bytes.side_effect = Exception("Parse error")

            alert = EmailParser.parse_raw_message("12345", b"Invalid email")

        assert alert is None

    def test_extract_commute_info(self):
        """Test extracting commute-specific information."""
        date = datetime(2025, 1, 15, 10, 30, 0)
        alert = EmailAlert(
            uid="12345",
            subject="Traffic Alert",
            body="Heavy traffic on I-95",
            sender="alerts@traffic.gov",
            date=date,
        )

        commute_info = EmailParser.extract_commute_info(alert)

        assert commute_info["alert_type"] == "commute"
        assert commute_info["raw_subject"] == "Traffic Alert"
        assert commute_info["raw_body"] == "Heavy traffic on I-95"
        assert commute_info["timestamp"] == date.isoformat()
        assert commute_info["source"] == "alerts@traffic.gov"

    def test_parse_with_multiple_plain_text_parts(self):
        """Test parsing email with multiple plain text parts."""
        mock_mail = Mock()
        mock_mail.subject = "Multi-part Email"
        mock_mail.from_ = ["test@example.com"]
        mock_mail.text_plain = ["Part 1", "Part 2", "Part 3"]
        mock_mail.text_html = None
        mock_mail.date = datetime(2025, 1, 15, 10, 30, 0)
        mock_mail.headers = {}

        with patch("email_sink.parser.mailparser") as mock_mailparser:
            mock_mailparser.parse_from_bytes.return_value = mock_mail

            alert = EmailParser.parse_raw_message("12345", b"Raw email")

        assert alert is not None
        assert alert.body == "Part 1\nPart 2\nPart 3"
