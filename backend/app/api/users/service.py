import uuid
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.models.user import User, Profile, UserPreference
from app.models.taxonomy import Genre
from app.core.exceptions import (
    ConflictException,
    NotFoundException,
    ValidationException,
    DatabaseException,
)
from app.api.users.schemas import (
    UserProfileUpdate,
    UserProfileResponse,
    UserPreferenceUpdate,
    UserPreferenceResponse,
    GenreSummary,
)


class UserService:
    @staticmethod
    def get_profile(db: Session, user_id: uuid.UUID) -> UserProfileResponse:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise NotFoundException("User not found.")
        
        return UserProfileResponse(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            username=user.username,
            avatar_url=user.avatar_url,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )

    @staticmethod
    def update_profile(
        db: Session, user_id: uuid.UUID, payload: UserProfileUpdate
    ) -> UserProfileResponse:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise NotFoundException("User not found.")

        # If username is being updated, check uniqueness
        if payload.username is not None:
            clean_username = payload.username.strip() if payload.username.strip() else None
            if clean_username:
                existing = (
                    db.query(User)
                    .filter(User.username == clean_username, User.id != user_id)
                    .first()
                )
                if existing:
                    raise ConflictException("Username is already taken.")
            user.username = clean_username

        if payload.full_name is not None:
            user.full_name = payload.full_name.strip() if payload.full_name.strip() else None

        if payload.avatar_url is not None:
            user.avatar_url = payload.avatar_url.strip() if payload.avatar_url.strip() else None

        # Synchronize Profile table
        profile = db.query(Profile).filter(Profile.id == user_id).first()
        if not profile:
            profile = Profile(
                id=user_id,
                username=user.username,
                full_name=user.full_name,
                avatar_url=user.avatar_url,
            )
            db.add(profile)
        else:
            profile.username = user.username
            profile.full_name = user.full_name
            profile.avatar_url = user.avatar_url

        try:
            db.commit()
            db.refresh(user)
        except Exception as e:
            db.rollback()
            raise DatabaseException("Failed to update profile.") from e

        return UserProfileResponse(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            username=user.username,
            avatar_url=user.avatar_url,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )

    @staticmethod
    def get_preferences(db: Session, user_id: uuid.UUID) -> UserPreferenceResponse:
        pref = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
        fav_ids = pref.favorite_genres if pref and pref.favorite_genres else []
        dis_ids = pref.disliked_genres if pref and pref.disliked_genres else []

        all_ids = list(set(fav_ids + dis_ids))
        genres_by_tmdb = {}
        genres_by_id = {}
        if all_ids:
            found_genres = (
                db.query(Genre)
                .filter(or_(Genre.tmdb_id.in_(all_ids), Genre.id.in_(all_ids)))
                .all()
            )
            for g in found_genres:
                genres_by_tmdb[g.tmdb_id] = g
                genres_by_id[g.id] = g

        def resolve_summaries(genre_ids: list[int]) -> list[GenreSummary]:
            summaries = []
            for gid in genre_ids:
                g = genres_by_tmdb.get(gid) or genres_by_id.get(gid)
                if g:
                    summaries.append(GenreSummary(id=g.id, tmdb_id=g.tmdb_id, name=g.name))
            return summaries

        return UserPreferenceResponse(
            user_id=str(user_id),
            favorite_genres=fav_ids,
            disliked_genres=dis_ids,
            favorite_genre_details=resolve_summaries(fav_ids),
            disliked_genre_details=resolve_summaries(dis_ids),
        )

    @staticmethod
    def update_preferences(
        db: Session, user_id: uuid.UUID, payload: UserPreferenceUpdate
    ) -> UserPreferenceResponse:
        all_requested_ids = list(set(payload.favorite_genres + payload.disliked_genres))
        
        # Validate that all requested genre IDs exist in genres table
        if all_requested_ids:
            existing_genres = (
                db.query(Genre)
                .filter(or_(Genre.tmdb_id.in_(all_requested_ids), Genre.id.in_(all_requested_ids)))
                .all()
            )
            valid_ids = set()
            for g in existing_genres:
                valid_ids.add(g.tmdb_id)
                valid_ids.add(g.id)
            
            invalid_ids = [gid for gid in all_requested_ids if gid not in valid_ids]
            if invalid_ids:
                raise ValidationException(
                    message=f"Invalid genre IDs in preferences: {invalid_ids}. Genres must exist in taxonomy.",
                    code="VALIDATION_ERROR",
                )

        pref = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
        if not pref:
            pref = UserPreference(
                user_id=user_id,
                favorite_genres=payload.favorite_genres,
                disliked_genres=payload.disliked_genres,
            )
            db.add(pref)
        else:
            pref.favorite_genres = payload.favorite_genres
            pref.disliked_genres = payload.disliked_genres

        try:
            db.commit()
            db.refresh(pref)
        except Exception as e:
            db.rollback()
            raise DatabaseException("Failed to update user preferences.") from e

        return UserService.get_preferences(db, user_id)
