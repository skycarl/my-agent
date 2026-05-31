"""
Tests for the runtime access-control allowlist.
"""

import pytest
from unittest.mock import patch

from app.core.settings import Config

pytestmark = [pytest.mark.unit, pytest.mark.app]

OWNER = 100
FAMILY = 200
GROUP = -100123


@pytest.fixture()
def access(tmp_path):
    """Import access_control with an isolated config (temp storage, known owner)."""
    cfg = Config.create_test_config(storage_path=str(tmp_path), owner_user_id=OWNER)
    with patch("app.core.access_control.config", cfg):
        import app.core.access_control as ac

        yield ac


class TestAuthorization:
    def test_owner_always_authorized(self, access):
        assert access.is_authorized(OWNER, OWNER, "private") is True
        assert access.is_authorized(OWNER, GROUP, "supergroup") is True

    def test_unknown_private_user_denied(self, access):
        assert access.is_authorized(FAMILY, FAMILY, "private") is False

    def test_added_user_authorized_in_private(self, access):
        assert access.add_user(FAMILY) is True
        assert access.is_authorized(FAMILY, FAMILY, "private") is True

    def test_group_member_denied_until_group_allowed(self, access):
        # A non-owner in a group is denied until the group is allowlisted.
        assert access.is_authorized(FAMILY, GROUP, "supergroup") is False
        assert access.add_group(GROUP) is True
        assert access.is_authorized(FAMILY, GROUP, "supergroup") is True
        # Anyone in the allowlisted group is allowed, even users not on the user list.
        assert access.is_authorized(999, GROUP, "group") is True

    def test_added_user_not_authorized_in_unlisted_group(self, access):
        access.add_user(FAMILY)
        # Private authorization does not extend to arbitrary groups.
        assert access.is_authorized(FAMILY, GROUP, "supergroup") is False


class TestMutations:
    def test_add_is_idempotent(self, access):
        assert access.add_user(FAMILY) is True
        assert access.add_user(FAMILY) is False

    def test_remove_user(self, access):
        access.add_user(FAMILY)
        assert access.remove_user(FAMILY) is True
        assert access.remove_user(FAMILY) is False
        assert access.is_authorized(FAMILY, FAMILY, "private") is False

    def test_remove_group(self, access):
        access.add_group(GROUP)
        assert access.remove_group(GROUP) is True
        assert access.remove_group(GROUP) is False

    def test_list_authorized(self, access):
        access.add_user(FAMILY)
        access.add_group(GROUP)
        data = access.list_authorized()
        assert data == {"users": [FAMILY], "groups": [GROUP]}
