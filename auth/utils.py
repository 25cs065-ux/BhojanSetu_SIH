"""
auth/utils.py
=============
Authentication helpers for BhojanSetu.

Responsibilities
----------------
- Load / save users.json
- Password hashing (hashlib PBKDF2 — no external dependency)
- OTP generation and verification
- Session helpers
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import random
import string
import time
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent.parent
_USERS_FILE = _HERE / "data" / "users.json"


# ---------------------------------------------------------------------------
# User store helpers
# ---------------------------------------------------------------------------

def _load_users() -> list[dict]:
    """Load users.json.  Returns [] on missing / empty / invalid file."""
    if not _USERS_FILE.exists():
        return []
    raw = _USERS_FILE.read_text(encoding="utf-8").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _save_users(users: list[dict]) -> None:
    """Persist users list to users.json."""
    _USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _USERS_FILE.write_text(json.dumps(users, indent=2), encoding="utf-8")


def get_user_by_email(email: str) -> Optional[dict]:
    """Return the user record matching email (case-insensitive), or None."""
    email_lower = email.strip().lower()
    for u in _load_users():
        if u.get("email", "").strip().lower() == email_lower:
            return u
    return None


def get_user_by_id(user_id: str) -> Optional[dict]:
    for u in _load_users():
        if u.get("user_id") == user_id:
            return u
    return None


def create_user(
    email: str,
    password: str,
    full_name: str,
    role: str,
    institution: str,
) -> dict:
    """
    Create a new user, persist to users.json.

    Raises ValueError if email already registered.
    Returns the new user record (without password_hash for safety).
    """
    if get_user_by_email(email):
        raise ValueError("Email already registered.")

    users = _load_users()
    user_id = "U" + str(len(users) + 1).zfill(4)

    hashed = _hash_password(password)
    record = {
        "user_id":       user_id,
        "email":         email.strip().lower(),
        "password_hash": hashed,
        "full_name":     full_name.strip(),
        "role":          role.strip().lower(),
        "institution":   institution.strip(),
        "verified":      False,
        "created_at":    _now_iso(),
    }
    users.append(record)
    _save_users(users)
    # Return without sensitive fields
    return {k: v for k, v in record.items() if k != "password_hash"}


def verify_credentials(email: str, password: str) -> Optional[dict]:
    """
    Return user dict (no password_hash) if credentials are correct, else None.
    """
    user = get_user_by_email(email)
    if user is None:
        return None
    stored_hash = user.get("password_hash", "")
    if not _check_password(password, stored_hash):
        return None
    return {k: v for k, v in user.items() if k != "password_hash"}


def mark_verified(email: str) -> None:
    """Set verified=True for the given email."""
    users = _load_users()
    for u in users:
        if u.get("email", "").strip().lower() == email.strip().lower():
            u["verified"] = True
    _save_users(users)


# ---------------------------------------------------------------------------
# Password hashing (PBKDF2-HMAC-SHA256)
# ---------------------------------------------------------------------------

_ITERATIONS = 260_000
_HASH_NAME   = "sha256"
_SALT_LEN    = 16


def _hash_password(password: str) -> str:
    """Return a salted PBKDF2-HMAC-SHA256 hash string."""
    salt = os.urandom(_SALT_LEN)
    dk = hashlib.pbkdf2_hmac(_HASH_NAME, password.encode(), salt, _ITERATIONS)
    return salt.hex() + ":" + dk.hex()


def _check_password(password: str, stored: str) -> bool:
    """Constant-time comparison of password against stored hash."""
    try:
        salt_hex, dk_hex = stored.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        dk_expected = bytes.fromhex(dk_hex)
        dk_actual = hashlib.pbkdf2_hmac(_HASH_NAME, password.encode(), salt, _ITERATIONS)
        return hmac.compare_digest(dk_actual, dk_expected)
    except (ValueError, AttributeError):
        return False


# ---------------------------------------------------------------------------
# OTP (simple in-memory store for demo; no email sending)
# ---------------------------------------------------------------------------

_OTP_STORE: dict[str, dict] = {}   # email → {otp, expires}
_OTP_TTL = 600  # 10 minutes


def generate_otp(email: str) -> str:
    """Generate and store a 6-digit OTP for email.  Returns the OTP string."""
    otp = "".join(random.choices(string.digits, k=6))
    _OTP_STORE[email.strip().lower()] = {
        "otp":     otp,
        "expires": time.time() + _OTP_TTL,
    }
    return otp


def verify_otp(email: str, otp: str) -> bool:
    """Return True if the OTP is correct and not expired.  Consumes the OTP."""
    key = email.strip().lower()
    record = _OTP_STORE.get(key)
    if record is None:
        return False
    if time.time() > record["expires"]:
        del _OTP_STORE[key]
        return False
    if not hmac.compare_digest(record["otp"], otp.strip()):
        return False
    del _OTP_STORE[key]   # one-time use
    return True


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
