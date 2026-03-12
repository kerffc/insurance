"""Subscriber management — tracks Telegram users who subscribe to updates."""

import logging
from datetime import datetime, timezone

from services.storage_service import read_json, write_json
from config import DATA_DIR
import os

logger = logging.getLogger(__name__)

SUBSCRIBERS_FILE = os.path.join(DATA_DIR, "subscribers.json")
BROADCASTS_FILE = os.path.join(DATA_DIR, "broadcasts.json")


def get_subscribers() -> list[dict]:
    return read_json(SUBSCRIBERS_FILE) or []


def add_subscriber(chat_id: int, first_name: str = "", username: str = "") -> bool:
    """Add subscriber. Returns True if new, False if already exists."""
    subs = get_subscribers()
    if any(s["chat_id"] == chat_id for s in subs):
        return False
    subs.append({
        "chat_id": chat_id,
        "first_name": first_name,
        "username": username,
        "subscribed_at": datetime.now(timezone.utc).isoformat(),
        "active": True,
    })
    write_json(SUBSCRIBERS_FILE, subs)
    return True


def remove_subscriber(chat_id: int) -> bool:
    """Remove subscriber. Returns True if found and removed."""
    subs = get_subscribers()
    new_subs = [s for s in subs if s["chat_id"] != chat_id]
    if len(new_subs) == len(subs):
        return False
    write_json(SUBSCRIBERS_FILE, new_subs)
    return True


def get_active_subscribers() -> list[dict]:
    return [s for s in get_subscribers() if s.get("active", True)]


def save_broadcast(message: str, sent_to: int, source_url: str = "") -> dict:
    """Save a broadcast record."""
    broadcasts = read_json(BROADCASTS_FILE) or []
    record = {
        "id": len(broadcasts) + 1,
        "message_preview": message[:200],
        "full_message": message,
        "source_url": source_url,
        "sent_to": sent_to,
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }
    broadcasts.append(record)
    write_json(BROADCASTS_FILE, broadcasts)
    return record


def get_broadcasts() -> list[dict]:
    return read_json(BROADCASTS_FILE) or []
