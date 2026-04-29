import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from . import db, redis_client
from .config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

REFRESH_PREFIX = "refresh:"
DENYLIST_PREFIX = "denylist:"
ACCESS_TYPE = "access"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def issue_access(username: str, role: str) -> tuple[str, str, int]:
    now = datetime.now(timezone.utc)
    jti = uuid.uuid4().hex
    exp = int((now + timedelta(minutes=settings.jwt_expires_min)).timestamp())
    payload = {
        "sub": username,
        "role": role,
        "type": ACCESS_TYPE,
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": exp,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256"), jti, exp


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {exc}")


async def issue_refresh(username: str, role: str) -> str:
    token = secrets.token_urlsafe(48)
    ttl = settings.jwt_refresh_days * 86400
    await redis_client.redis().setex(
        f"{REFRESH_PREFIX}{token}",
        ttl,
        f"{username}|{role}",
    )
    return token


async def consume_refresh(token: str) -> tuple[str, str] | None:
    val = await redis_client.redis().get(f"{REFRESH_PREFIX}{token}")
    if val is None:
        return None
    username, role = val.split("|", 1)
    return username, role


async def revoke_refresh(token: str) -> None:
    await redis_client.redis().delete(f"{REFRESH_PREFIX}{token}")


async def revoke_access(jti: str, exp_unix: int) -> None:
    now = int(datetime.now(timezone.utc).timestamp())
    ttl = max(exp_unix - now, 1)
    await redis_client.redis().setex(f"{DENYLIST_PREFIX}{jti}", ttl, "1")


async def current_user(token: str | None = Depends(oauth2_scheme)) -> dict:
    if token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing token")
    payload = decode_token(token)
    if payload.get("type") not in (None, ACCESS_TYPE):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong token type")
    jti = payload.get("jti")
    if jti and await redis_client.redis().exists(f"{DENYLIST_PREFIX}{jti}"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token revoked")
    return payload


async def ensure_admin_seed() -> None:
    async with db.pool().acquire() as conn:
        row = await conn.fetchval("SELECT 1 FROM users WHERE username = $1", settings.admin_username)
        if row is None:
            await conn.execute(
                "INSERT INTO users(username, password_hash, role) VALUES ($1, $2, 'admin')",
                settings.admin_username,
                hash_password(settings.admin_password),
            )
