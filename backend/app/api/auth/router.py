from datetime import timedelta
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pwdlib import PasswordHash
from pydantic import EmailStr

from app.database.session import get_db
from app.database.models.user import User
from app.core.security import create_access_token, get_current_user
from app.api.auth.schemas import (
    UserRegister,
    UserLogin,
    Token,
    UserResponse,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# Password hashing


password_hash = PasswordHash.recommended()

def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    return password_hash.hash(password)

def verify_password(password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return password_hash.verify(password, hashed_password)


@router.post("/register", response_model=Token)
async def register(
    payload: UserRegister,
    db: Session = Depends(get_db),
):
    """Register a new user"""
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == payload.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    
    # Create new user
    user = User(
        id=uuid.uuid4(),
        email=payload.email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        is_active=True,
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Create access token
    access_token = create_access_token(user.id)
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
    }


@router.post("/login", response_model=Token)
async def login(
    payload: UserLogin,
    db: Session = Depends(get_db),
):
    """Login with email and password"""
    user = db.query(User).filter(User.email == payload.email).first()
    
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )
    
    access_token = create_access_token(user.id)
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
    }


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
):
    """Get current authenticated user information"""
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        full_name=current_user.full_name,
    )


@router.post("/logout")
async def logout():
    """Logout endpoint - token is invalidated by the client"""
    return {"message": "Successfully logged out"}


@router.get("/health")
async def auth_health():
    """Health check for auth service"""
    return {"message": "Authentication service is running"}
