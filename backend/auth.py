"""Authentication: password hashing, user accounts, and server-managed
sessions - kept separate from storage.py (interview data) and from the
route handlers in main.py.

Sessions are opaque random tokens stored in the database (not JWTs), so a
session can be instantly and completely revoked by deleting its row - no
app-wide signing secret is needed. A second random value, the CSRF token,
is issued alongside the session and must be echoed back as a request
header on cookie-authenticated state-changing requests (the "double submit
cookie" pattern) - see README.md for the full explanation.
"""
import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError

import db

SESSION_COOKIE_NAME = "prepai_session"
CSRF_COOKIE_NAME = "prepai_csrf"
DEFAULT_SESSION_LIFETIME_DAYS = 7

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_hasher = PasswordHasher()


class EmailAlreadyRegistered(Exception):
    pass


class InvalidCredentials(Exception):
    pass


def normalize_email(email: str) -> str:
    return email.strip().lower()


def is_valid_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(email)) and len(email) <= 254


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def session_lifetime_days() -> int:
    try:
        return int(os.environ.get("SESSION_LIFETIME_DAYS", DEFAULT_SESSION_LIFETIME_DAYS))
    except ValueError:
        return DEFAULT_SESSION_LIFETIME_DAYS


def session_cookie_secure() -> bool:
    return os.environ.get("SESSION_COOKIE_SECURE", "false").strip().lower() == "true"


def create_user(email: str, password: str) -> dict:
    """Hashes the password (Argon2id, never stored or logged in plain text)
    and inserts a new user row. Raises EmailAlreadyRegistered on a duplicate
    normalized email - the UNIQUE constraint is the real guard against a
    race between two near-simultaneous registrations, not just this check."""
    normalized = normalize_email(email)
    password_hash = _hasher.hash(password)
    created_at = _iso(_now())
    conn = db.connect()
    try:
        try:
            with conn:
                cursor = conn.execute(
                    "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
                    (normalized, password_hash, created_at),
                )
        except sqlite3.IntegrityError:
            raise EmailAlreadyRegistered(normalized)
        return {"id": cursor.lastrowid, "email": normalized, "created_at": created_at}
    finally:
        conn.close()


def authenticate(email: str, password: str) -> dict:
    """Verifies email+password. Raises InvalidCredentials for both an
    unknown email and a wrong password - using the same exception (and the
    same HTTP response later) for both avoids revealing which emails are
    registered."""
    normalized = normalize_email(email)
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT id, email, password_hash, created_at FROM users WHERE email = ?", (normalized,)
        ).fetchone()
        if row is None:
            # Still do a hash verification against a dummy hash so this path
            # takes roughly the same time as a real wrong-password check,
            # rather than returning instantly and leaking timing information
            # about which emails exist.
            try:
                _hasher.verify(_hasher.hash("decoy-password"), password)
            except VerifyMismatchError:
                pass
            raise InvalidCredentials("unknown email")
        try:
            _hasher.verify(row["password_hash"], password)
        except (VerifyMismatchError, InvalidHashError):
            raise InvalidCredentials("wrong password")
        return {"id": row["id"], "email": row["email"], "created_at": row["created_at"]}
    finally:
        conn.close()


def create_session_for_user(user_id: int) -> dict:
    """Always issues a brand-new random token - never accepts or reuses a
    client-supplied identifier, which is what prevents session fixation."""
    token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    created_at = _now()
    expires_at = created_at + timedelta(days=session_lifetime_days())
    conn = db.connect()
    try:
        with conn:
            conn.execute(
                "INSERT INTO sessions (token, csrf_token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                (token, csrf_token, user_id, _iso(created_at), _iso(expires_at)),
            )
        return {"token": token, "csrf_token": csrf_token, "expires_at": _iso(expires_at)}
    finally:
        conn.close()


def get_user_for_session(token: str):
    """Returns the {id, email, created_at, csrf_token} dict for a valid,
    unexpired session token, or None. Never raises on a missing/garbage
    token - callers treat None as "not logged in"."""
    if not token:
        return None
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT s.csrf_token AS csrf_token, s.expires_at AS expires_at, "
            "u.id AS id, u.email AS email, u.created_at AS created_at "
            "FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = ?",
            (token,),
        ).fetchone()
        if row is None:
            return None
        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at < _now():
            return None
        return {"id": row["id"], "email": row["email"], "created_at": row["created_at"], "csrf_token": row["csrf_token"]}
    finally:
        conn.close()


def delete_session(token: str) -> None:
    if not token:
        return
    conn = db.connect()
    try:
        with conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
    finally:
        conn.close()
