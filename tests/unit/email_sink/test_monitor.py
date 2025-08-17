"""
Unit tests for email_sink.monitor module.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from email_sink.monitor import EmailMonitorService, get_monitor_service
from email_sink.models import EmailAlert, EmailSinkConfig
from app.core.timezone_utils import now_local


class TestEmailMonitorService:
    """Test EmailMonitorService class."""

    def test_init(self):
        """Test EmailMonitorService initialization."""
        with patch.object(EmailMonitorService, "_load_email_configs"):
            service = EmailMonitorService()
            assert service.scheduler is not None
            assert service.running is False
            assert isinstance(service.email_configs, list)

    def test_load_email_configs_single_pattern(self):
        """Test loading email configurations with single pattern."""
        with patch("email_sink.monitor.config") as mock_config:
            mock_config.email_sender_patterns = "alerts@"

            service = EmailMonitorService()

            assert len(service.email_configs) == 1
            config = service.email_configs[0]
            assert config.sender_pattern == "alerts@"
            assert config.endpoint == "/process_alert"
            assert config.description == "Email alerts from pattern: alerts@"

    def test_load_email_configs_multiple_patterns(self):
        """Test loading email configurations with multiple patterns."""
        with patch("email_sink.monitor.config") as mock_config:
            mock_config.email_sender_patterns = (
                "alerts@, @transit.gov, notifications@weather.gov"
            )

            service = EmailMonitorService()

            assert len(service.email_configs) == 3

            # Check first pattern
            config1 = service.email_configs[0]
            assert config1.sender_pattern == "alerts@"
            assert config1.endpoint == "/process_alert"
            assert config1.description == "Email alerts from pattern: alerts@"

            # Check second pattern
            config2 = service.email_configs[1]
            assert config2.sender_pattern == "@transit.gov"
            assert config2.endpoint == "/process_alert"
            assert config2.description == "Email alerts from pattern: @transit.gov"

            # Check third pattern
            config3 = service.email_configs[2]
            assert config3.sender_pattern == "notifications@weather.gov"
            assert config3.endpoint == "/process_alert"
            assert (
                config3.description
                == "Email alerts from pattern: notifications@weather.gov"
            )

    def test_load_email_configs_empty_patterns(self):
        """Test loading email configurations with empty patterns."""
        with patch("email_sink.monitor.config") as mock_config:
            mock_config.email_sender_patterns = ""

            service = EmailMonitorService()

            assert len(service.email_configs) == 0

    def test_load_email_configs_whitespace_only(self):
        """Test loading email configurations with whitespace only."""
        with patch("email_sink.monitor.config") as mock_config:
            mock_config.email_sender_patterns = "   "

            service = EmailMonitorService()

            assert len(service.email_configs) == 0

    def test_load_email_configs_invalid_commas(self):
        """Test loading email configurations with extra commas and whitespace."""
        with patch("email_sink.monitor.config") as mock_config:
            mock_config.email_sender_patterns = (
                "alerts@, , @domain.com,  ,notifications@"
            )

            service = EmailMonitorService()

            assert len(service.email_configs) == 3
            assert service.email_configs[0].sender_pattern == "alerts@"
            assert service.email_configs[1].sender_pattern == "@domain.com"
            assert service.email_configs[2].sender_pattern == "notifications@"

    @pytest.mark.asyncio
    async def test_check_email_for_alerts_disabled(self):
        """Test email check when service is disabled."""
        with patch("email_sink.monitor.config") as mock_config:
            mock_config.email_sink_enabled = False

            service = EmailMonitorService()
            await service.check_email_for_alerts()

            # Should return early without error

    @pytest.mark.asyncio
    async def test_check_email_for_alerts_no_credentials(self):
        """Test email check with missing credentials."""
        with patch("email_sink.monitor.config") as mock_config:
            mock_config.email_sink_enabled = True
            mock_config.email_address = ""
            mock_config.email_password = ""

            service = EmailMonitorService()
            await service.check_email_for_alerts()

            # Should return early without error

    @pytest.mark.asyncio
    async def test_check_email_for_alerts_success(self):
        """Test successful email check."""
        mock_email_client = Mock()
        mock_email_client.__enter__ = Mock(return_value=mock_email_client)
        mock_email_client.__exit__ = Mock(return_value=None)

        with patch("email_sink.monitor.config") as mock_config:
            mock_config.email_sink_enabled = True
            mock_config.email_address = "test@example.com"
            mock_config.email_password = "password"

            with patch(
                "email_sink.monitor.EmailClient", return_value=mock_email_client
            ):
                service = EmailMonitorService()
                with patch.object(
                    service, "_process_sink_config", new_callable=AsyncMock
                ) as mock_process:
                    await service.check_email_for_alerts()

                    # Should process each sink config
                    assert mock_process.call_count == len(service.email_configs)

    @pytest.mark.asyncio
    async def test_process_sink_config_no_messages(self):
        """Test processing sink config with no messages."""
        mock_email_client = Mock()
        mock_email_client.get_unread_messages_from_sender.return_value = []

        sink_config = EmailSinkConfig(
            sender_pattern="test@example.com",
            endpoint="/test_alert",
            description="Test alerts",
        )

        service = EmailMonitorService()
        await service._process_sink_config(mock_email_client, sink_config)

        mock_email_client.get_unread_messages_from_sender.assert_called_once_with(
            "test@example.com"
        )

    @pytest.mark.asyncio
    async def test_process_sink_config_with_messages(self):
        """Test processing sink config with messages."""
        mock_email_client = Mock()
        mock_email_client.get_unread_messages_from_sender.return_value = [
            ("123", b"raw_message_1"),
            ("456", b"raw_message_2"),
        ]
        mock_email_client.mark_as_read = Mock()

        mock_alert = EmailAlert(
            uid="123",
            subject="Test Alert",
            body="Alert body",
            sender="test@example.com",
            date=datetime.now(),
        )

        sink_config = EmailSinkConfig(
            sender_pattern="test@example.com",
            endpoint="/test_alert",
            description="Test alerts",
        )

        with patch("email_sink.monitor.EmailParser") as mock_parser:
            mock_parser.parse_raw_message.return_value = mock_alert

            service = EmailMonitorService()
            with patch.object(
                service,
                "_post_alert_to_endpoint",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_post:
                await service._process_sink_config(mock_email_client, sink_config)

                # Should parse and post both messages
                assert mock_parser.parse_raw_message.call_count == 2
                assert mock_post.call_count == 2
                assert mock_email_client.mark_as_read.call_count == 2

    @pytest.mark.asyncio
    async def test_process_sink_config_parse_failure(self):
        """Test processing when email parsing fails."""
        mock_email_client = Mock()
        mock_email_client.get_unread_messages_from_sender.return_value = [
            ("123", b"invalid_message")
        ]

        sink_config = EmailSinkConfig(
            sender_pattern="test@example.com",
            endpoint="/test_alert",
            description="Test alerts",
        )

        with patch("email_sink.monitor.EmailParser") as mock_parser:
            mock_parser.parse_raw_message.return_value = None  # Parse failure

            service = EmailMonitorService()
            with patch.object(
                service, "_post_alert_to_endpoint", new_callable=AsyncMock
            ) as mock_post:
                await service._process_sink_config(mock_email_client, sink_config)

                # Should not post or mark as read when parsing fails
                mock_post.assert_not_called()
                mock_email_client.mark_as_read.assert_not_called()

    @pytest.mark.asyncio
    async def test_post_alert_to_endpoint_success(self):
        """Test successfully posting alert to endpoint."""
        alert = EmailAlert(
            uid="123",
            subject="Test Alert",
            body="Alert body",
            sender="test@example.com",
            date=now_local(),
        )

        mock_response = Mock()
        mock_response.status_code = 200

        with patch("email_sink.monitor.config") as mock_config:
            mock_config.app_url = "http://localhost:8000"
            mock_config.x_token = "test_token"

            with patch("email_sink.monitor.httpx.AsyncClient") as mock_client:
                mock_client_instance = AsyncMock()
                mock_client_instance.post.return_value = mock_response
                mock_client.return_value.__aenter__.return_value = mock_client_instance

                service = EmailMonitorService()
                result = await service._post_alert_to_endpoint(alert, "/test_alert")

                assert result is True
                mock_client_instance.post.assert_called_once()

                # Verify that the datetime was properly serialized
                call_args = mock_client_instance.post.call_args
                posted_data = call_args.kwargs["json"]
                assert isinstance(
                    posted_data["date"], str
                )  # Should be serialized to string

    @pytest.mark.asyncio
    async def test_post_alert_to_endpoint_failure(self):
        """Test posting alert to endpoint with HTTP error."""
        alert = EmailAlert(
            uid="123",
            subject="Test Alert",
            body="Alert body",
            sender="test@example.com",
            date=now_local(),
        )

        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch("email_sink.monitor.config") as mock_config:
            mock_config.app_url = "http://localhost:8000"
            mock_config.x_token = "test_token"

            with patch("email_sink.monitor.httpx.AsyncClient") as mock_client:
                mock_client_instance = AsyncMock()
                mock_client_instance.post.return_value = mock_response
                mock_client.return_value.__aenter__.return_value = mock_client_instance

                service = EmailMonitorService()
                result = await service._post_alert_to_endpoint(alert, "/test_alert")

                assert result is False

    @pytest.mark.asyncio
    async def test_post_alert_to_endpoint_exception(self):
        """Test posting alert with exception."""
        alert = EmailAlert(
            uid="123",
            subject="Test Alert",
            body="Alert body",
            sender="test@example.com",
            date=now_local(),
        )

        with patch("email_sink.monitor.config") as mock_config:
            mock_config.app_url = "http://localhost:8000"
            mock_config.x_token = "test_token"

            with patch("email_sink.monitor.httpx.AsyncClient") as mock_client:
                mock_client_instance = AsyncMock()
                mock_client_instance.post.side_effect = Exception("Network error")
                mock_client.return_value.__aenter__.return_value = mock_client_instance

                service = EmailMonitorService()
                result = await service._post_alert_to_endpoint(alert, "/test_alert")

                assert result is False

    def test_start_service(self):
        """Test starting the email monitoring service."""
        with patch("email_sink.monitor.config") as mock_config:
            mock_config.email_sink_enabled = True
            mock_config.email_poll_interval = 60

            service = EmailMonitorService()

            # Mock the scheduler to avoid async event loop issues
            with (
                patch.object(service.scheduler, "add_job") as mock_add_job,
                patch.object(service.scheduler, "start") as mock_start,
            ):
                service.start()

                assert service.running is True
                mock_add_job.assert_called_once()
                mock_start.assert_called_once()

    def test_start_service_disabled(self):
        """Test starting service when disabled."""
        with patch("email_sink.monitor.config") as mock_config:
            mock_config.email_sink_enabled = False

            service = EmailMonitorService()
            service.start()

            assert service.running is False

    def test_stop_service(self):
        """Test stopping the email monitoring service."""
        with patch("email_sink.monitor.config") as mock_config:
            mock_config.email_sink_enabled = True

            service = EmailMonitorService()

            # Mock the scheduler to avoid async event loop issues
            with (
                patch.object(service.scheduler, "add_job"),
                patch.object(service.scheduler, "start"),
                patch.object(service.scheduler, "shutdown") as mock_shutdown,
            ):
                service.start()
                service.stop()

                assert service.running is False
                mock_shutdown.assert_called_once()

    def test_get_monitor_service_singleton(self):
        """Test that get_monitor_service returns a singleton."""
        service1 = get_monitor_service()
        service2 = get_monitor_service()

        assert service1 is service2
