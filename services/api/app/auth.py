from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from .config import settings
from . import db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def issue_token(username: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_expires_min)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {exc}")


async def current_user(token: str | None = Depends(oauth2_scheme)) -> dict:
    if token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing token")
    return decode_token(token)


async def ensure_admin_seed() -> None:
    async with db.pool().acquire() as conn:
        row = await conn.fetchval("SELECT 1 FROM users WHERE username = $1", settings.admin_username)
        if row is None:
            await conn.execute(
                "INSERT INTO users(username, password_hash, role) VALUES ($1, $2, 'admin')",
                settings.admin_username,
                hash_password(settings.admin_password),
            )
