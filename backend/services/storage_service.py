"""JSON file storage with thread-safe locking."""

import json
import logging
import os
import threading

from config import DATA_DIR, USERS_FILE, POLICY_CHANGES_FILE, SESSIONS_DIR

logger = logging.getLogger(__name__)

_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()


def _get_lock(filepath: str) -> threading.Lock:
    with _locks_lock:
        if filepath not in _locks:
            _locks[filepath] = threading.Lock()
        return _locks[filepath]


def ensure_dirs() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(SESSIONS_DIR, exist_ok=True)


def read_json(filepath: str) -> list | dict:
    lock = _get_lock(filepath)
    with lock:
        if not os.path.exists(filepath):
            return []
        with open(filepath, "r") as f:
            return json.load(f)


def write_json(filepath: str, data: list | dict) -> None:
    lock = _get_lock(filepath)
    with lock:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def read_users() -> list[dict]:
    return read_json(USERS_FILE)


def write_users(users: list[dict]) -> None:
    write_json(USERS_FILE, users)


def read_policy_changes() -> list[dict]:
    return read_json(POLICY_CHANGES_FILE)


def write_policy_changes(changes: list[dict]) -> None:
    write_json(POLICY_CHANGES_FILE, changes)


def session_path(session_id: str) -> str:
    return os.path.join(SESSIONS_DIR, f"{session_id}.json")


def read_session(session_id: str) -> dict | None:
    path = session_path(session_id)
    if not os.path.exists(path):
        return None
    return read_json(path)


def write_session(session_id: str, data: dict) -> None:
    write_json(session_path(session_id), data)


def list_sessions() -> list[dict]:
    """List all sessions (metadata only, no full client lists)."""
    sessions = []
    if not os.path.exists(SESSIONS_DIR):
        return sessions
    for fname in sorted(os.listdir(SESSIONS_DIR), reverse=True):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(SESSIONS_DIR, fname)
        data = read_json(path)
        if isinstance(data, dict):
            sessions.append({
                "id": data.get("id"),
                "created_at": data.get("created_at"),
                "created_by": data.get("created_by"),
                "policy_change_id": data.get("policy_change_id"),
                "total_clients": len(data.get("clients", [])),
                "total_notifications": len(data.get("notifications", [])),
                "sent_count": sum(
                    1 for n in data.get("notifications", []) if n.get("status") == "sent"
                ),
            })
    return sessions
