from fastapi import Header, HTTPException, status
from app.config import settings

async def require_api_key(x_api_key: str | None = Header(default=None)):
    if x_api_key != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key (send header 'X-API-Key').",
        )