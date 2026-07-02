from datetime import datetime, timedelta, timezone
import jwt
from passlib.context import CryptContext
from app.config import settings

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return _pwd.hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    return _pwd.verify(password, password_hash)

def _create_token(sub: str, token_type: str, expires: timedelta, **extra) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,                 # the user id
        "type": token_type,         # "access" or "refresh"
        "iat": now,
        "exp": now + expires,
        **extra,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)

def create_access_token(sub: str, role: str = "user") -> str:
    return _create_token(
        sub, "access",
        timedelta(minutes=settings.ACCESS_TOKEN_MINUTES),
        role=role,
    )

def create_refresh_token(sub: str) -> str:
    return _create_token(
        sub, "refresh",
        timedelta(days=settings.REFRESH_TOKEN_DAYS),
    )

def create_mqtt_token(sub: str) -> str:

    return _create_token(
        sub, "mqtt",
        timedelta(minutes=settings.ACCESS_TOKEN_MINUTES * 30),  
    )

def create_service_token() -> str:

    return _create_token("service", "service", timedelta(days=365), role="service")


def decode_token(token: str) -> dict:

    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
