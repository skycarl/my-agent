"""
Tests for alert cancellation/resolution handling.
"""

import json
from unittest.mock import patch

from app.agents.alert_processor_agent import AlertDecision
from app.agents.commute.commute_service import (
    AlertSummary,
    get_recent_alerts,
)
from app.core.timezone_utils import now_local


class TestAlertDecisionModel:
    """Test AlertDecision model with resolves_alert_id field."""

    def test_alert_decision_without_resolves(self):
        """AlertDecision works without resolves_alert_id (backward compat)."""
        decision = AlertDecision(
            rationale="Normal disruption alert",
            notify_user=True,
            message_content="Route 40 delayed 15 min",
        )
        assert decision.resolves_alert_id is None
        assert decision.notify_user is True

    def test_alert_decision_with_resolves(self):
        """AlertDecision includes resolves_alert_id for cancellations."""
        decision = AlertDecision(
            rationale="This is a cancellation of a previous alert",
            notify_user=True,
            message_content="Route 40 delay has been cleared",
            resolves_alert_id="alert_1_abc123",
        )
        assert decision.resolves_alert_id == "alert_1_abc123"


class TestAlertSummaryModel:
    """Test AlertSummary model with status fields."""

    def test_alert_summary_defaults(self):
        """AlertSummary defaults to active status with no resolved_by."""
        summary = AlertSummary(
            subject="Route 40 delays",
            received_date="2026-03-10T08:00:00",
            alert_type="email",
            notify_user=True,
            message_content="Delays on Route 40",
        )
        assert summary.status == "active"
        assert summary.resolved_by is None
        assert summary.id == ""

    def test_alert_summary_resolved(self):
        """AlertSummary can represent a resolved alert."""
        summary = AlertSummary(
            id="alert_1_abc",
            subject="Route 40 delays",
            received_date="2026-03-10T08:00:00",
            alert_type="email",
            notify_user=True,
            message_content="Delays on Route 40",
            status="resolved",
            resolved_by="alert_2_def",
        )
        assert summary.status == "resolved"
        assert summary.resolved_by == "alert_2_def"


class TestGetRecentAlertsStatusFilter:
    """Test get_recent_alerts with status filtering."""

    def _write_alerts(self, tmp_path, alerts):
        alerts_file = tmp_path / "commute_alerts.json"
        with open(alerts_file, "w") as f:
            json.dump(alerts, f)
        return alerts_file

    def _make_alert(self, id, subject, status="active", **kwargs):
        now = now_local()
        base = {
            "id": id,
            "uid": id,
            "subject": subject,
            "body": "test body",
            "sender": "alerts@transit.com",
            "received_date": now.isoformat(),
            "stored_date": now.isoformat(),
            "alert_type": "email",
            "notify_user": True,
            "message_content": subject,
            "status": status,
            "agent_processing": {"agent_response": ""},
        }
        base.update(kwargs)
        return base

    def test_no_filter_returns_all(self, tmp_path):
        """With no status filter, returns both active and resolved alerts."""
        alerts = [
            self._make_alert("a1", "Route 40 delay", status="active"),
            self._make_alert(
                "a2", "Route 40 cleared", status="resolved", resolved_by="a3"
            ),
        ]
        alerts_file = self._write_alerts(tmp_path, alerts)

        with patch.object(
            __import__("app.agents.commute.commute_service", fromlist=["ALERTS_FILE"]),
            "ALERTS_FILE",
            alerts_file,
        ):
            result = get_recent_alerts(days=7, status=None)
            assert len(result.alerts) == 2

    def test_filter_active(self, tmp_path):
        """status='active' returns only active alerts."""
        alerts = [
            self._make_alert("a1", "Route 40 delay", status="active"),
            self._make_alert("a2", "Route 40 cleared", status="resolved"),
        ]
        alerts_file = self._write_alerts(tmp_path, alerts)

        with patch.object(
            __import__("app.agents.commute.commute_service", fromlist=["ALERTS_FILE"]),
            "ALERTS_FILE",
            alerts_file,
        ):
            result = get_recent_alerts(days=7, status="active")
            assert len(result.alerts) == 1
            assert result.alerts[0].status == "active"
            assert result.alerts[0].subject == "Route 40 delay"

    def test_filter_resolved(self, tmp_path):
        """status='resolved' returns only resolved alerts."""
        alerts = [
            self._make_alert("a1", "Route 40 delay", status="active"),
            self._make_alert(
                "a2", "Route 40 cleared", status="resolved", resolved_by="a3"
            ),
        ]
        alerts_file = self._write_alerts(tmp_path, alerts)

        with patch.object(
            __import__("app.agents.commute.commute_service", fromlist=["ALERTS_FILE"]),
            "ALERTS_FILE",
            alerts_file,
        ):
            result = get_recent_alerts(days=7, status="resolved")
            assert len(result.alerts) == 1
            assert result.alerts[0].status == "resolved"
            assert result.alerts[0].resolved_by == "a3"

    def test_missing_status_defaults_to_active(self, tmp_path):
        """Alerts without a status field are treated as active (backward compat)."""
        now = now_local()
        legacy_alert = {
            "id": "old_alert",
            "uid": "old_alert",
            "subject": "Old disruption",
            "body": "test",
            "sender": "alerts@transit.com",
            "received_date": now.isoformat(),
            "stored_date": now.isoformat(),
            "alert_type": "email",
            "notify_user": True,
            "message_content": "Old disruption",
            "agent_processing": {"agent_response": ""},
            # no "status" field
        }
        alerts_file = self._write_alerts(tmp_path, [legacy_alert])

        with patch.object(
            __import__("app.agents.commute.commute_service", fromlist=["ALERTS_FILE"]),
            "ALERTS_FILE",
            alerts_file,
        ):
            result = get_recent_alerts(days=7, status="active")
            assert len(result.alerts) == 1
            assert result.alerts[0].status == "active"

    def test_summary_includes_id(self, tmp_path):
        """AlertSummary includes the alert id field."""
        alerts = [self._make_alert("alert_42_xyz", "Test alert")]
        alerts_file = self._write_alerts(tmp_path, alerts)

        with patch.object(
            __import__("app.agents.commute.commute_service", fromlist=["ALERTS_FILE"]),
            "ALERTS_FILE",
            alerts_file,
        ):
            result = get_recent_alerts(days=7)
            assert result.alerts[0].id == "alert_42_xyz"
