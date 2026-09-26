"""
Supabase Auth token validation — the production authentication path.

The browser authenticates directly against Supabase Auth and receives a Supabase
access token (a JWT). That token is sent to FastAPI as `Authorization: Bearer
<token>`. This module validates the token *locally* (no per-request network call
for the common HS256 case) and resolves it to a WatchMan user record.

Identity mapping (single identity system):

    supabase auth.users.id (JWT `sub`, a UUID)  ==  watchman users.id (PK, UUID)

On the first authenticated request for a given Supabase user we just-in-time
provision a matching WatchMan `users` / `profiles` / `user_preferences` row keyed
by that same UUID. No local password is ever stored on this path.

Two verification strategies are supported:

* Symmetric (HS256/384/512) — verified with `SUPABASE_JWT_SECRET`. This is the
  default for Supabase's shared "JWT secret" and needs no network access, so it
  is what the unit tests exercise.
* Asymmetric (RS*/ES*/EdDSA) — verified against the project JWKS
  (`<SUPABASE_URL>/auth/v1/.well-known/jwks.json`), fetched once and cached in
  process. Used when a project has migrated to signing keys.

Never accept an unsigned token, and never fall back to trusting the token
without a verified signature.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import httpx
from jose import jwt
from jose.exceptions import JWTError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AuthenticationException, AuthorizationException
from app.models.user import User, Profile, UserPreference


# --------------------------------------------------------------------------- #
# JWKS cache (asymmetric keys only)
# --------------------------------------------------------------------------- #

_JWKS_CACHE: dict[str, Any] = {"fetched_at": 0.0, "keys": None}
_JWKS_TTL_SECONDS = 3600


def _jwks_url() -> str:
    base = (settings.SUPABASE_URL or "").rstrip("/")
    return f"{base}/auth/v1/.well-known/jwks.json"


def _get_jwks(force: bool = False) -> list[dict]:
    now = time.time()
    if (
        not force
        and _JWKS_CACHE["keys"] is not None
        and (now - _JWKS_CACHE["fetched_at"]) < _JWKS_TTL_SECONDS
    ):
        return _JWKS_CACHE["keys"]
    try:
        resp = httpx.get(_jwks_url(), timeout=5.0)
        resp.raise_for_status()
        keys = resp.json().get("keys", [])
    except Exception as exc:  # noqa: BLE001
        raise AuthenticationException(
            message="Unable to retrieve Supabase signing keys to validate token.",
            code="UNAUTHORIZED",
        ) from exc
    _JWKS_CACHE["keys"] = keys
    _JWKS_CACHE["fetched_at"] = now
    return keys


def _key_for_kid(kid: str | None) -> dict:
    keys = _get_jwks()
    for key in keys:
        if key.get("kid") == kid:
            return key
    # Key may have rotated — refetch once.
    for key in _get_jwks(force=True):
        if key.get("kid") == kid:
            return key
    raise AuthenticationException(
        message="Token signing key not recognized.",
        code="UNAUTHORIZED",
    )


# --------------------------------------------------------------------------- #
# Token verification
# --------------------------------------------------------------------------- #

def verify_supabase_token(token: str) -> dict:
    """
    Verify a Supabase access token's signature, expiry and audience.

    Returns the decoded claims on success; raises AuthenticationException on any
    validation failure. Performs NO trust-without-verification fallback.
    """
    if not token or not isinstance(token, str):
        raise AuthenticationException(
            message="Authentication credentials were not provided.",
            code="UNAUTHORIZED",
        )

    try:
        header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise AuthenticationException(
            message="Malformed authentication token.", code="UNAUTHORIZED"
        ) from exc

    alg = (header.get("alg") or "").upper()
    audience = settings.SUPABASE_JWT_AUD
    options = {"verify_aud": bool(audience)}

    try:
        if alg.startswith("HS"):
            secret = settings.SUPABASE_JWT_SECRET
            if not secret:
                raise AuthenticationException(
                    message="Server is not configured to validate Supabase tokens.",
                    code="UNAUTHORIZED",
                )
            claims = jwt.decode(
                token,
                secret,
                algorithms=[alg],
                audience=audience or None,
                options=options,
            )
        elif alg in ("RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "EDDSA"):
            key = _key_for_kid(header.get("kid"))
            claims = jwt.decode(
                token,
                key,
                algorithms=[alg],
                audience=audience or None,
                options=options,
            )
        else:
            raise AuthenticationException(
                message=f"Unsupported token algorithm '{alg}'.",
                code="UNAUTHORIZED",
            )
    except AuthenticationException:
        raise
    except JWTError as exc:
        raise AuthenticationException(
            message="Invalid or expired authentication token.",
            code="UNAUTHORIZED",
        ) from exc

    if not claims.get("sub"):
        raise AuthenticationException(
            message="Authentication token is missing a subject (user id).",
            code="UNAUTHORIZED",
        )
    return claims


# --------------------------------------------------------------------------- #
# Identity mapping: Supabase auth.users.id -> WatchMan user
# --------------------------------------------------------------------------- #

def resolve_user_from_claims(db: Session, claims: dict) -> User:
    """
    Map verified Supabase claims to a WatchMan user, provisioning one on first
    sight. The Supabase `sub` UUID is used directly as the WatchMan users.id, so
    exactly one identity exists per authenticated principal.
    """
    sub = claims.get("sub")
    try:
        user_uuid = uuid.UUID(str(sub))
    except (ValueError, TypeError) as exc:
        raise AuthenticationException(
            message="Invalid user identifier in token.", code="UNAUTHORIZED"
        ) from exc

    user = db.query(User).filter(User.id == user_uuid).first()
    if user is not None:
        if not user.is_active:
            raise AuthorizationException(
                message="User account is inactive.", code="FORBIDDEN"
            )
        return user

    # Just-in-time provisioning of the local mirror record.
    email = (claims.get("email") or "").strip().lower() or None
    metadata = claims.get("user_metadata") or {}
    full_name = metadata.get("full_name") or metadata.get("name")
    username = metadata.get("username")

    user = User(
        id=user_uuid,
        email=email or f"{user_uuid}@users.noreply.supabase",
        username=username,
        full_name=full_name,
        password_hash=None,  # No local password on the Supabase path.
        is_active=True,
    )
    profile = Profile(id=user_uuid, username=username, full_name=full_name)
    preference = UserPreference(user_id=user_uuid, favorite_genres=[], disliked_genres=[])

    db.add(user)
    db.add(profile)
    db.add(preference)
    try:
        db.commit()
    except Exception:  # noqa: BLE001
        # Concurrent provisioning — fall back to the row the other request wrote.
        db.rollback()
        user = db.query(User).filter(User.id == user_uuid).first()
        if user is None:
            raise
        return user

    db.refresh(user)
    return user
