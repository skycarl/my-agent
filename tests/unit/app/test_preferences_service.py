"""
Test commute preferences service.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.agents.commute.preferences_service import (
    read_preferences_file,
    write_preferences_file,
    get_commute_overrides,
    add_commute_override,
    remove_commute_override,
    get_full_commute_context,
    cleanup_expired_overrides,
)
from app.core.settings import Config


@pytest.fixture
def test_config(tmp_path):
    """Create a test config with tmp_path as storage."""
    cfg = Config.create_test_config(storage_path=str(tmp_path))
    with patch("app.agents.commute.preferences_service.config", cfg):
        yield cfg


class TestReadPreferencesFile:
    def test_read_preferences_file(self, test_config, tmp_path):
        """Test reading an existing preferences file."""
        prefs_path = Path(test_config.commute_preferences_path)
        prefs_path.write_text("# My Preferences\n- Monday: Remote\n", encoding="utf-8")
        result = read_preferences_file()
        assert "# My Preferences" in result
        assert "Monday: Remote" in result

    def test_read_preferences_file_not_exists(self, test_config):
        """Test reading when the preferences file doesn't exist."""
        result = read_preferences_file()
        assert result == ""


class TestWritePreferencesFile:
    def test_write_preferences_file(self, test_config, tmp_path):
        """Test writing content to the preferences file."""
        content = "# Updated Preferences\n- Monday: Office\n"
        result = write_preferences_file(content)
        assert "updated successfully" in result

        # Verify file content
        prefs_path = Path(test_config.commute_preferences_path)
        assert prefs_path.read_text(encoding="utf-8") == content


class TestGetCommuteOverrides:
    def test_get_commute_overrides(self, test_config, tmp_path):
        """Test reading overrides and filtering expired entries."""
        overrides = [
            {
                "id": "a1",
                "date": "2026-03-01",
                "type": "commute_day",
                "note": "meeting",
                "expires_after": "2099-12-31",
            },
            {
                "id": "a2",
                "date": "2020-01-01",
                "type": "remote_day",
                "note": "old",
                "expires_after": "2020-01-01",
            },
        ]
        Path(test_config.commute_overrides_path).write_text(
            json.dumps(overrides), encoding="utf-8"
        )
        result = get_commute_overrides()
        assert len(result) == 1
        assert result[0]["id"] == "a1"

    def test_get_commute_overrides_empty_file(self, test_config, tmp_path):
        """Test with no overrides file."""
        result = get_commute_overrides()
        assert result == []


class TestAddCommuteOverride:
    def test_add_commute_override(self, test_config, tmp_path):
        """Test adding an override entry."""
        # Seed empty file
        Path(test_config.commute_overrides_path).write_text("[]", encoding="utf-8")

        entry = add_commute_override(
            date="2026-03-05",
            override_type="commute_day",
            note="team offsite",
            expires_after="2026-03-05",
        )
        assert entry["date"] == "2026-03-05"
        assert entry["type"] == "commute_day"
        assert entry["note"] == "team offsite"
        assert entry["expires_after"] == "2026-03-05"
        assert "id" in entry
        assert "created_at" in entry

        # Verify persisted
        raw = json.loads(Path(test_config.commute_overrides_path).read_text())
        assert len(raw) == 1

    def test_add_commute_override_defaults_expires_after(self, test_config, tmp_path):
        """Test that expires_after defaults to the override date."""
        Path(test_config.commute_overrides_path).write_text("[]", encoding="utf-8")

        entry = add_commute_override(
            date="2026-04-10",
            override_type="remote_day",
            note="dentist appointment",
        )
        assert entry["expires_after"] == "2026-04-10"

    def test_add_commute_override_invalid_type(self, test_config, tmp_path):
        """Test that invalid override_type raises ValueError."""
        Path(test_config.commute_overrides_path).write_text("[]", encoding="utf-8")
        with pytest.raises(ValueError, match="Invalid override_type"):
            add_commute_override(
                date="2026-03-05", override_type="invalid", note="nope"
            )


class TestRemoveCommuteOverride:
    def test_remove_commute_override(self, test_config, tmp_path):
        """Test removing an override by ID."""
        overrides = [
            {
                "id": "x1",
                "date": "2026-03-01",
                "type": "commute_day",
                "note": "a",
                "expires_after": "2026-03-01",
            },
            {
                "id": "x2",
                "date": "2026-03-02",
                "type": "remote_day",
                "note": "b",
                "expires_after": "2026-03-02",
            },
        ]
        Path(test_config.commute_overrides_path).write_text(
            json.dumps(overrides), encoding="utf-8"
        )

        assert remove_commute_override("x1") is True
        remaining = json.loads(Path(test_config.commute_overrides_path).read_text())
        assert len(remaining) == 1
        assert remaining[0]["id"] == "x2"

    def test_remove_commute_override_not_found(self, test_config, tmp_path):
        """Test removing a non-existent override returns False."""
        Path(test_config.commute_overrides_path).write_text("[]", encoding="utf-8")
        assert remove_commute_override("nonexistent") is False


class TestGetFullCommuteContext:
    def test_get_full_commute_context(self, test_config, tmp_path):
        """Test building full commute context string."""
        # Write preferences
        Path(test_config.commute_preferences_path).write_text(
            "# Commute Preferences\n- Thursday: Office\n", encoding="utf-8"
        )
        # Write active override
        overrides = [
            {
                "id": "o1",
                "date": "2026-03-05",
                "type": "commute_day",
                "note": "offsite",
                "expires_after": "2099-12-31",
            },
        ]
        Path(test_config.commute_overrides_path).write_text(
            json.dumps(overrides), encoding="utf-8"
        )

        result = get_full_commute_context()
        assert "Today is" in result
        assert "Commute Preferences" in result
        assert "Thursday: Office" in result
        assert "Active Overrides" in result
        assert "commute_day" in result

    def test_get_full_commute_context_empty(self, test_config, tmp_path):
        """Test context when no preferences or overrides exist."""
        result = get_full_commute_context()
        assert "Today is" in result
        assert "No preferences configured" in result
        assert "No active overrides" in result


class TestCleanupExpiredOverrides:
    def test_cleanup_expired_overrides(self, test_config, tmp_path):
        """Test that expired entries are pruned."""
        overrides = [
            {
                "id": "keep",
                "date": "2099-01-01",
                "type": "commute_day",
                "note": "future",
                "expires_after": "2099-01-01",
            },
            {
                "id": "remove",
                "date": "2020-01-01",
                "type": "remote_day",
                "note": "past",
                "expires_after": "2020-01-01",
            },
        ]
        Path(test_config.commute_overrides_path).write_text(
            json.dumps(overrides), encoding="utf-8"
        )

        removed = cleanup_expired_overrides()
        assert removed == 1

        remaining = json.loads(Path(test_config.commute_overrides_path).read_text())
        assert len(remaining) == 1
        assert remaining[0]["id"] == "keep"

    def test_cleanup_expired_overrides_nothing_to_remove(self, test_config, tmp_path):
        """Test cleanup when no entries are expired."""
        overrides = [
            {
                "id": "keep",
                "date": "2099-01-01",
                "type": "commute_day",
                "note": "future",
                "expires_after": "2099-01-01",
            },
        ]
        Path(test_config.commute_overrides_path).write_text(
            json.dumps(overrides), encoding="utf-8"
        )

        removed = cleanup_expired_overrides()
        assert removed == 0
