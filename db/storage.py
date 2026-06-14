"""SQLite helpers for sessions and quiz results."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "knowledge.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create database file and tables if they do not exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                is_verified INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                lesson_text TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                user_id INTEGER REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS quiz_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                score INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions (id)
            );

            CREATE TABLE IF NOT EXISTS otp_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                otp TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                expires_at TEXT NOT NULL,
                is_used INTEGER DEFAULT 0,
                attempt_count INTEGER DEFAULT 0
            );
            """
        )

        session_cols = {row["name"] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
        if "user_id" not in session_cols:
            conn.execute("ALTER TABLE sessions ADD COLUMN user_id INTEGER REFERENCES users(id)")

        quiz_cols = {row["name"] for row in conn.execute("PRAGMA table_info(quiz_results)").fetchall()}
        if "attempt_details" not in quiz_cols:
            conn.execute(
                "ALTER TABLE quiz_results ADD COLUMN attempt_details TEXT NOT NULL DEFAULT '[]'"
            )

        user_cols = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "is_verified" not in user_cols:
            # No DEFAULT so existing rows stay NULL until backfilled (verified legacy users).
            conn.execute("ALTER TABLE users ADD COLUMN is_verified INTEGER")
            conn.execute("UPDATE users SET is_verified = 1 WHERE is_verified IS NULL")

        otp_cols = {row["name"] for row in conn.execute("PRAGMA table_info(otp_codes)").fetchall()}
        if otp_cols and "attempt_count" not in otp_cols:
            conn.execute("ALTER TABLE otp_codes ADD COLUMN attempt_count INTEGER DEFAULT 0")

        conn.commit()

    delete_unverified_expired_users()


def create_user(username: str, email: str, hashed_password: str) -> bool:
    """Insert a new user (unverified until OTP confirmed). Returns False if duplicate."""
    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO users (username, email, password, is_verified)
                VALUES (?, ?, ?, 0)
                """,
                (username.strip(), email.strip(), hashed_password),
            )
            conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def delete_user_by_email(email: str) -> None:
    """Remove user row by email (e.g. rollback failed signup email send)."""
    with _connect() as conn:
        conn.execute("DELETE FROM otp_codes WHERE email = ?", (email.strip().lower(),))
        conn.execute("DELETE FROM users WHERE email = ?", (email.strip().lower(),))
        conn.commit()


def get_user_by_username(username: str) -> dict | None:
    """Return full user row including password hash, or None."""
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, username, email, password, created_at,
                   IFNULL(is_verified, 0) AS is_verified
            FROM users WHERE username = ?
            """,
            (username.strip(),),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "username": row["username"],
        "email": row["email"],
        "password": row["password"],
        "created_at": row["created_at"],
        "is_verified": int(row["is_verified"]),
    }


def save_otp(email: str, otp: str, expires_at: str) -> None:
    """Replace prior OTP rows for this email and insert a new code."""
    e = email.strip().lower()
    with _connect() as conn:
        conn.execute("DELETE FROM otp_codes WHERE email = ?", (e,))
        conn.execute(
            """
            INSERT INTO otp_codes (email, otp, expires_at)
            VALUES (?, ?, ?)
            """,
            (e, otp, expires_at),
        )
        conn.commit()


def get_latest_otp(email: str) -> dict | None:
    """Most recent OTP row for this email, or None."""
    e = email.strip().lower()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT otp, expires_at, is_used, attempt_count, created_at
            FROM otp_codes
            WHERE email = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (e,),
        ).fetchone()
    if row is None:
        return None
    return {
        "otp": row["otp"],
        "expires_at": row["expires_at"],
        "is_used": int(row["is_used"]),
        "attempt_count": int(row["attempt_count"] if row["attempt_count"] is not None else 0),
        "created_at": row["created_at"],
    }


def increment_otp_attempt_count(email: str) -> None:
    """Increment failed-attempt counter on the latest OTP row."""
    e = email.strip().lower()
    with _connect() as conn:
        row = conn.execute(
            "SELECT id FROM otp_codes WHERE email = ? ORDER BY id DESC LIMIT 1",
            (e,),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE otp_codes SET attempt_count = IFNULL(attempt_count, 0) + 1 WHERE id = ?",
                (row["id"],),
            )
            conn.commit()


def mark_otp_used(email: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE otp_codes SET is_used = 1 WHERE email = ?",
            (email.strip().lower(),),
        )
        conn.commit()


def verify_user_email(email: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET is_verified = 1 WHERE email = ?",
            (email.strip().lower(),),
        )
        conn.commit()


def is_user_verified(username: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT IFNULL(is_verified, 0) AS v FROM users WHERE username = ?",
            (username.strip(),),
        ).fetchone()
    if row is None:
        return False
    return int(row["v"]) == 1


