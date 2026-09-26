from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.core.security import get_current_user
from app.api.users.schemas import (
    UserProfileUpdate,
    UserProfileResponse,
    UserPreferenceUpdate,
    UserPreferenceResponse,
)
from app.api.users.service import UserService

router = APIRouter(prefix="/users", tags=["Users & Preferences"])


@router.get("/me", response_model=UserProfileResponse)
@router.get("/me/profile", response_model=UserProfileResponse)
def get_current_user_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve the current user's profile."""
    return UserService.get_profile(db, current_user.id)


@router.put("/me", response_model=UserProfileResponse)
@router.put("/me/profile", response_model=UserProfileResponse)
def update_current_user_profile(
    payload: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update the current user's profile details."""
    return UserService.update_profile(db, current_user.id, payload)


@router.get("/me/preferences", response_model=UserPreferenceResponse)
def get_user_preferences(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve the current user's genre preferences."""
    return UserService.get_preferences(db, current_user.id)


@router.put("/me/preferences", response_model=UserPreferenceResponse)
def update_user_preferences(
    payload: UserPreferenceUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update the current user's genre preferences with strict taxonomy validation."""
    return UserService.update_preferences(db, current_user.id, payload)
