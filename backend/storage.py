"""Interview session repository, backed by the SQLite database in db.py.

Sessions, their questions, and submitted answers now persist in the
database file and survive a backend restart (Phase 6). This module keeps
the exact same public function names, arguments, exceptions, and returned
dict shape as the earlier in-memory version, so main.py's route handlers
did not need to change at all.
"""
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import List, Tuple

import db


class SessionNotFound(Exception):
    pass


class QuestionNotFound(Exception):
    pass


class AlreadyCompleted(Exception):
    pass


class DuplicateAnswer(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_session(conn: sqlite3.Connection, session_id: str) -> dict:
    interview = conn.execute("SELECT * FROM interviews WHERE id = ?", (session_id,)).fetchone()
    if interview is None:
        raise SessionNotFound(session_id)
    rows = conn.execute(
        "SELECT q.id AS id, q.text AS text, a.answer_text AS answer_text "
        "FROM questions q LEFT JOIN answers a "
        "ON a.interview_id = q.interview_id AND a.question_id = q.id "
        "WHERE q.interview_id = ? ORDER BY q.position ASC",
        (session_id,),
    ).fetchall()
    return {
        "id": interview["id"],
        "role": interview["role"],
        "category": interview["category"],
        "difficulty": interview["difficulty"],
        "status": interview["status"],
        "created_at": interview["created_at"],
        "completed_at": interview["completed_at"],
        "question_source": interview["question_source"],
        "questions": [{"id": r["id"], "text": r["text"], "answer": r["answer_text"]} for r in rows],
    }


def create_session(role: str, category: str, difficulty: str, questions: List[Tuple[str, str]], question_source: str = "fixed") -> dict:
    session_id = uuid.uuid4().hex
    created_at = _now()
    conn = db.connect()
    try:
        with conn:
            conn.execute(
                "INSERT INTO interviews (id, role, category, difficulty, question_count, status, question_source, created_at, completed_at) "
                "VALUES (?, ?, ?, ?, ?, 'in_progress', ?, ?, NULL)",
                (session_id, role, category, difficulty, len(questions), question_source, created_at),
            )
            for position, (question_id, text) in enumerate(questions):
                conn.execute(
                    "INSERT INTO questions (interview_id, id, text, position) VALUES (?, ?, ?, ?)",
                    (session_id, question_id, text, position),
                )
        return _load_session(conn, session_id)
    finally:
        conn.close()


def get_session(session_id: str) -> dict:
    conn = db.connect()
    try:
        return _load_session(conn, session_id)
    finally:
        conn.close()


def record_answer(session_id: str, question_id: str, answer: str) -> dict:
    conn = db.connect()
    try:
        interview = conn.execute("SELECT status FROM interviews WHERE id = ?", (session_id,)).fetchone()
        if interview is None:
            raise SessionNotFound(session_id)
        if interview["status"] == "completed":
            raise AlreadyCompleted(session_id)
        question = conn.execute(
            "SELECT 1 FROM questions WHERE interview_id = ? AND id = ?", (session_id, question_id)
        ).fetchone()
        if question is None:
            raise QuestionNotFound(question_id)
        existing = conn.execute(
            "SELECT 1 FROM answers WHERE interview_id = ? AND question_id = ?", (session_id, question_id)
        ).fetchone()
        if existing is not None:
            raise DuplicateAnswer(question_id)
        try:
            with conn:
                conn.execute(
                    "INSERT INTO answers (interview_id, question_id, answer_text, submitted_at) VALUES (?, ?, ?, ?)",
                    (session_id, question_id, answer, _now()),
                )
        except sqlite3.IntegrityError:
            # Backstop for a near-simultaneous duplicate submission that
            # slipped past the SELECT check above.
            raise DuplicateAnswer(question_id)
        return _load_session(conn, session_id)
    finally:
        conn.close()


def complete_session(session_id: str) -> dict:
    conn = db.connect()
    try:
        interview = conn.execute("SELECT status FROM interviews WHERE id = ?", (session_id,)).fetchone()
        if interview is None:
            raise SessionNotFound(session_id)
        if interview["status"] == "completed":
            raise AlreadyCompleted(session_id)
        with conn:
            conn.execute(
                "UPDATE interviews SET status = 'completed', completed_at = ? WHERE id = ?",
                (_now(), session_id),
            )
        return _load_session(conn, session_id)
    finally:
        conn.close()


def answered_count(session: dict) -> int:
    return sum(1 for q in session["questions"] if q["answer"] is not None)
