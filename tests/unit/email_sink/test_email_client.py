"""
Unit tests for email_sink.email_client module.
"""

import pytest
from unittest.mock import Mock, patch

from email_sink.email_client import EmailClient


@pytest.fixture
def email_client():
    """EmailClient with a mocked IMAPClient connection."""
    with patch("email_sink.email_client.config") as mock_config:
        mock_config.email_imap_server = "imap.example.com"
        mock_config.email_address = "test@example.com"
        mock_config.email_password = "password"

        client = EmailClient()
        client.client = Mock()
        yield client


class TestGetUnreadMessages:
    """Test get_unread_messages_from_sender."""

    def test_fetches_with_body_peek(self, email_client):
        """Test that fetch uses BODY.PEEK[] so messages are not marked seen."""
        email_client.client.select_folder.return_value = {b"UIDVALIDITY": 42}
        email_client.client.search.return_value = [123]
        email_client.client.fetch.return_value = {123: {b"BODY[]": b"raw_data"}}

        messages = email_client.get_unread_messages_from_sender("alerts@")

        email_client.client.fetch.assert_called_once_with([123], ["BODY.PEEK[]"])
        assert messages == [("42-123", b"raw_data")]

    def test_uid_includes_uidvalidity(self, email_client):
        """Test that returned uids are prefixed with UIDVALIDITY."""
        email_client.client.select_folder.return_value = {b"UIDVALIDITY": 7}
        email_client.client.search.return_value = [1, 2]
        email_client.client.fetch.side_effect = [
            {1: {b"BODY[]": b"msg1"}},
            {2: {b"BODY[]": b"msg2"}},
        ]

        messages = email_client.get_unread_messages_from_sender("alerts@")

        assert [uid for uid, _ in messages] == ["7-1", "7-2"]

    def test_no_messages(self, email_client):
        """Test empty search result returns empty list."""
        email_client.client.select_folder.return_value = {b"UIDVALIDITY": 42}
        email_client.client.search.return_value = []

        assert email_client.get_unread_messages_from_sender("alerts@") == []


class TestMarkAsRead:
    """Test mark_as_read."""

    def test_composite_uid(self, email_client):
        """Test that the uidvalidity prefix is stripped before adding flags."""
        result = email_client.mark_as_read("42-123")

        assert result is True
        email_client.client.add_flags.assert_called_once_with([123], [b"\\Seen"])

    def test_failure_returns_false(self, email_client):
        """Test that an IMAP error returns False."""
        email_client.client.add_flags.side_effect = Exception("IMAP error")

        assert email_client.mark_as_read("42-123") is False
