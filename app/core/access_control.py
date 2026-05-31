"""
Runtime access control for the Telegram bot.

Persists an allowlist of authorized private users and group chats to
``storage/authorized_users.json``. The owner (``config.owner_user_id``) is
always authorized everywhere and is never stored in the file.

Shared by the bot (authorization checks + admin commands) and the app. Uses a
FileLock for safe concurrent access, mirroring ``app/core/task_store.py``.
"""

import json
from pathlib import Path
from typing import Dict, List

from filelock import FileLock

from app.core.settings import config


def _store_path() -> Path:
    return Path(config.storage_path) / "authorized_users.json"


def _lock_path() -> str:
    return str(_store_path()) + ".lock"


def _read() -> Dict[str, List[int]]:
    """Read the allowlist, returning a normalized {"users": [...], "groups": [...]} dict."""
    store = _store_path()
    if store.exists():
        try:
            data = json.loads(store.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    else:
        data = {}
    return {
        "users": [int(u) for u in data.get("users", [])],
        "groups": [int(g) for g in data.get("groups", [])],
    }


def _write(data: Dict[str, List[int]]) -> None:
    store = _store_path()
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def is_authorized(user_id: int, chat_id: int, chat_type: str) -> bool:
    """Return True if the given user/chat is allowed to use the bot.

    - private chat: the owner or any allowlisted user
    - group/supergroup: any member of an allowlisted group (the owner is always allowed)
    """
    if user_id == config.owner_user_id:
        return True

    data = _read()
    if chat_type == "private":
        return user_id in data["users"]
    if chat_type in ("group", "supergroup"):
        return chat_id in data["groups"]
    return False


def add_user(user_id: int) -> bool:
    """Add a user to the allowlist. Returns False if already present."""
    with FileLock(_lock_path()):
        data = _read()
        if user_id in data["users"]:
            return False
        data["users"].append(user_id)
        _write(data)
        return True


def remove_user(user_id: int) -> bool:
    """Remove a user from the allowlist. Returns False if not present."""
    with FileLock(_lock_path()):
        data = _read()
        if user_id not in data["users"]:
            return False
        data["users"].remove(user_id)
        _write(data)
        return True


def add_group(chat_id: int) -> bool:
    """Add a group chat to the allowlist. Returns False if already present."""
    with FileLock(_lock_path()):
        data = _read()
        if chat_id in data["groups"]:
            return False
        data["groups"].append(chat_id)
        _write(data)
        return True


def remove_group(chat_id: int) -> bool:
    """Remove a group chat from the allowlist. Returns False if not present."""
    with FileLock(_lock_path()):
        data = _read()
        if chat_id not in data["groups"]:
            return False
        data["groups"].remove(chat_id)
        _write(data)
        return True


def list_authorized() -> Dict[str, List[int]]:
    """Return the current allowlist {"users": [...], "groups": [...]}."""
    return _read()
