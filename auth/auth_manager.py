"""Login, signup, and OTP verification (password hashing via bcrypt)."""

from __future__ import annotations

import re
from datetime import datetime

import bcrypt

from auth.email_sender import generate_otp, get_otp_expiry, send_otp_email
from db.storage import (
    can_resend_otp,
    create_user,
    delete_user_by_email,
    email_exists,
    get_latest_otp,
    get_user_by_username,
    increment_otp_attempt_count,
    mark_otp_used,
    save_otp,
    username_exists,
    verify_user_email,
)

OTP_SENT_MESSAGE = "otp_sent"


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def _validate_username(username: str) -> tuple[bool, str]:
    u = username.strip()
    if not (3 <= len(u) <= 20):
        return False, "Username must be between 3 and 20 characters."
    if not re.fullmatch(r"[a-zA-Z0-9_]+", u):
        return False, "Username may only contain letters, numbers, and underscores."
    return True, ""


def _validate_email(email: str) -> tuple[bool, str]:
    e = email.strip()
    if "@" not in e or "." not in e:
        return False, "Please enter a valid email address."
    return True, ""


def _validate_password(password: str) -> tuple[bool, str]:
    if len(password) < 8:
        return False, "Password must be at least 8 characters."
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one number."
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter."
    return True, ""


def signup_user(username: str, email: str, password: str) -> tuple[bool, str]:
    ok, msg = _validate_username(username)
    if not ok:
        return False, msg
    ok, msg = _validate_email(email)
    if not ok:
        return False, msg
    ok, msg = _validate_password(password)
    if not ok:
        return False, msg

    u = username.strip().lower()
    e = email.strip().lower()
    if username_exists(u):
        return False, "That username is already taken."
    if email_exists(e):
        return False, "That email is already registered."

    hashed = hash_password(password)
    if not create_user(u, e, hashed):
        return False, "Could not create account. Username or email may already be taken."

    otp = generate_otp()
    expires_at = get_otp_expiry()
    save_otp(e, otp, expires_at)

    sent, error = send_otp_email(e, otp)
    if not sent:
        delete_user_by_email(e)
        return False, f"Account could not be completed: {error}"

    return True, OTP_SENT_MESSAGE


def login_user(username: str, password: str) -> tuple[bool, str | dict]:
    row = get_user_by_username(username.strip().lower())
    if row is None:
        return False, "Invalid username or password."
    if not verify_password(password, row["password"]):
        return False, "Invalid username or password."
    if int(row.get("is_verified", 0)) != 1:
        return False, "EMAIL_NOT_VERIFIED"
    return True, {
        "id": row["id"],
        "username": row["username"],
        "email": row["email"],
    }


def verify_otp(email: str, entered_otp: str) -> tuple[bool, str]:
    e = email.strip().lower()
    record = get_latest_otp(e)

    if not record:
        return False, "No verification code found. Please sign up again."

    if record["is_used"] == 1:
        return False, "This code has already been used. Please request a new one."

    if record["attempt_count"] >= 5:
        mark_otp_used(e)
        return False, "Too many wrong attempts. Please request a new code."

    try:
        expires_at = datetime.strptime(record["expires_at"].strip()[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        mark_otp_used(e)
        return False, "Invalid verification state. Please request a new code."

    if datetime.now() > expires_at:
        return False, "Code has expired. Please request a new one."

    if record["otp"] != entered_otp.strip():
        increment_otp_attempt_count(e)
        refreshed = get_latest_otp(e)
        if refreshed and refreshed["attempt_count"] >= 5:
            mark_otp_used(e)
            return False, "Too many wrong attempts. Please request a new code."
        return False, "Incorrect code. Please try again."

    mark_otp_used(e)
    verify_user_email(e)

    return True, "verified"


def resend_otp(email: str) -> tuple[bool, str]:
    e = email.strip().lower()
    ok_wait, wait_msg = can_resend_otp(e)
    if not ok_wait:
        return False, wait_msg

    otp = generate_otp()
    expires_at = get_otp_expiry()
    save_otp(e, otp, expires_at)

    sent, error = send_otp_email(e, otp)
    if not sent:
        return False, f"Failed to resend: {error}"

    return True, "resent"