def can_resend_otp(email: str) -> tuple[bool, str]:
    """Require at least 60 seconds since last OTP row was created."""
    record = get_latest_otp(email)
    if record is None:
        return True, "ok"
    created_raw = record.get("created_at")
    if not created_raw:
        return True, "ok"
    try:
        created = datetime.strptime(str(created_raw).strip()[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return True, "ok"
    seconds_since = (datetime.now() - created).total_seconds()
    if seconds_since < 60:
        wait = int(60 - seconds_since)
        return False, f"Please wait {wait} seconds before requesting a new code."
    return True, "ok"


def delete_unverified_expired_users() -> None:
    """Remove accounts still unverified after 24 hours (and their OTP rows)."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT email FROM users
            WHERE IFNULL(is_verified, 0) = 0
              AND datetime(created_at) < datetime('now', '-24 hours')
            """
        ).fetchall()
        for row in rows:
            conn.execute("DELETE FROM otp_codes WHERE email = ?", (row["email"],))
        conn.execute(
            """
            DELETE FROM users
            WHERE IFNULL(is_verified, 0) = 0
              AND datetime(created_at) < datetime('now', '-24 hours')
            """
        )
        conn.commit()


def username_exists(username: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM users WHERE username = ? LIMIT 1",
            (username.strip(),),
        ).fetchone()
    return row is not None


def email_exists(email: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM users WHERE email = ? LIMIT 1",
            (email.strip().lower(),),
        ).fetchone()
    return row is not None


def save_session(topic: str, lesson_text: str, user_id: int) -> int:
    """Persist a learning session for the given user."""
    ts = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO sessions (topic, lesson_text, timestamp, user_id)
            VALUES (?, ?, ?, ?)
            """,
            (topic.strip(), lesson_text, ts, user_id),
        )
        conn.commit()
        return int(cur.lastrowid)


def verify_session_owner(session_id: int, user_id: int) -> bool:
    """Return True if this session belongs to the user."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT user_id FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
    if row is None:
        return False
    return row["user_id"] == user_id


def save_quiz_result(session_id: int, score: int, attempt_details: list[dict] | None = None) -> None:
    """Record a quiz attempt (score 0–3) with optional per-question details."""
    ts = datetime.now(timezone.utc).isoformat()
    details_text = json.dumps(attempt_details or [], ensure_ascii=False)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO quiz_results (session_id, score, timestamp, attempt_details)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, score, ts, details_text),
        )
        conn.commit()


def get_history(user_id: int) -> list[dict]:
    """
    Return this user's sessions with quiz summary fields.
    Each row: id, topic, lesson_text, session_timestamp, score, attempts, last_quiz_timestamp.
    """
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                s.id,
                s.topic,
                s.lesson_text,
                s.timestamp AS session_timestamp,
                (SELECT MAX(q.score) FROM quiz_results q WHERE q.session_id = s.id) AS score,
                (SELECT COUNT(*) FROM quiz_results q WHERE q.session_id = s.id) AS attempts,
                (SELECT MAX(q.timestamp) FROM quiz_results q WHERE q.session_id = s.id) AS last_quiz_timestamp
            FROM sessions s
            WHERE s.user_id = ?
            ORDER BY s.timestamp DESC
            """,
            (user_id,),
        ).fetchall()

    return [
        {
            "id": row["id"],
            "topic": row["topic"],
            "lesson_text": row["lesson_text"],
            "session_timestamp": row["session_timestamp"],
            "score": row["score"],
            "attempts": row["attempts"],
            "last_quiz_timestamp": row["last_quiz_timestamp"],
        }
        for row in rows
    ]


def delete_session(session_id: int, user_id: int) -> bool:
    """
    Delete a session and all its quiz results.
    Only deletes if the session belongs to the given user.
    Returns True if deleted, False if not found or wrong owner.
    """
    if not verify_session_owner(session_id, user_id):
        return False
    with _connect() as conn:
        conn.execute(
            "DELETE FROM quiz_results WHERE session_id = ?",
            (session_id,),
        )
        conn.execute(
            "DELETE FROM sessions WHERE id = ?",
            (session_id,),
        )
        conn.commit()
    return True


def get_quiz_attempts(session_id: int) -> list[dict]:
    """Return all quiz attempts for one session, newest first."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, score, timestamp, attempt_details
            FROM quiz_results
            WHERE session_id = ?
            ORDER BY timestamp DESC
            """,
            (session_id,),
        ).fetchall()
    attempts: list[dict] = []
    for row in rows:
        try:
            details = json.loads(row["attempt_details"] or "[]")
        except Exception:
            details = []
        attempts.append(
            {
                "id": row["id"],
                "score": row["score"],
                "timestamp": row["timestamp"],
                "details": details if isinstance(details, list) else [],
            }
        )
    return attempts
