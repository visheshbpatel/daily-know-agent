"""SQLite persistence for learning sessions and quiz results."""

from db.storage import (
    get_history,
    get_quiz_attempts,
    init_db,
    save_quiz_result,
    save_session,
)

__all__ = [
    "init_db",
    "save_session",
    "save_quiz_result",
    "get_history",
    "get_quiz_attempts",
]
