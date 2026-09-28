"""WatchMan scoring, feedback, and decision API router."""

from __future__ import annotations

import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.exceptions import ContentNotFoundException
from app.core.security import get_current_user, get_current_user_optional
from app.db.session import get_db
from app.models.content import Content
from app.models.user import User
from app.schemas.watchman import (
    WatchmanDecisionRequest,
    WatchmanScoreResponse,
)
from app.services.watchman_service import WatchmanService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WatchMan Decision & Scoring"])


def _resolve_content(db: Session, content_id: int, content_type: str | None = None) -> Content:
    """Find content by internal ID, or fallback to tmdb_id."""
    query = db.query(Content).filter(Content.id == content_id)
    content = query.first()
    if not content:
        # Fallback to tmdb_id lookup
        t_query = db.query(Content).filter(Content.tmdb_id == content_id)
        if content_type:
            t_query = t_query.filter(Content.content_type == content_type)
        content = t_query.first()

    if not content:
        raise ContentNotFoundException(
            message=f"Content with identifier '{content_id}' was not found.",
            content_id=content_id,
        )
    return content


@router.get(
    "/content/{content_id}/watchman",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Get WatchMan score and classification for content",
)
@router.get(
    "/movies/{content_id}/watchman",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
@router.get(
    "/web-series/{content_id}/watchman",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def get_watchman_score(
    content_id: int,
    content_type: Optional[str] = Query(default=None, pattern="^(movie|tv)$"),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> dict:
    """Return dynamic WatchMan score (0-100), classification, community breakdown, and user decision."""
    content = _resolve_content(db, content_id, content_type)
    score_resp = WatchmanService.compute_watchman_score(
        db=db,
        content=content,
        user_id=current_user.id if current_user else None,
    )
    return {
        "success": True,
        "data": score_resp.model_dump(),
    }


@router.put(
    "/content/{content_id}/watchman",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Submit or update user decision (must_watch, time_pass, skip)",
)
@router.patch(
    "/content/{content_id}/watchman",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
@router.put(
    "/movies/{content_id}/watchman",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
@router.put(
    "/web-series/{content_id}/watchman",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def set_watchman_decision(
    content_id: int,
    payload: WatchmanDecisionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Persist user decision (must_watch, time_pass, or skip) and return updated score."""
    content = _resolve_content(db, content_id, payload.content_type)
    WatchmanService.upsert_user_decision(
        db=db,
        user_id=current_user.id,
        content=content,
        decision=payload.decision,
        content_type=payload.content_type,
    )

    updated_score = WatchmanService.compute_watchman_score(
        db=db,
        content=content,
        user_id=current_user.id,
    )
    return {
        "success": True,
        "data": updated_score.model_dump(),
    }
