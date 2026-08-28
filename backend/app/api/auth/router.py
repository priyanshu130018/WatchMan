from fastapi import APIRouter

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.get("/health")
async def auth_health():
    return {
        "message": "Supabase authentication is configured."
    }