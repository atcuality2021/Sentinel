"""Lightweight session-based auth for Sentinel.

scrypt password hash (stdlib) · signed session token in httponly cookie ·
in-memory rate limiter (10 attempts / 5 min per IP). No external deps.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import time

# ------------------------------------------------------------------ sessions --
_sessions: dict[str, float] = {}  # token → expiry (unix timestamp)
SESSION_TTL = 12 * 3600            # 12 hours

# ------------------------------------------------------------------- rate limit --
_rate: dict[str, list[float]] = {}  # ip → [attempt_timestamps]
MAX_ATTEMPTS = 10
WINDOW = 300  # 5 minutes


def hash_password(password: str) -> str:
    """Return a 'scrypt$<salt_hex>$<key_hex>' string."""
    salt = os.urandom(16)
    key = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${key.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time verify. Returns False on any error."""
    try:
        _, salt_hex, key_hex = stored.split("$")
        key = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=16384, r=8, p=1, dklen=32,
        )
        return secrets.compare_digest(key.hex(), key_hex)
    except Exception:
        return False


def create_session() -> str:
    token = secrets.token_urlsafe(32)
    _sessions[token] = time.time() + SESSION_TTL
    return token


def is_valid_session(token: str | None) -> bool:
    if not token:
        return False
    exp = _sessions.get(token)
    if exp is None or time.time() > exp:
        _sessions.pop(token, None)
        return False
    return True


def delete_session(token: str | None) -> None:
    if token:
        _sessions.pop(token, None)


def clear_all_sessions() -> None:
    _sessions.clear()


def check_rate_limit(ip: str) -> bool:
    """Return True (allowed) or False (too many attempts)."""
    now = time.time()
    hits = [t for t in _rate.get(ip, []) if now - t < WINDOW]
    _rate[ip] = hits
    if len(hits) >= MAX_ATTEMPTS:
        return False
    _rate[ip].append(now)
    return True
