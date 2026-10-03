import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

try:
    import bcrypt
    def hash_password(password: str) -> str:
        """Hash a password securely using bcrypt."""
        pwd_bytes = password.encode("utf-8")[:72]
        return bcrypt.hashpw(pwd_bytes, bcrypt.gensalt()).decode("utf-8")

    def verify_password(password: str, hashed_password: str) -> bool:
        """Verify a password against its bcrypt hash."""
        pwd_bytes = password.encode("utf-8")[:72]
        hashed_bytes = hashed_password.encode("utf-8")
        try:
            return bcrypt.checkpw(pwd_bytes, hashed_bytes)
        except Exception:
            return False
except ImportError:
    try:
        from pwdlib import PasswordHash
        password_hash = PasswordHash.recommended()
        def hash_password(password: str) -> str:
            return password_hash.hash(password)
        def verify_password(password: str, hashed_password: str) -> bool:
            return password_hash.verify(password, hashed_password)
    except ImportError:
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        def hash_password(password: str) -> str:
            return pwd_context.hash(password)
        def verify_password(password: str, hashed_password: str) -> bool:
            return pwd_context.verify(password, hashed_password)

from app.db.session import get_db
from app.models.user import User, Profile, UserPreference
from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
)
from app.core.exceptions import (
    AuthenticationException,
    AuthorizationException,
    ConflictException,
    DatabaseException,
    UserAlreadyExistsException,
)
from app.api.auth.schemas import (
    UserRegister,
    UserLogin,
    RefreshTokenRequest,
    Token,
    UserResponse,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/register", response_model=Token)
async def register(
    payload: UserRegister,
    db: Session = Depends(get_db),
):
    """Register a new user account and initialize profile/preferences."""
    email = payload.email.strip().lower()
    
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise UserAlreadyExistsException("Email already registered.")
    
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=email,
        username=payload.username.strip() if payload.username else None,
        full_name=payload.full_name.strip() if payload.full_name else None,
        password_hash=hash_password(payload.password),
        is_active=True,
    )
    profile = Profile(
        id=user_id,
        username=user.username,
        full_name=user.full_name,
    )
    preference = UserPreference(
        user_id=user_id,
        favorite_genres=[],
        disliked_genres=[],
    )
    
    try:
        db.add(user)
        db.add(profile)
        db.add(preference)
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise ConflictException("A user with this email or username already exists.") from e
    except Exception as e:
        db.rollback()
        raise DatabaseException("Failed to register user account.") from e

    db.refresh(user)
    
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    
    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        user=UserResponse(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            username=user.username,
            avatar_url=user.avatar_url,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at,
        ),
    )


@router.post("/login", response_model=Token)
async def login(
    payload: UserLogin,
    db: Session = Depends(get_db),
):
    """Authenticate with email and password and issue access and refresh tokens."""
    email = payload.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()

    if not user or not user.password_hash or not verify_password(payload.password, user.password_hash):
        raise AuthenticationException("Invalid email or password.")
    
    if not user.is_active:
        raise AuthorizationException("User account is inactive.")
    
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    
    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        user=UserResponse(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            username=user.username,
            avatar_url=user.avatar_url,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at,
        ),
    )


@router.post("/refresh", response_model=Token)
async def refresh_token(
    payload: RefreshTokenRequest,
    db: Session = Depends(get_db),
):
    """Validate refresh token and issue a fresh access token and rotated refresh token."""
    token_payload = decode_token(payload.refresh_token)
    
    token_type = token_payload.get("type")
    if token_type != "refresh":
        raise AuthenticationException("Invalid token type. Refresh token required.")
    
    user_id_str = token_payload.get("sub") or token_payload.get("user_id")
    if not user_id_str:
        raise AuthenticationException("Invalid token payload.")
    
    try:
        user_uuid = uuid.UUID(str(user_id_str))
    except (ValueError, TypeError):
        raise AuthenticationException("Invalid user identifier in token.")
    
    user = db.query(User).filter(User.id == user_uuid).first()
    if not user:
        raise AuthenticationException("User associated with token not found.")
    
    if not user.is_active:
        raise AuthorizationException("User account is inactive.")
    
    new_access_token = create_access_token(user.id)
    new_refresh_token = create_refresh_token(user.id)
    
    return Token(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        user=UserResponse(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            username=user.username,
            avatar_url=user.avatar_url,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at,
        ),
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
):
    """Get current authenticated user information."""
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        full_name=current_user.full_name,
        username=current_user.username,
        avatar_url=current_user.avatar_url,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
        updated_at=current_user.updated_at,
    )


@router.post("/logout")
async def logout():
    """Stateless logout acknowledgment endpoint."""
    return {"message": "Successfully logged out"}


@router.get("/health")
async def auth_health():
    """Health check for auth service."""
    return {"status": "ok", "service": "Authentication"}
