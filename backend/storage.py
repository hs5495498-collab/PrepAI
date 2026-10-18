"""In-memory interview session store.

Sessions live only in this process's memory (a plain dict) and are lost
whenever the backend restarts. That's expected for this phase - persistent
storage (a real database) is planned for a later phase, not this one.
"""
import uuid
from datetime import datetime, timezone
from typing import List, Tuple

SESSIONS: dict = {}


class SessionNotFound(Exception):
    pass


class QuestionNotFound(Exception):
    pass


class AlreadyCompleted(Exception):
    pass


class DuplicateAnswer(Exception):
    pass


def create_session(role: str, category: str, difficulty: str, questions: List[Tuple[str, str]], question_source: str = "fixed") -> dict:
    session_id = uuid.uuid4().hex
    session = {
        "id": session_id,
        "role": role,
        "category": category,
        "difficulty": difficulty,
        "status": "in_progress",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
        "question_source": question_source,
        "questions": [{"id": q_id, "text": text, "answer": None} for q_id, text in questions],
    }
    SESSIONS[session_id] = session
    return session


def get_session(session_id: str) -> dict:
    session = SESSIONS.get(session_id)
    if session is None:
        raise SessionNotFound(session_id)
    return session


def record_answer(session_id: str, question_id: str, answer: str) -> dict:
    session = get_session(session_id)
    if session["status"] == "completed":
        raise AlreadyCompleted(session_id)
    question = next((q for q in session["questions"] if q["id"] == question_id), None)
    if question is None:
        raise QuestionNotFound(question_id)
    if question["answer"] is not None:
        raise DuplicateAnswer(question_id)
    question["answer"] = answer
    return session


def complete_session(session_id: str) -> dict:
    session = get_session(session_id)
    if session["status"] == "completed":
        raise AlreadyCompleted(session_id)
    session["status"] = "completed"
    session["completed_at"] = datetime.now(timezone.utc).isoformat()
    return session


def answered_count(session: dict) -> int:
    return sum(1 for q in session["questions"] if q["answer"] is not None)
