import logging

import jwt

from app.security import decode_token

logger = logging.getLogger("mqtt_auth")

_OK = {"result": "ok"}


def _deny(reason: str) -> dict:
    logger.info("MQTT auth deny: %s", reason)
    return {"result": {"error": reason}}


def _claims_from_password(password: str | None) -> dict | None:
    if not password:
        return None
    try:
        return decode_token(password)
    except jwt.PyJWTError:
        return None


def _user_topic_allowed(sub: str, topic: str) -> bool:
    """A user may only touch users/{sub}/ ... (their own subtree)."""
    return topic == f"users/{sub}" or topic.startswith(f"users/{sub}/")


async def on_register(body: dict) -> dict:
    """Validate the token; username must match the token subject."""
    username = body.get("username")
    claims = _claims_from_password(body.get("password"))
    if claims is None:
        return _deny("invalid or missing token")

    # Service account: allow (used by backend/worker publisher).
    if claims.get("type") == "service":
        return _OK

    if claims.get("type") not in ("mqtt", "access"):
        return _deny("wrong token type")
    if username and username != claims.get("sub"):
        return _deny("username does not match token subject")
    return _OK


async def on_subscribe(body: dict) -> dict:
    """Allow only subscriptions to the caller's own topics."""
    claims = _claims_from_password(body.get("password"))
    # NOTE: subscribe payload may not carry the password; fall back to username.
    sub = (claims or {}).get("sub") or body.get("username")
    role = (claims or {}).get("role")

    if role == "service":
        return _OK  # service can read anything (rarely used)

    topics = body.get("topics", [])
    for t in topics:
        topic = t.get("topic", "")
        if not _user_topic_allowed(sub, topic):
            return _deny(f"not allowed to subscribe to {topic}")
    return _OK


async def on_publish(body: dict) -> dict:
    """Only the service account may publish; users may not publish to topics."""
    username = body.get("username")
    topic = body.get("topic", "")
    # The service account (backend/worker) publishes user notifications.
    if username == "service":
        return _OK
    # A regular user could be allowed to publish to their own topic if needed;
    # by default we deny user publishes (clients only subscribe).
    return _deny(f"user '{username}' may not publish to {topic}")
