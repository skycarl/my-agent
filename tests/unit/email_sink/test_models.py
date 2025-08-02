"""
Unit tests for email_sink.models module.
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

from email_sink.models import EmailAlert, EmailSinkConfig, AlertRequest


class TestEmailAlert:
    """Test EmailAlert model."""

    def test_email_alert_creation(self):
        """Test creating a valid EmailAlert."""
        date = datetime.now()
        alert = EmailAlert(
            uid="12345",
            subject="Test Subject",
            body="Test body content",
            sender="test@example.com",
            date=date,
        )

        assert alert.uid == "12345"
        assert alert.subject == "Test Subject"
        assert alert.body == "Test body content"
        assert alert.sender == "test@example.com"
        assert alert.date == date
        assert alert.raw_headers == {}

    def test_email_alert_with_headers(self):
        """Test EmailAlert with raw headers."""
        date = datetime.now()
        headers = {"Message-ID": "123", "Content-Type": "text/plain"}

        alert = EmailAlert(
            uid="12345",
            subject="Test Subject",
            body="Test body",
            sender="test@example.com",
            date=date,
            raw_headers=headers,
        )

        assert alert.raw_headers == headers

    def test_email_alert_validation_errors(self):
        """Test EmailAlert validation errors."""
        # Missing required fields
        with pytest.raises(ValidationError):
            EmailAlert(uid="12345")  # Missing other required fields

        # Invalid date type - use type: ignore to bypass type checker for test
        with pytest.raises(ValidationError):
            EmailAlert(
                uid="12345",
                subject="Test",
                body="Test",
                sender="test@example.com",
                date="invalid-date",
            )


class TestEmailSinkConfig:
    """Test EmailSinkConfig model."""

    def test_email_sink_config_creation(self):
        """Test creating a valid EmailSinkConfig."""
        config = EmailSinkConfig(
            sender_pattern="alerts@example.com",
            endpoint="/commute_alert",
            description="Test configuration",
        )

        assert config.sender_pattern == "alerts@example.com"
        assert config.endpoint == "/commute_alert"
        assert config.description == "Test configuration"

    def test_email_sink_config_validation(self):
        """Test EmailSinkConfig validation."""
        # Missing required fields
        with pytest.raises(ValidationError):
            EmailSinkConfig(
                sender_pattern="test@example.com"
            )  # Missing endpoint and description

        # Missing description
        with pytest.raises(ValidationError):
            EmailSinkConfig(
                sender_pattern="test@example.com",
                endpoint="/test",
                # Missing description
            )


class TestAlertRequest:
    """Test AlertRequest model."""

    def test_alert_request_creation(self):
        """Test creating a valid AlertRequest."""
        date = datetime.now()
        request = AlertRequest(
            uid="12345",
            subject="Test Alert",
            body="Alert body",
            sender="alerts@example.com",
            date=date,
        )

        assert request.uid == "12345"
        assert request.subject == "Test Alert"
        assert request.body == "Alert body"
        assert request.sender == "alerts@example.com"
        assert request.date == date
        assert request.alert_type == "email"  # Default value

    def test_alert_request_custom_type(self):
        """Test AlertRequest with custom alert type."""
        date = datetime.now()
        request = AlertRequest(
            uid="12345",
            subject="Test Alert",
            body="Alert body",
            sender="alerts@example.com",
            date=date,
            alert_type="custom",
        )

        assert request.alert_type == "custom"

    def test_alert_request_validation_errors(self):
        """Test AlertRequest validation errors."""
        # Missing required fields
        with pytest.raises(ValidationError):
            AlertRequest(uid="12345")  # Missing other required fields

        # Invalid date - use type: ignore to bypass type checker for test
        with pytest.raises(ValidationError):
            AlertRequest(
                uid="12345",
                subject="Test",
                body="Test",
                sender="test@example.com",
                date="invalid",
            )
