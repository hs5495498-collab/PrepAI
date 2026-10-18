import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import db
import storage


def test_schema_initializes_on_first_connect():
    conn = db.connect()
    try:
        tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        assert {"interviews", "questions", "answers"} <= tables
    finally:
        conn.close()


def test_create_session_persists_interview_and_questions():
    session = storage.create_session("Engineer", "technical", "easy", [("q1", "A?"), ("q2", "B?")], "fixed")
    conn = db.connect()
    try:
        interview = conn.execute("SELECT * FROM interviews WHERE id = ?", (session["id"],)).fetchone()
        assert interview is not None
        assert interview["role"] == "Engineer"
        assert interview["category"] == "technical"
        assert interview["difficulty"] == "easy"
        assert interview["question_count"] == 2
        assert interview["status"] == "in_progress"
        assert interview["question_source"] == "fixed"
        assert interview["completed_at"] is None
        questions = conn.execute(
            "SELECT * FROM questions WHERE interview_id = ? ORDER BY position", (session["id"],)
        ).fetchall()
        assert len(questions) == 2
    finally:
        conn.close()


def test_question_ordering_and_ids_preserved():
    session = storage.create_session(
        "Engineer", "behavioral", "medium",
        [("q1", "First"), ("q2", "Second"), ("q3", "Third")],
        "fixed",
    )
    assert [q["id"] for q in session["questions"]] == ["q1", "q2", "q3"]
    assert [q["text"] for q in session["questions"]] == ["First", "Second", "Third"]

    reloaded = storage.get_session(session["id"])
    assert [q["id"] for q in reloaded["questions"]] == ["q1", "q2", "q3"]
    assert [q["text"] for q in reloaded["questions"]] == ["First", "Second", "Third"]


def test_answer_persists_and_is_returned_on_reload():
    session = storage.create_session("Engineer", "technical", "easy", [("q1", "A?")], "fixed")
    storage.record_answer(session["id"], "q1", "my answer")

    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT answer_text FROM answers WHERE interview_id = ? AND question_id = ?",
            (session["id"], "q1"),
        ).fetchone()
        assert row["answer_text"] == "my answer"
    finally:
        conn.close()

    reloaded = storage.get_session(session["id"])
    assert reloaded["questions"][0]["answer"] == "my answer"


def test_duplicate_answer_rejected_at_storage_level():
    session = storage.create_session("Engineer", "technical", "easy", [("q1", "A?")], "fixed")
    storage.record_answer(session["id"], "q1", "first")
    with pytest.raises(storage.DuplicateAnswer):
        storage.record_answer(session["id"], "q1", "second")


def test_completion_state_and_timestamp_persist():
    session = storage.create_session("Engineer", "technical", "easy", [("q1", "A?")], "fixed")
    completed = storage.complete_session(session["id"])
    assert completed["status"] == "completed"
    assert completed["completed_at"] is not None

    conn = db.connect()
    try:
        row = conn.execute("SELECT status, completed_at FROM interviews WHERE id = ?", (session["id"],)).fetchone()
        assert row["status"] == "completed"
        assert row["completed_at"] is not None
    finally:
        conn.close()


def test_get_session_returns_questions_and_answers_together():
    session = storage.create_session(
        "Engineer", "technical", "easy", [("q1", "A?"), ("q2", "B?")], "fixed"
    )
    storage.record_answer(session["id"], "q1", "answered")

    reloaded = storage.get_session(session["id"])
    assert reloaded["questions"][0]["answer"] == "answered"
    assert reloaded["questions"][1]["answer"] is None


def test_foreign_key_enforcement_rejects_orphan_answer():
    session = storage.create_session("Engineer", "technical", "easy", [("q1", "A?")], "fixed")
    conn = db.connect()
    try:
        with pytest.raises(sqlite3.IntegrityError):
            with conn:
                conn.execute(
                    "INSERT INTO answers (interview_id, question_id, answer_text, submitted_at) "
                    "VALUES (?, 'does-not-exist', 'x', 'now')",
                    (session["id"],),
                )
    finally:
        conn.close()


def test_transaction_rolls_back_on_duplicate_question_id():
    conn_before = db.connect()
    try:
        before_interviews = conn_before.execute("SELECT COUNT(*) AS n FROM interviews").fetchone()["n"]
        before_questions = conn_before.execute("SELECT COUNT(*) AS n FROM questions").fetchone()["n"]
    finally:
        conn_before.close()

    # Two questions sharing the same id violates the (interview_id, id)
    # primary key on the second insert - the whole transaction, including
    # the interview row itself, must roll back rather than leaving a
    # half-written interview with only one question.
    with pytest.raises(sqlite3.IntegrityError):
        storage.create_session(
            "Engineer", "technical", "easy", [("q1", "A?"), ("q1", "Duplicate id")], "fixed"
        )

    conn_after = db.connect()
    try:
        after_interviews = conn_after.execute("SELECT COUNT(*) AS n FROM interviews").fetchone()["n"]
        after_questions = conn_after.execute("SELECT COUNT(*) AS n FROM questions").fetchone()["n"]
    finally:
        conn_after.close()

    assert after_interviews == before_interviews
    assert after_questions == before_questions


def test_data_survives_closing_and_reopening_the_connection():
    session = storage.create_session("Engineer", "technical", "easy", [("q1", "A?")], "fixed")
    storage.record_answer(session["id"], "q1", "persisted answer")

    # A brand new connection object, independent of anything storage.py or
    # this test has open - the only thing that could make the data visible
    # here is that it actually reached disk.
    fresh_conn = sqlite3.connect(str(db.get_db_path()))
    try:
        fresh_conn.row_factory = sqlite3.Row
        row = fresh_conn.execute(
            "SELECT answer_text FROM answers WHERE interview_id = ?", (session["id"],)
        ).fetchone()
        assert row["answer_text"] == "persisted answer"
    finally:
        fresh_conn.close()


def test_session_survives_simulated_restart():
    # storage.py never holds a connection or any session data in memory
    # between calls - every function opens and closes its own connection.
    # Re-reading through get_session() after that is already a faithful
    # simulation of "the backend process restarted and we reconnected."
    session = storage.create_session("Engineer", "hr", "easy", [("q1", "A?"), ("q2", "B?")], "fixed")
    storage.record_answer(session["id"], "q1", "before restart")
    storage.complete_session(session["id"])

    reloaded = storage.get_session(session["id"])
    assert reloaded["status"] == "completed"
    assert reloaded["questions"][0]["answer"] == "before restart"
    assert reloaded["questions"][1]["answer"] is None


def test_fixed_question_interview_persists_with_correct_source():
    session = storage.create_session("Engineer", "technical", "easy", [("q1", "A?")], "fixed")
    assert storage.get_session(session["id"])["question_source"] == "fixed"


def test_ai_sourced_interview_persists_with_correct_source_no_live_call():
    # No AI provider is touched here - these questions are handed in
    # directly, exactly as main.py would after a (mocked, in other tests)
    # successful ai_provider.generate_questions() call.
    session = storage.create_session(
        "Engineer", "technical", "easy", [("q1", "AI question one"), ("q2", "AI question two")], "ai"
    )
    reloaded = storage.get_session(session["id"])
    assert reloaded["question_source"] == "ai"
    assert [q["text"] for q in reloaded["questions"]] == ["AI question one", "AI question two"]
