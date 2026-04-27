import re

from fastapi import APIRouter, Body, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from .. import auth, db

router = APIRouter(prefix="/api/auth", tags=["auth"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PROFILE_FIELDS = ("first_name", "last_name", "email")


def _profile_dict(row) -> dict:
    return {
        "username": row["username"],
        "role": row["role"],
        "first_name": row["first_name"],
        "last_name": row["last_name"],
        "email": row["email"],
    }


@router.post("/login")
async def login(form: OAuth2PasswordRequestForm = Depends()) -> dict:
    async with db.pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT username, password_hash, role FROM users WHERE username = $1",
            form.username,
        )
    if row is None or not auth.verify_password(form.password, row["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    token = auth.issue_token(row["username"], row["role"])
    return {"access_token": token, "token_type": "bearer", "role": row["role"]}


@router.get("/me")
async def me(user: dict = Depends(auth.current_user)) -> dict:
    async with db.pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT username, role, first_name, last_name, email FROM users WHERE username = $1",
            user["sub"],
        )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    return _profile_dict(row)


@router.patch("/me")
async def update_me(
    payload: dict = Body(...),
    user: dict = Depends(auth.current_user),
) -> dict:
    updates: dict = {}
    for k in PROFILE_FIELDS:
        if k in payload:
            v = payload[k]
            v = v.strip() if isinstance(v, str) else v
            updates[k] = v or None

    if "email" in updates and updates["email"] is not None and not EMAIL_RE.match(updates["email"]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid email")

    if not updates:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no fields to update")

    set_sql = ", ".join(f"{k} = ${i + 1}" for i, k in enumerate(updates))
    args = list(updates.values()) + [user["sub"]]
    async with db.pool().acquire() as conn:
        row = await conn.fetchrow(
            f"UPDATE users SET {set_sql}, updated_at = NOW() WHERE username = ${len(updates) + 1} "
            f"RETURNING username, role, first_name, last_name, email",
            *args,
        )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    return _profile_dict(row)
