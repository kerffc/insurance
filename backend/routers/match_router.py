"""Match clients to policy changes."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from deps import get_current_user
from services.matching_service import match_clients
from services.storage_service import read_policy_changes

router = APIRouter()


class MatchRequest(BaseModel):
    clients: list[dict]
    policy_change_id: str


@router.post("/match")
def match(body: MatchRequest, username: str = Depends(get_current_user)):
    changes = read_policy_changes()
    change = next((c for c in changes if c["id"] == body.policy_change_id), None)
    if not change:
        raise HTTPException(status_code=404, detail="Policy change not found.")
    matched = match_clients(body.clients, change)
    return {
        "policy_change": change,
        "total_clients": len(body.clients),
        "matched_count": len(matched),
        "matched_clients": matched,
    }
