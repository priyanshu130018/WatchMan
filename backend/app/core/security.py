from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer

security = HTTPBearer()


async def get_current_user(credentials=Depends(security)):
    return credentials.credentials