import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.config import get_settings

ALGORITHM = "HS256"
ISSUER = "aegisrmf"


def create_access_token(user_id: uuid.UUID, provider: str, sid: uuid.UUID | None = None, operator_id: uuid.UUID | None = None) -> tuple[str, int]:
    s = get_settings()
    ttl = s.jwt_ttl_minutes * 60
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iss": ISSUER,
        "iat": now,
        "exp": now + timedelta(seconds=ttl),
        "jti": str(uuid.uuid4()),
        "amr": [provider],
        "type": "access",
    }
    if sid:
        payload["sid"] = str(sid)
    if operator_id:
        payload["op"] = str(operator_id)
    return jwt.encode(payload, s.jwt_secret, algorithm=ALGORITHM), ttl


def decode_access_token(token: str) -> dict:
    payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[ALGORITHM], issuer=ISSUER)
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Invalid token type")
    return payload
