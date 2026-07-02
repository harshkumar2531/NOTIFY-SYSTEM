
import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.config import settings
from app.security import decode_token
from app.state import clients

# auto_error=False so a missing token doesn't 403 before we can also check the API key.
_bearer = HTTPBearer(auto_error=False)

# Redis key prefix for revoked (logged-out) refresh tokens.
DENYLIST_PREFIX = "revoked_refresh:"

async def require_api_key(x_api_key: str | None = Header(default=None)):
    if x_api_key != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key (send header 'X-API-Key').",
        )

async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    x_api_key: str | None = Header(default=None),
) -> dict:
    """Resolve the caller from a JWT Bearer token OR the API key."""
    # 1) API key -> service/admin identity (bypasses ownership).
    if x_api_key and x_api_key == settings.API_KEY:
        return {"id": "service", "role": "service"}

    # 2) JWT bearer token.
    if creds is not None:
        try:
            claims = decode_token(creds.credentials)
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.PyJWTError:
            raise HTTPException(status_code=401, detail="Invalid token")

        if claims.get("type") != "access":
            raise HTTPException(status_code=401, detail="Not an access token")

        return {"id": claims["sub"], "role": claims.get("role", "user")}

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated (send a Bearer token or X-API-Key).",
    )


def require_owner_or_admin(user_id: str, current_user: dict) -> None:
    """Raise 403 unless the caller owns this user_id or is admin/service."""
    if current_user["role"] in ("admin", "service"):
        return
    if current_user["id"] != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own data.",
        )


# --------------------- Refresh-token revocation (logout) --------------------

async def revoke_refresh_token(jti_or_token: str) -> None:
    """Add a refresh token to the Redis denylist (expires with the token)."""
    ttl = settings.REFRESH_TOKEN_DAYS * 24 * 3600
    await clients["redis"].set(DENYLIST_PREFIX + jti_or_token, "1", ex=ttl)


async def is_refresh_revoked(jti_or_token: str) -> bool:
    return await clients["redis"].exists(DENYLIST_PREFIX + jti_or_token) == 1
