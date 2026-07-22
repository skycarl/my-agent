"""
Tests for alert cancellation/resolution handling.
"""

import json
from datetime import timedelta, timezone
from unittest.mock import patch

from app.agents.alert_processor_agent import AlertDecision
from app.agents.commute.commute_service import (
    AlertSummary,
    cleanup_old_alerts,
    get_recent_alerts,
)
from app.core.settings import config
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
        self._write_alerts(tmp_path, alerts)

        with patch.object(config, "storage_path", str(tmp_path)):
            result = get_recent_alerts(days=7, status=None)
            assert len(result.alerts) == 2

    def test_filter_active(self, tmp_path):
        """status='active' returns only active alerts."""
        alerts = [
            self._make_alert("a1", "Route 40 delay", status="active"),
            self._make_alert("a2", "Route 40 cleared", status="resolved"),
        ]
        self._write_alerts(tmp_path, alerts)

        with patch.object(config, "storage_path", str(tmp_path)):
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
        self._write_alerts(tmp_path, alerts)

        with patch.object(config, "storage_path", str(tmp_path)):
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
        self._write_alerts(tmp_path, [legacy_alert])

        with patch.object(config, "storage_path", str(tmp_path)):
            result = get_recent_alerts(days=7, status="active")
            assert len(result.alerts) == 1
            assert result.alerts[0].status == "active"

    def test_utc_dates_not_excluded_by_timezone_mismatch(self, tmp_path):
        """Alerts stored with UTC dates (+00:00) are correctly included in results.

        Regression test: string comparison of ISO dates with different timezone
        offsets (e.g. +00:00 vs -07:00) could wrongly exclude recent alerts.
        """
        # Create an alert with a UTC received_date (1 hour ago)
        now = now_local()
        utc_date = (now - timedelta(hours=1)).astimezone(timezone.utc)
        alert = self._make_alert(
            "utc_alert",
            "Sounder delay",
            received_date=utc_date.isoformat(),
        )
        self._write_alerts(tmp_path, [alert])

        with patch.object(config, "storage_path", str(tmp_path)):
            result = get_recent_alerts(days=2, status=None)
            assert len(result.alerts) == 1
            assert result.alerts[0].id == "utc_alert"

    def test_str_format_dates_not_excluded(self, tmp_path):
        """Alerts stored with str(datetime) format (space separator) are included.

        Regression test: str(datetime) uses space separator instead of T,
        which caused string comparison to always evaluate as less than the
        T-formatted cutoff.
        """
        now = now_local()
        # str(datetime) uses space separator: "2026-03-18 22:00:00-07:00"
        str_date = str(now - timedelta(hours=1))
        alert = self._make_alert(
            "str_alert",
            "Bus delay",
            received_date=str_date,
        )
        self._write_alerts(tmp_path, [alert])

        with patch.object(config, "storage_path", str(tmp_path)):
            result = get_recent_alerts(days=2, status=None)
            assert len(result.alerts) == 1
            assert result.alerts[0].id == "str_alert"

    def test_summary_includes_id(self, tmp_path):
        """AlertSummary includes the alert id field."""
        alerts = [self._make_alert("alert_42_xyz", "Test alert")]
        self._write_alerts(tmp_path, alerts)

        with patch.object(config, "storage_path", str(tmp_path)):
            result = get_recent_alerts(days=7)
            assert result.alerts[0].id == "alert_42_xyz"


class TestAlertsPathResolution:
    """Regression tests for the reader/writer path split.

    The reader used a hardcoded CWD-relative path while the /process_alert
    writer used config.storage_path — in Docker (CWD=/app,
    STORAGE_PATH=/app/workspace/storage) they pointed at different files, so
    freshly stored alerts were invisible to get_recent_alerts.
    """

    def _make_alert(self, uid):
        now = now_local()
        return {
            "id": f"alert_1_{uid}",
            "uid": uid,
            "subject": "Link light rail delay",
            "body": "test",
            "sender": "alerts@transit.com",
            "received_date": now.isoformat(),
            "stored_date": now.isoformat(),
            "alert_type": "email",
            "notify_user": True,
            "message_content": "Link light rail delay",
            "status": "active",
            "agent_processing": {"agent_response": ""},
        }

    def test_reader_uses_config_storage_path_not_cwd(self, tmp_path, monkeypatch):
        """Alerts under config.storage_path are found even when the CWD has a
        different (stale/empty) storage/commute_alerts.json."""
        real_storage = tmp_path / "real_storage"
        real_storage.mkdir()
        with open(real_storage / "commute_alerts.json", "w") as f:
            json.dump([self._make_alert("fresh")], f)

        # Decoy: a CWD-relative storage dir with an empty alerts file, like
        # the stale snapshot baked into the Docker image
        cwd = tmp_path / "container_workdir"
        (cwd / "storage").mkdir(parents=True)
        with open(cwd / "storage" / "commute_alerts.json", "w") as f:
            json.dump([], f)
        monkeypatch.chdir(cwd)

        with patch.object(config, "storage_path", str(real_storage)):
            result = get_recent_alerts(days=2, status="active")

        assert result.total_stored == 1
        assert len(result.alerts) == 1
        assert result.alerts[0].subject == "Link light rail delay"

    def test_cleanup_uses_config_storage_path_not_cwd(self, tmp_path, monkeypatch):
        """cleanup_old_alerts prunes the config-derived file, not a CWD-relative one."""
        real_storage = tmp_path / "real_storage"
        real_storage.mkdir()
        old_alert = self._make_alert("old")
        old_alert["stored_date"] = (now_local() - timedelta(days=45)).isoformat()
        with open(real_storage / "commute_alerts.json", "w") as f:
            json.dump([old_alert], f)

        cwd = tmp_path / "container_workdir"
        cwd.mkdir()
        monkeypatch.chdir(cwd)

        with patch.object(config, "storage_path", str(real_storage)):
            removed = cleanup_old_alerts(retention_days=30)

        assert removed == 1
        with open(real_storage / "commute_alerts.json") as f:
            assert json.load(f) == []


class TestCleanupOldAlerts:
    """Tests for cleanup_old_alerts date handling."""

    def test_mixed_utc_offsets_compared_as_datetimes(self, tmp_path):
        """A recent UTC-offset stored_date must survive cleanup even though it
        sorts lexicographically before a local-offset cutoff string."""
        recent_utc = (now_local() - timedelta(days=1)).astimezone(timezone.utc)
        old_local = now_local() - timedelta(days=45)
        alerts = [
            {"uid": "recent_utc", "stored_date": recent_utc.isoformat()},
            {"uid": "old_local", "stored_date": old_local.isoformat()},
            {"uid": "legacy_no_date"},
            {"uid": "unparseable", "stored_date": "not-a-date"},
        ]
        with open(tmp_path / "commute_alerts.json", "w") as f:
            json.dump(alerts, f)

        with patch.object(config, "storage_path", str(tmp_path)):
            removed = cleanup_old_alerts(retention_days=30)

        assert removed == 1
        with open(tmp_path / "commute_alerts.json") as f:
            remaining = {a["uid"] for a in json.load(f)}
        assert remaining == {"recent_utc", "legacy_no_date", "unparseable"}
