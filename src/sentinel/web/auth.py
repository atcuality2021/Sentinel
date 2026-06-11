"""Lightweight session-based auth for Sentinel.

scrypt password hash (stdlib) · signed session token in httponly cookie ·
SQLite-persisted sessions (survive server restarts) ·
in-memory rate limiter (10 attempts / 5 min per IP). No external deps.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import time
from pathlib import Path

SESSION_TTL = 12 * 3600  # 12 hours

# ------------------------------------------------------------------- rate limit --
_rate: dict[str, list[float]] = {}  # ip → [attempt_timestamps]
MAX_ATTEMPTS = 10
WINDOW = 300  # 5 minutes


# ------------------------------------------------------------------ DB helpers --

def _db_path() -> Path:
    return Path(os.getenv("SENTINEL_DATA_DIR", "data")) / "sentinel.db"


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(_db_path(), check_same_thread=False)
    con.execute(
        "CREATE TABLE IF NOT EXISTS sessions "
        "(token TEXT PRIMARY KEY, expires_at REAL NOT NULL)"
    )
    con.commit()
    return con


# ------------------------------------------------------------------ sessions --

def create_session() -> str:
    token = secrets.token_urlsafe(32)
    exp = time.time() + SESSION_TTL
    with _conn() as con:
        con.execute(
            "INSERT OR REPLACE INTO sessions (token, expires_at) VALUES (?, ?)",
            (token, exp),
        )
    return token


def is_valid_session(token: str | None) -> bool:
    if not token:
        return False
    now = time.time()
    with _conn() as con:
        row = con.execute(
            "SELECT expires_at FROM sessions WHERE token = ?", (token,)
        ).fetchone()
    if row is None or now > row[0]:
        delete_session(token)
        return False
    return True


def delete_session(token: str | None) -> None:
    if not token:
        return
    with _conn() as con:
        con.execute("DELETE FROM sessions WHERE token = ?", (token,))


def clear_all_sessions() -> None:
    with _conn() as con:
        con.execute("DELETE FROM sessions")


def _purge_expired() -> None:
    """Remove expired rows — called lazily; no background thread needed."""
    with _conn() as con:
        con.execute("DELETE FROM sessions WHERE expires_at < ?", (time.time(),))


# ------------------------------------------------------------------ password --

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


# ------------------------------------------------------------------ rate limit --

def check_rate_limit(ip: str) -> bool:
    """Return True (allowed) or False (too many attempts)."""
    now = time.time()
    hits = [t for t in _rate.get(ip, []) if now - t < WINDOW]
    _rate[ip] = hits
    if len(hits) >= MAX_ATTEMPTS:
        return False
    _rate[ip].append(now)
    return True
