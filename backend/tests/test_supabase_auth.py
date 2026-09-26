"""Unit tests for the production Supabase Auth path.

Covers token validation (valid / invalid signature / expired / wrong audience /
missing subject / malformed) and the identity mapping that provisions a single
WatchMan user record from verified Supabase claims.

Tokens are HS256 and signed with the same shared secret the app validates
against (`settings.SUPABASE_JWT_SECRET`), so these tests need no network access
and no real Supabase project — matching the shared-secret production path.
"""

import time
import uuid

import pytest
from jose import jwt

from app.core.config import settings
from app.core.exceptions import AuthenticationException, AuthorizationException
from app.core.supabase_auth import verify_supabase_token, resolve_user_from_claims
from app.models.user import User


def _make_token(claims: dict, secret: str | None = None, alg: str = "HS256") -> str:
    return jwt.encode(claims, secret or settings.SUPABASE_JWT_SECRET, algorithm=alg)


def _base_claims(**overrides) -> dict:
    now = int(time.time())
    claims = {
        "sub": str(uuid.uuid4()),
        "aud": settings.SUPABASE_JWT_AUD,
        "email": "person@example.com",
        "exp": now + 3600,
        "iat": now,
    }
    claims.update(overrides)
    return claims


# --------------------------------------------------------------------------- #
# verify_supabase_token
# --------------------------------------------------------------------------- #

def test_valid_token_returns_claims():
    sub = str(uuid.uuid4())
    token = _make_token(_base_claims(sub=sub))
    claims = verify_supabase_token(token)
    assert claims["sub"] == sub
    assert claims["email"] == "person@example.com"


def test_invalid_signature_rejected():
    token = _make_token(_base_claims(), secret="a_completely_different_secret_value_1234567890")
    with pytest.raises(AuthenticationException):
        verify_supabase_token(token)


def test_expired_token_rejected():
    token = _make_token(_base_claims(exp=int(time.time()) - 10))
    with pytest.raises(AuthenticationException):
        verify_supabase_token(token)


def test_wrong_audience_rejected():
    token = _make_token(_base_claims(aud="some-other-audience"))
    with pytest.raises(AuthenticationException):
        verify_supabase_token(token)


def test_missing_subject_rejected():
    claims = _base_claims()
    claims.pop("sub")
    token = _make_token(claims)
    with pytest.raises(AuthenticationException):
        verify_supabase_token(token)


def test_malformed_token_rejected():
    with pytest.raises(AuthenticationException):
        verify_supabase_token("not-a-jwt")


def test_empty_token_rejected():
    with pytest.raises(AuthenticationException):
        verify_supabase_token("")


def test_unsigned_none_alg_rejected():
    """A token advertising alg=none must never be trusted."""
    import base64
    import json
    h = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).decode().rstrip("=")
    p = base64.urlsafe_b64encode(json.dumps(_base_claims()).encode()).decode().rstrip("=")
    token = f"{h}.{p}."
    with pytest.raises(AuthenticationException):
        verify_supabase_token(token)


# --------------------------------------------------------------------------- #
# resolve_user_from_claims (identity mapping / JIT provisioning)
# --------------------------------------------------------------------------- #

def test_jit_provisions_single_identity(db_session):
    sub = str(uuid.uuid4())
    claims = _base_claims(sub=sub, email="new@example.com",
                          user_metadata={"full_name": "New Person", "username": "newp"})
    user = resolve_user_from_claims(db_session, claims)

    assert str(user.id) == sub          # Supabase sub IS the WatchMan user id
    assert user.email == "new@example.com"
    assert user.password_hash is None   # no local password on the Supabase path
    assert user.is_active is True


def test_resolve_is_idempotent(db_session):
    sub = str(uuid.uuid4())
    claims = _base_claims(sub=sub)
    first = resolve_user_from_claims(db_session, claims)
    second = resolve_user_from_claims(db_session, claims)
    assert first.id == second.id
    assert db_session.query(User).filter(User.id == first.id).count() == 1


def test_inactive_user_forbidden(db_session):
    sub = uuid.uuid4()
    db_session.add(User(id=sub, email="inactive@example.com", password_hash=None, is_active=False))
    db_session.commit()
    with pytest.raises(AuthorizationException):
        resolve_user_from_claims(db_session, _base_claims(sub=str(sub)))


def test_invalid_subject_uuid_rejected(db_session):
    with pytest.raises(AuthenticationException):
        resolve_user_from_claims(db_session, {"sub": "not-a-uuid"})


# --------------------------------------------------------------------------- #
# get_current_user dispatch (supabase mode) — authenticated / invalid /
# unauthenticated request paths, exercised without a live HTTP server.
# --------------------------------------------------------------------------- #

import asyncio
from types import SimpleNamespace

from app.core import security as security_mod


def _run_get_current_user(credentials, db):
    return asyncio.run(security_mod.get_current_user(credentials=credentials, db=db))


def test_dispatch_authenticated_supabase_request(db_session, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_PROVIDER", "supabase")
    sub = str(uuid.uuid4())
    token = _make_token(_base_claims(sub=sub, email="auth@example.com"))
    creds = SimpleNamespace(credentials=token)

    user = _run_get_current_user(creds, db_session)
    assert str(user.id) == sub
    assert user.email == "auth@example.com"


def test_dispatch_invalid_token_supabase(db_session, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_PROVIDER", "supabase")
    creds = SimpleNamespace(credentials="garbage.token.value")
    with pytest.raises(AuthenticationException):
        _run_get_current_user(creds, db_session)


def test_dispatch_unauthenticated_request(db_session, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_PROVIDER", "supabase")
    with pytest.raises(AuthenticationException):
        _run_get_current_user(None, db_session)
