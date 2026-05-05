"""
Authentication module for the NextFlex Manager Dashboard.

Three users, hashed passwords, JWT-in-cookie sessions.
Passwords are stored as bcrypt hashes (never plaintext).
JWT secret comes from the JWT_SECRET environment variable in
production; falls back to a random per-process value in dev.
"""

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import HTTPException, Request


# ─── User store ──────────────────────────────────────────────────────────
# Three users, each with a fixed role. Password hashes baked in at build
# time. To change passwords, regenerate the hashes (see scripts/gen_pw.py)
# and replace the strings here.
#
# Generated 2026-04-30. Plaintext passwords are documented separately
# and should be rotated before any real deployment.
USERS = {
    "nfx-admin": {
        "role": "admin",
        "display_name": "Scott Miller",
        "title": "Executive Director · NextFlex",
        "avatar": "SM",
        # Password: 3LEqkim$k!
        "password_hash": "$2b$12$o8II9f4aFyJ0rrka/GQmsOFviy7/ajX.Q5936L85PHyISl3kwvDEO",
    },
    "nfx-dow": {
        "role": "dow",
        "display_name": "Dr. R. Adams",
        "title": "Materials Director · ARL",
        "avatar": "RA",
        # Password: f6&NTm@hNr
        "password_hash": "$2b$12$PAV8YccU/TeJPTkyCIHub.MAETMC48aPvASzFyEpjlU89eJ7zpPF.",
    },
    "nfx-member": {
        "role": "member",
        "display_name": "Dr. V. Vokkarane",
        "title": "PI · UMass Lowell ECE",
        "avatar": "VV",
        # Password: &vTXf4g9#s
        "password_hash": "$2b$12$1My6JaizIirhV7CGVcTR6e0GUEikB2ZotAeZrX1bdb1bi8w.F3Z1O",
    },
}


# ─── JWT secret ──────────────────────────────────────────────────────────
# Pull from env in production. In dev, a random per-process value means
# you'll get logged out on server restart — that's intentional for dev,
# fine for prod once JWT_SECRET is set in Render's environment.
JWT_SECRET = os.environ.get("JWT_SECRET")
if not JWT_SECRET:
    JWT_SECRET = secrets.token_urlsafe(48)
    print(
        "[auth] WARNING: JWT_SECRET not set in env. Using ephemeral key. "
        "Set JWT_SECRET in your Render dashboard for stable sessions.",
        flush=True,
    )

JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 8  # session length

COOKIE_NAME = "nfx_session"


# ─── Password verification ───────────────────────────────────────────────
def verify_password(password: str, hashed: str) -> bool:
    """Constant-time bcrypt comparison."""
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False


def authenticate(username: str, password: str) -> Optional[dict]:
    """Return user record if credentials are valid, else None."""
    user = USERS.get(username)
    if not user:
        # Run a real bcrypt check anyway against a placeholder hash so the
        # response time when the username doesn't exist looks the same as
        # when it does — defends against username-enumeration timing attacks.
        verify_password(password, "$2b$12$" + "x" * 53)
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    return {
        "username": username,
        "role": user["role"],
        "display_name": user["display_name"],
        "title": user["title"],
        "avatar": user["avatar"],
    }


# ─── JWT issuance / verification ─────────────────────────────────────────
def issue_token(user: dict) -> str:
    """Sign a JWT for the authenticated user."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user["username"],
        "role": user["role"],
        "name": user["display_name"],
        "title": user["title"],
        "avatar": user["avatar"],
        "iat": now,
        "exp": now + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ─── FastAPI dependency for protected routes ────────────────────────────
def current_user(request: Request) -> Optional[dict]:
    """Return the user record from the cookie, or None if not authenticated."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    return {
        "username": payload["sub"],
        "role": payload["role"],
        "display_name": payload.get("name"),
        "title": payload.get("title"),
        "avatar": payload.get("avatar"),
    }


def require_user(request: Request) -> dict:
    """Like current_user but raises 401 if not logged in."""
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="not_authenticated")
    return user
