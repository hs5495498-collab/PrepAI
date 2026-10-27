"""Interview session repository, backed by the SQLite database in db.py.

Sessions, their questions, and submitted answers now persist in the
database file and survive a backend restart (Phase 6). This module keeps
the exact same public function names, arguments, exceptions, and returned
dict shape as the earlier in-memory version, so main.py's route handlers
did not need to change at all.
"""
import json
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


class AnswerNotFound(Exception):
    """Raised when a question exists but has no submitted answer yet -
    evaluating it would mean evaluating nothing."""
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_session(conn: sqlite3.Connection, session_id: str) -> dict:
    interview = conn.execute("SELECT * FROM interviews WHERE id = ?", (session_id,)).fetchone()
    if interview is None:
        raise SessionNotFound(session_id)
    rows = conn.execute(
        "SELECT q.id AS id, q.text AS text, a.answer_text AS answer_text, "
        "ev.total_score AS eval_total_score, ev.relevance_score AS eval_relevance_score, "
        "ev.correctness_score AS eval_correctness_score, ev.completeness_score AS eval_completeness_score, "
        "ev.clarity_score AS eval_clarity_score, ev.strengths AS eval_strengths, "
        "ev.weaknesses AS eval_weaknesses, ev.suggestions AS eval_suggestions, "
        "ev.example_answer AS eval_example_answer, ev.model AS eval_model, "
        "ev.created_at AS eval_created_at "
        "FROM questions q "
        "LEFT JOIN answers a ON a.interview_id = q.interview_id AND a.question_id = q.id "
        "LEFT JOIN evaluations ev ON ev.interview_id = q.interview_id AND ev.question_id = q.id "
        "WHERE q.interview_id = ? ORDER BY q.position ASC",
        (session_id,),
    ).fetchall()
    questions = []
    for r in rows:
        question = {"id": r["id"], "text": r["text"], "answer": r["answer_text"], "evaluation": None}
        if r["eval_total_score"] is not None:
            question["evaluation"] = {
                "total_score": r["eval_total_score"],
                "relevance_score": r["eval_relevance_score"],
                "correctness_score": r["eval_correctness_score"],
                "completeness_score": r["eval_completeness_score"],
                "clarity_score": r["eval_clarity_score"],
                "strengths": json.loads(r["eval_strengths"]),
                "weaknesses": json.loads(r["eval_weaknesses"]),
                "suggestions": json.loads(r["eval_suggestions"]),
                "example_answer": r["eval_example_answer"],
                "model": r["eval_model"],
                "created_at": r["eval_created_at"],
            }
        questions.append(question)
    return {
        "id": interview["id"],
        "role": interview["role"],
        "category": interview["category"],
        "difficulty": interview["difficulty"],
        "status": interview["status"],
        "created_at": interview["created_at"],
        "completed_at": interview["completed_at"],
        "question_source": interview["question_source"],
        "user_id": interview["user_id"],
        "questions": questions,
    }


