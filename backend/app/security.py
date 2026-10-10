"""Authentication (OAuth2 password flow -> signed JWT bearer token) and role-based authorization.

Passwords are stored as bcrypt hashes. Tokens are HS256 JWTs carrying the user id, role and company id,
and expire after JWT_TTL_MIN minutes. Every protected route re-loads the user from the database, so a
deactivated user loses access immediately. Repeated failed logins for one email are throttled.
"""
from __future__ import annotations

import time
from collections import deque
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from . import config
from .db import get_db
from .models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")
_ALGO = "HS256"
_FAILS: dict[str, deque] = {}  # email -> recent failure times (entries removed once they expire)
MAX_FAILS, WINDOW_S = 5, 300


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=10)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def check_throttle(email: str) -> None:
    q = _FAILS.get(email.lower())
    if q is None:
        return
    while q and time.time() - q[0] > WINDOW_S:
        q.popleft()
    if not q:
        _FAILS.pop(email.lower(), None)
    elif len(q) >= MAX_FAILS:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many failed attempts. Try again in a few minutes.")


def record_failure(email: str) -> None:
    _FAILS.setdefault(email.lower(), deque()).append(time.time())


def clear_failures(email: str) -> None:
    _FAILS.pop(email.lower(), None)


def create_token(user: User) -> tuple[str, int]:
    now = datetime.now(timezone.utc)  # aware: .timestamp() of a naive time would use the server's local zone
    exp = now + timedelta(minutes=config.JWT_TTL_MIN)
    payload = {"sub": str(user.id), "role": user.role, "cid": user.company_id,
               "iat": int(now.timestamp()), "exp": int(exp.timestamp())}
    return jwt.encode(payload, config.JWT_SECRET, algorithm=_ALGO), config.JWT_TTL_MIN * 60


def _unauthorized(detail: str = "Not signed in") -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"})


def current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[_ALGO])
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Session expired, please sign in again")
    except jwt.PyJWTError:
        raise _unauthorized("Invalid session")
    user = db.get(User, int(payload.get("sub", 0)))
    if user is None or not user.is_active:
        raise _unauthorized("Account not found or disabled")
    return user


def require_finance(user: User = Depends(current_user)) -> User:
    if user.role != "finance":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Finance role required")
    return user
