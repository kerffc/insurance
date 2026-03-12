"""Policy change CRUD router."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from deps import get_current_user
from services.storage_service import read_policy_changes, write_policy_changes

router = APIRouter()


class PolicyChangeCreate(BaseModel):
    insurer: str
    product_line: str
    plan_names: list[str] = []
    change_title: str
    change_description: str
    effective_date: str
    impact_summary: str
    source_url: Optional[str] = None


class PolicyChangeUpdate(PolicyChangeCreate):
    pass


@router.get("/policy-changes")
def list_policy_changes(username: str = Depends(get_current_user)):
    return read_policy_changes()


@router.post("/policy-changes")
def create_policy_change(body: PolicyChangeCreate, username: str = Depends(get_current_user)):
    changes = read_policy_changes()
    new_change = {
        "id": str(uuid.uuid4()),
        **body.model_dump(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": username,
    }
    changes.append(new_change)
    write_policy_changes(changes)
    return new_change


@router.put("/policy-changes/{change_id}")
def update_policy_change(change_id: str, body: PolicyChangeUpdate, username: str = Depends(get_current_user)):
    changes = read_policy_changes()
    idx = next((i for i, c in enumerate(changes) if c["id"] == change_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Policy change not found.")
    changes[idx].update(body.model_dump())
    write_policy_changes(changes)
    return changes[idx]


@router.delete("/policy-changes/{change_id}")
def delete_policy_change(change_id: str, username: str = Depends(get_current_user)):
    changes = read_policy_changes()
    changes = [c for c in changes if c["id"] != change_id]
    write_policy_changes(changes)
    return {"ok": True}
