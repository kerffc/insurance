"""Auth router — login, register (first user = admin + auto-approved)."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from deps import pwd_context, create_token, get_current_user
from rate_limit import login_limiter
from services.storage_service import read_users, write_users

router = APIRouter()


class AuthRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: AuthRequest, request: Request):
    login_limiter.check(request)
    users = read_users()
    user = next((u for u in users if u["username"] == body.username), None)
    if not user or not pwd_context.verify(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials.")
    if not user.get("approved", False):
        raise HTTPException(status_code=403, detail="PENDING_APPROVAL")
    return {
        "token": create_token(body.username),
        "username": body.username,
        "role": user.get("role", "user"),
    }


@router.post("/register")
def register(body: AuthRequest, request: Request):
    login_limiter.check(request)
    if not body.username.strip() or not body.password.strip():
        raise HTTPException(status_code=400, detail="Username and password are required.")
    users = read_users()
    if any(u["username"] == body.username for u in users):
        raise HTTPException(status_code=409, detail="Username already taken.")
    is_first = len(users) == 0
    new_user = {
        "username": body.username,
        "password_hash": pwd_context.hash(body.password),
        "role": "admin" if is_first else "user",
        "approved": is_first,
    }
    users.append(new_user)
    write_users(users)
    if is_first:
        return {
            "token": create_token(body.username),
            "username": body.username,
            "role": "admin",
            "message": "First user registered as admin.",
        }
    return {"message": "Registration submitted. Awaiting admin approval."}
