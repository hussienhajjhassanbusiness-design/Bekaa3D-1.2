import asyncio
from typing import Literal

import structlog
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import text

from app.core.config import get_settings

logger = structlog.get_logger()

router = APIRouter(tags=["health"])

# Per dependency. A probe that hangs is worse than one that fails: the
# orchestrator waits on it instead of routing traffic away (BUG-14).
READINESS_TIMEOUT_SECONDS = 2.0


class LivenessRead(BaseModel):
    status: Literal["ok"] = "ok"


class ReadinessRead(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    commit: str


@router.get("/health/live", response_model=LivenessRead)
async def liveness() -> LivenessRead:
    """Process liveness only. Never probes dependencies - a slow database must
    not make the orchestrator kill a perfectly healthy process."""
    return LivenessRead()


@router.get("/health/ready", response_model=ReadinessRead)
async def readiness(request: Request) -> ReadinessRead:
    """Checks dependencies this instance actually needs to serve requests.
    Never includes secrets - only version/commit for deploy verification."""
    settings = get_settings()

    async def probe_database() -> None:
        async with request.app.state.db_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    try:
        await asyncio.wait_for(probe_database(), READINESS_TIMEOUT_SECONDS)
    except Exception as exc:
        await logger.awarning("readiness_db_unavailable")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database is unavailable."
        ) from exc

    try:
        await asyncio.wait_for(request.app.state.redis.ping(), READINESS_TIMEOUT_SECONDS)
    except Exception as exc:
        await logger.awarning("readiness_redis_unavailable")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="Redis is unavailable."
        ) from exc

    return ReadinessRead(version=settings.app_version, commit=settings.git_commit_sha)
