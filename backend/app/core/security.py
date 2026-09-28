from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid

from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AuthenticationException, AuthorizationException
from app.db.session import get_db
from app.models.user import User

security = HTTPBearer(auto_error=False)


def create_access_token(user_id: uuid.UUID | str, expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT access token."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    
    uid_str = str(user_id)
    to_encode = {
        "sub": uid_str,
        "user_id": uid_str,
        "type": "access",
        "iat": now,
        "jti": str(uuid.uuid4()),
        "exp": expire,
    }
    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    return encoded_jwt


def create_refresh_token(user_id: uuid.UUID | str, expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT refresh token."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )
    
    uid_str = str(user_id)
    to_encode = {
        "sub": uid_str,
        "user_id": uid_str,
        "type": "refresh",
        "iat": now,
        "jti": str(uuid.uuid4()),
        "exp": expire,
    }
    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    return encoded_jwt


def decode_token(token: str) -> dict:
    """Decode and validate signature and expiry of a JWT token."""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        return payload
    except JWTError:
        raise AuthenticationException(
            message="Invalid or expired authentication token.",
            code="UNAUTHORIZED",
        )


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """
    Resolve the current authenticated user from the bearer token.

    The verification strategy is selected by ``settings.AUTH_PROVIDER``:

    * ``"supabase"`` (production) — the token is a Supabase Auth access token,
      validated in :mod:`app.core.supabase_auth` and mapped to a WatchMan user
      by its ``sub`` UUID. No local JWT/bcrypt is involved.
    * ``"local"`` (development) — the legacy local HS256 JWT minted by this
      service is decoded and validated below.

    There is no fallback between the two: a production deployment configured for
    Supabase never accepts a locally minted token, and vice-versa.
    """
    if not credentials or not credentials.credentials:
        raise AuthenticationException(
            message="Authentication credentials were not provided.",
            code="UNAUTHORIZED",
        )

    token = credentials.credentials

    if settings.AUTH_PROVIDER == "supabase":
        # Production path: validate the Supabase access token and map identity.
        from app.core.supabase_auth import verify_supabase_token, resolve_user_from_claims

        claims = verify_supabase_token(token)
        return resolve_user_from_claims(db, claims)

    # Local development path: this service's own JWT.
    payload = decode_token(token)

    token_type = payload.get("type", "access")
    if token_type != "access":
        raise AuthenticationException(
            message="Invalid token type. Access token required.",
            code="UNAUTHORIZED",
        )

    user_id = payload.get("sub") or payload.get("user_id")
    if not user_id:
        raise AuthenticationException(
            message="Invalid authentication token payload.",
            code="UNAUTHORIZED",
        )

    try:
        user_uuid = uuid.UUID(str(user_id))
    except (ValueError, TypeError):
        raise AuthenticationException(
            message="Invalid user identifier in token.",
            code="UNAUTHORIZED",
        )

    user = db.query(User).filter(User.id == user_uuid).first()
    if user is None:
        raise AuthenticationException(
            message="User associated with token was not found.",
            code="UNAUTHORIZED",
        )

    if not user.is_active:
        raise AuthorizationException(
            message="User account is inactive.",
            code="FORBIDDEN",
        )

    return user


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Resolve user if bearer token is provided and valid, otherwise return None."""
    if not credentials or not credentials.credentials:
        return None
    try:
        return await get_current_user(credentials=credentials, db=db)
    except Exception:
        return None


def require_resource_owner(resource_user_id: uuid.UUID | str, current_user_id: uuid.UUID | str) -> None:
    """Validate that the authenticated user owns the target resource."""
    if str(resource_user_id) != str(current_user_id):
        raise AuthorizationException(
            message="You do not have permission to access or modify this resource.",
            code="FORBIDDEN",
        )


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """
    Restrict operational / diagnostic endpoints to configured operators.

    Reuses the ``ML_ADMIN_EMAILS`` allowlist (the same set trusted to run
    expensive ML jobs) as the operator/admin allowlist for operational
    telemetry (``/ops``). The caller must
    first authenticate via :func:`get_current_user`; anonymous callers are
    rejected there with 401 before this check runs.
    """
    if current_user.email.lower() not in settings.ml_admin_emails:
        raise AuthorizationException(
            message="Operator (admin) access is required for this endpoint.",
            code="FORBIDDEN",
        )
    return current_user
