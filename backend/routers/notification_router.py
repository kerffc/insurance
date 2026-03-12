"""Notification router — generate messages, manage sessions, dashboard."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from deps import get_current_user
from services.message_service import generate_messages_batch
from services.storage_service import (
    read_policy_changes, read_session, write_session, list_sessions,
)

router = APIRouter()


class GenerateRequest(BaseModel):
    clients: list[dict]
    policy_change_id: str
    channel_map: dict[str, str]  # {client_id: "whatsapp"|"email"|"sms"}
    agent_name: str


class NotificationUpdate(BaseModel):
    message: Optional[str] = None
    status: Optional[str] = None  # "reviewed" | "sent"


class BulkStatusUpdate(BaseModel):
    notification_ids: list[str]
    status: str  # "reviewed" | "sent"


@router.post("/generate-messages")
def generate_messages(body: GenerateRequest, username: str = Depends(get_current_user)):
    changes = read_policy_changes()
    change = next((c for c in changes if c["id"] == body.policy_change_id), None)
    if not change:
        raise HTTPException(status_code=404, detail="Policy change not found.")

    results = generate_messages_batch(body.clients, change, body.channel_map, body.agent_name)

    now = datetime.now(timezone.utc).isoformat()
    notifications = []
    for r in results:
        client = next((c for c in body.clients if c["id"] == r["client_id"]), None)
        notifications.append({
            "id": str(uuid.uuid4()),
            "client_id": r["client_id"],
            "client_name": client["name"] if client else "Unknown",
            "channel": r["channel"],
            "message": r["message"],
            "error": r["error"],
            "status": "pending",
            "reviewed_at": None,
            "sent_at": None,
            "edited": False,
        })

    session = {
        "id": str(uuid.uuid4()),
        "created_at": now,
        "created_by": username,
        "policy_change_id": body.policy_change_id,
        "policy_change_title": change["change_title"],
        "clients": body.clients,
        "notifications": notifications,
    }
    write_session(session["id"], session)
    return session


@router.get("/sessions")
def get_sessions(username: str = Depends(get_current_user)):
    return list_sessions()


@router.get("/sessions/{session_id}")
def get_session(session_id: str, username: str = Depends(get_current_user)):
    session = read_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    return session


@router.patch("/sessions/{session_id}/notifications/{notif_id}")
def update_notification(
    session_id: str,
    notif_id: str,
    body: NotificationUpdate,
    username: str = Depends(get_current_user),
):
    session = read_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    notif = next((n for n in session["notifications"] if n["id"] == notif_id), None)
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found.")

    now = datetime.now(timezone.utc).isoformat()
    if body.message is not None:
        notif["message"] = body.message
        notif["edited"] = True
    if body.status:
        notif["status"] = body.status
        if body.status == "reviewed":
            notif["reviewed_at"] = now
        elif body.status == "sent":
            notif["sent_at"] = now

    write_session(session_id, session)
    return notif


@router.patch("/sessions/{session_id}/notifications/bulk-status")
def bulk_update_status(
    session_id: str,
    body: BulkStatusUpdate,
    username: str = Depends(get_current_user),
):
    session = read_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    now = datetime.now(timezone.utc).isoformat()
    updated = 0
    for notif in session["notifications"]:
        if notif["id"] in body.notification_ids:
            notif["status"] = body.status
            if body.status == "reviewed":
                notif["reviewed_at"] = now
            elif body.status == "sent":
                notif["sent_at"] = now
            updated += 1

    write_session(session_id, session)
    return {"updated": updated}


@router.get("/dashboard/stats")
def dashboard_stats(username: str = Depends(get_current_user)):
    sessions = list_sessions()
    total_notifications = sum(s["total_notifications"] for s in sessions)
    total_sent = sum(s["sent_count"] for s in sessions)
    total_pending = total_notifications - total_sent
    return {
        "total_sessions": len(sessions),
        "total_notifications": total_notifications,
        "total_sent": total_sent,
        "total_pending": total_pending,
        "sessions": sessions,
    }
