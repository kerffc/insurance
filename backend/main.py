"""Insurance Update Automation — FastAPI backend."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import ALLOWED_ORIGINS
from services.storage_service import ensure_dirs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_dirs()
    logger.info("Insurance Update Automation started")
    yield


app = FastAPI(title="Insurance Update Automation", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──────────────────────────────────────────────────────────────────
from routers.auth_router import router as auth_router
from routers.upload_router import router as upload_router
from routers.policy_router import router as policy_router
from routers.match_router import router as match_router
from routers.notification_router import router as notification_router

app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(upload_router, prefix="/api", tags=["upload"])
app.include_router(policy_router, prefix="/api", tags=["policy-changes"])
app.include_router(match_router, prefix="/api", tags=["matching"])
app.include_router(notification_router, prefix="/api", tags=["notifications"])


@app.get("/api/health")
def health():
    return {"status": "ok"}