def create_session(role: str, category: str, difficulty: str, questions: List[Tuple[str, str]], question_source: str = "fixed", user_id=None) -> dict:
    session_id = uuid.uuid4().hex
    created_at = _now()
    conn = db.connect()
    try:
        with conn:
            conn.execute(
                "INSERT INTO interviews (id, role, category, difficulty, question_count, status, question_source, created_at, completed_at, user_id) "
                "VALUES (?, ?, ?, ?, ?, 'in_progress', ?, ?, NULL, ?)",
                (session_id, role, category, difficulty, len(questions), question_source, created_at, user_id),
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


def get_question_for_evaluation(session_id: str, question_id: str) -> dict:
    """Returns {question_text, answer_text} for a question that both exists
    in this interview and has a real, non-blank submitted answer. Raises
    SessionNotFound / QuestionNotFound / AnswerNotFound otherwise - the
    answer is always read from the database, never trusted from a caller."""
    conn = db.connect()
    try:
        interview = conn.execute("SELECT id FROM interviews WHERE id = ?", (session_id,)).fetchone()
        if interview is None:
            raise SessionNotFound(session_id)
        question = conn.execute(
            "SELECT text FROM questions WHERE interview_id = ? AND id = ?", (session_id, question_id)
        ).fetchone()
        if question is None:
            raise QuestionNotFound(question_id)
        answer = conn.execute(
            "SELECT answer_text FROM answers WHERE interview_id = ? AND question_id = ?", (session_id, question_id)
        ).fetchone()
        if answer is None or not answer["answer_text"] or not answer["answer_text"].strip():
            raise AnswerNotFound(question_id)
        return {"question_text": question["text"], "answer_text": answer["answer_text"]}
    finally:
        conn.close()


def get_recent_question_texts(user_id, category: str, difficulty: str, limit_interviews: int = 3) -> set:
    """Returns the set of question texts used in this account's most recent
    `limit_interviews` interviews of this exact category/difficulty, so a
    new session can prefer to avoid repeating them (see
    questions.pick_questions's exclude_texts). Scoped strictly to user_id,
    so this never leaks one account's recent questions into another's, and
    anonymous sessions (user_id is None) have no persistent identity to
    track against, so this always returns an empty set for them rather
    than querying anything - recent-question avoidance is an account-only
    feature, like recommendations."""
    if user_id is None:
        return set()
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT q.text AS text FROM questions q "
            "WHERE q.interview_id IN ("
            "  SELECT id FROM interviews WHERE user_id = ? AND category = ? AND difficulty = ? "
            "  ORDER BY created_at DESC, id DESC LIMIT ?"
            ")",
            (user_id, category, difficulty, limit_interviews),
        ).fetchall()
        return {r["text"] for r in rows}
    finally:
        conn.close()


def get_user_recommendation_data(user_id: int) -> dict:
    """Returns only this account's own data for building recommendations
    and analytics: its total interview count, how many it has completed,
    and every evaluation attached to an interview it owns (joined with
    that interview's category/difficulty). Anonymous interviews (user_id
    IS NULL) and other accounts' interviews are never included - the
    WHERE clause is the ownership boundary, enforced in SQL."""
    conn = db.connect()
    try:
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM interviews WHERE user_id = ?", (user_id,)
        ).fetchone()["n"]
        completed = conn.execute(
            "SELECT COUNT(*) AS n FROM interviews WHERE user_id = ? AND status = 'completed'", (user_id,)
        ).fetchone()["n"]
        rows = conn.execute(
            "SELECT i.category AS category, i.difficulty AS difficulty, "
            "e.question_id AS question_id, e.total_score AS total_score, "
            "e.relevance_score AS relevance_score, e.correctness_score AS correctness_score, "
            "e.completeness_score AS completeness_score, e.clarity_score AS clarity_score, "
            "e.created_at AS evaluated_at "
            "FROM evaluations e JOIN interviews i ON i.id = e.interview_id "
            "WHERE i.user_id = ? ORDER BY e.created_at ASC",
            (user_id,),
        ).fetchall()
        return {
            "total_interviews": total,
            "completed_interviews": completed,
            "evaluations": [dict(r) for r in rows],
        }
    finally:
        conn.close()


def list_user_interviews(user_id: int, limit: int, offset: int):
    """Returns (items, total) for this account's own interviews, newest
    first, with per-interview answered/evaluated counts and average score
    computed in the same query (one round trip, no N+1 pattern). Ownership
    is enforced by the WHERE clause, not filtered after the fact."""
    conn = db.connect()
    try:
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM interviews WHERE user_id = ?", (user_id,)
        ).fetchone()["n"]
        rows = conn.execute(
            "SELECT i.id AS id, i.role AS role, i.category AS category, i.difficulty AS difficulty, "
            "i.status AS status, i.question_count AS question_count, "
            "i.created_at AS created_at, i.completed_at AS completed_at, "
            "(SELECT COUNT(*) FROM answers a WHERE a.interview_id = i.id) AS answered_count, "
            "(SELECT COUNT(*) FROM evaluations e WHERE e.interview_id = i.id) AS evaluated_count, "
            "(SELECT AVG(e.total_score) FROM evaluations e WHERE e.interview_id = i.id) AS average_score "
            "FROM interviews i WHERE i.user_id = ? "
            "ORDER BY i.created_at DESC, i.id DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        ).fetchall()
        items = [{
            "session_id": r["id"], "role": r["role"], "category": r["category"], "difficulty": r["difficulty"],
            "status": r["status"], "question_count": r["question_count"],
            "answered_count": r["answered_count"], "evaluated_count": r["evaluated_count"],
            "average_score": round(r["average_score"], 1) if r["average_score"] is not None else None,
            "created_at": r["created_at"], "completed_at": r["completed_at"],
        } for r in rows]
        return items, total
    finally:
        conn.close()


def _row_to_evaluation(row) -> dict:
    return {
        "question_id": row["question_id"],
        "total_score": row["total_score"],
        "relevance_score": row["relevance_score"],
        "correctness_score": row["correctness_score"],
        "completeness_score": row["completeness_score"],
        "clarity_score": row["clarity_score"],
        "relevance_assessment": row["relevance_assessment"],
        "correctness_assessment": row["correctness_assessment"],
        "explanation": row["explanation"],
        "strengths": json.loads(row["strengths"]),
        "weaknesses": json.loads(row["weaknesses"]),
        "suggestions": json.loads(row["suggestions"]),
        "example_answer": row["example_answer"],
        "model": row["model"],
        "created_at": row["created_at"],
    }


def get_evaluation(session_id: str, question_id: str):
    """Returns the stored evaluation dict for this question, or None if it
    has never been evaluated."""
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT * FROM evaluations WHERE interview_id = ? AND question_id = ?", (session_id, question_id)
        ).fetchone()
        return _row_to_evaluation(row) if row is not None else None
    finally:
        conn.close()


def save_evaluation(session_id: str, question_id: str, result: dict) -> dict:
    """Stores a new evaluation. If one already exists for this question
    (e.g. a retried request), returns the EXISTING row rather than creating
    a duplicate, overwriting it, or calling the AI provider again -
    evaluation is idempotent per question."""
    conn = db.connect()
    try:
        existing = conn.execute(
            "SELECT * FROM evaluations WHERE interview_id = ? AND question_id = ?", (session_id, question_id)
        ).fetchone()
        if existing is not None:
            return _row_to_evaluation(existing)
        try:
            with conn:
                conn.execute(
                    "INSERT INTO evaluations (interview_id, question_id, total_score, relevance_score, "
                    "correctness_score, completeness_score, clarity_score, relevance_assessment, "
                    "correctness_assessment, explanation, strengths, weaknesses, suggestions, "
                    "example_answer, model, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        session_id, question_id, result["total_score"], result["relevance_score"],
                        result["correctness_score"], result["completeness_score"], result["clarity_score"],
                        result["relevance_assessment"], result["correctness_assessment"], result["explanation"],
                        json.dumps(result["strengths"]), json.dumps(result["weaknesses"]), json.dumps(result["suggestions"]),
                        result.get("example_answer"), result["model"], _now(),
                    ),
                )
        except sqlite3.IntegrityError:
            # A near-simultaneous duplicate request won the race - return
            # its result instead of erroring or inserting a second row.
            row = conn.execute(
                "SELECT * FROM evaluations WHERE interview_id = ? AND question_id = ?", (session_id, question_id)
            ).fetchone()
            return _row_to_evaluation(row)
        row = conn.execute(
            "SELECT * FROM evaluations WHERE interview_id = ? AND question_id = ?", (session_id, question_id)
        ).fetchone()
        return _row_to_evaluation(row)
    finally:
        conn.close()
