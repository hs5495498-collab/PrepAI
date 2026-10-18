import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlite3

from fastapi.testclient import TestClient

import ai_provider
import main
import storage
from main import app

client = TestClient(app)


def create_interview(role="Software Engineer", category="technical", difficulty="medium", question_count=3):
    return client.post(
        "/api/interviews",
        json={"role": role, "category": category, "difficulty": difficulty, "question_count": question_count},
    )


def test_health_endpoint():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_create_interview_success():
    res = create_interview()
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "in_progress"
    assert body["role"] == "Software Engineer"
    assert body["category"] == "technical"
    assert body["total_questions"] == 3
    assert len(body["questions"]) == 3
    assert body["answered_count"] == 0
    assert all(q["answer"] is None for q in body["questions"])


def test_create_interview_rejects_invalid_category():
    res = client.post(
        "/api/interviews",
        json={"role": "Engineer", "category": "not-a-real-category", "difficulty": "medium", "question_count": 3},
    )
    assert res.status_code == 422


def test_get_session_success():
    created = create_interview().json()
    res = client.get(f"/api/interviews/{created['session_id']}")
    assert res.status_code == 200
    assert res.json()["session_id"] == created["session_id"]


def test_get_session_invalid_id():
    res = client.get("/api/interviews/does-not-exist")
    assert res.status_code == 404


def test_submit_answer_success():
    created = create_interview().json()
    session_id = created["session_id"]
    question_id = created["questions"][0]["id"]
    res = client.post(f"/api/interviews/{session_id}/answers", json={"question_id": question_id, "answer": "My answer"})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "answer_recorded"
    assert body["answered_count"] == 1
    assert body["total_questions"] == 3

    follow_up = client.get(f"/api/interviews/{session_id}")
    stored = next(q for q in follow_up.json()["questions"] if q["id"] == question_id)
    assert stored["answer"] == "My answer"


def test_submit_blank_answer_rejected():
    created = create_interview().json()
    session_id = created["session_id"]
    question_id = created["questions"][0]["id"]
    res = client.post(f"/api/interviews/{session_id}/answers", json={"question_id": question_id, "answer": "   "})
    assert res.status_code == 422


def test_submit_answer_invalid_session():
    res = client.post("/api/interviews/does-not-exist/answers", json={"question_id": "q1", "answer": "hi"})
    assert res.status_code == 404


def test_submit_answer_invalid_question_id():
    created = create_interview().json()
    session_id = created["session_id"]
    res = client.post(f"/api/interviews/{session_id}/answers", json={"question_id": "not-a-real-question", "answer": "hi"})
    assert res.status_code == 404


def test_submit_duplicate_answer_rejected():
    created = create_interview().json()
    session_id = created["session_id"]
    question_id = created["questions"][0]["id"]
    first = client.post(f"/api/interviews/{session_id}/answers", json={"question_id": question_id, "answer": "first"})
    assert first.status_code == 200
    second = client.post(f"/api/interviews/{session_id}/answers", json={"question_id": question_id, "answer": "second"})
    assert second.status_code == 409


def test_complete_interview_success():
    created = create_interview(question_count=2).json()
    session_id = created["session_id"]
    for q in created["questions"]:
        client.post(f"/api/interviews/{session_id}/answers", json={"question_id": q["id"], "answer": "an answer"})

    res = client.post(f"/api/interviews/{session_id}/complete")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "completed"
    assert body["answered_count"] == 2
    assert all(q["answer"] == "an answer" for q in body["questions"])


def test_submit_answer_after_completion_rejected():
    created = create_interview(question_count=1).json()
    session_id = created["session_id"]
    question_id = created["questions"][0]["id"]
    client.post(f"/api/interviews/{session_id}/complete")

    res = client.post(f"/api/interviews/{session_id}/answers", json={"question_id": question_id, "answer": "too late"})
    assert res.status_code == 409


def test_complete_twice_rejected():
    created = create_interview(question_count=1).json()
    session_id = created["session_id"]
    first = client.post(f"/api/interviews/{session_id}/complete")
    assert first.status_code == 200
    second = client.post(f"/api/interviews/{session_id}/complete")
    assert second.status_code == 409


def test_complete_invalid_session():
    res = client.post("/api/interviews/does-not-exist/complete")
    assert res.status_code == 404


def test_create_interview_uses_fixed_questions_by_default():
    # No AI env vars are set anywhere in this test run, so every interview
    # created without extra setup must come from the existing fixed bank -
    # this is Offline/Demo-equivalent behavior and must never silently
    # depend on a real AI provider being reachable.
    body = create_interview().json()
    assert body["question_source"] == "fixed"


def test_create_interview_uses_ai_when_configured(monkeypatch):
    def fake_generate(role, category, difficulty, count):
        return [("q{}".format(i + 1), "AI question {} for {}".format(i + 1, role)) for i in range(count)]

    monkeypatch.setattr(main.ai_provider, "is_configured", lambda: True)
    monkeypatch.setattr(main.ai_provider, "generate_questions", fake_generate)

    body = create_interview(question_count=3).json()
    assert body["question_source"] == "ai"
    assert len(body["questions"]) == 3
    assert body["questions"][0]["text"] == "AI question 1 for Software Engineer"
    ids = [q["id"] for q in body["questions"]]
    assert ids == ["q1", "q2", "q3"]


def test_create_interview_ai_failure_returns_clear_error_without_fallback(monkeypatch):
    monkeypatch.setattr(main.ai_provider, "is_configured", lambda: True)

    def fake_fail(role, category, difficulty, count):
        raise ai_provider.AIProviderUnavailable("the provider is down right now")

    monkeypatch.setattr(main.ai_provider, "generate_questions", fake_fail)

    res = create_interview()
    assert res.status_code == 503
    detail = res.json()["detail"]
    assert "session_id" not in res.json()
    # The internal exception text must never leak to the client.
    assert "the provider is down right now" not in detail
    assert isinstance(detail, str) and len(detail) > 0


def test_answer_and_completion_work_with_ai_generated_questions(monkeypatch):
    def fake_generate(role, category, difficulty, count):
        return [("q{}".format(i + 1), "AI question {}".format(i + 1)) for i in range(count)]

    monkeypatch.setattr(main.ai_provider, "is_configured", lambda: True)
    monkeypatch.setattr(main.ai_provider, "generate_questions", fake_generate)

    created = create_interview(question_count=2).json()
    session_id = created["session_id"]
    assert created["question_source"] == "ai"

    for q in created["questions"]:
        res = client.post(f"/api/interviews/{session_id}/answers", json={"question_id": q["id"], "answer": "an answer"})
        assert res.status_code == 200

    completed = client.post(f"/api/interviews/{session_id}/complete")
    assert completed.status_code == 200
    body = completed.json()
    assert body["status"] == "completed"
    assert body["question_source"] == "ai"
    assert all(q["answer"] == "an answer" for q in body["questions"])


def test_database_error_does_not_leak_sql_details(monkeypatch):
    def broken(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked: /some/internal/path.db")

    monkeypatch.setattr(main.storage, "create_session", broken)

    # A plain client with raise_server_exceptions=True (TestClient's default)
    # re-raises an exception into the test even after main.py's app-level
    # handler already turned it into a safe response - that is a debugging
    # convenience, not what a real browser would see. Checking the actual
    # wire response needs raise_server_exceptions=False here.
    safe_client = TestClient(app, raise_server_exceptions=False)
    res = safe_client.post(
        "/api/interviews",
        json={"role": "Software Engineer", "category": "technical", "difficulty": "medium", "question_count": 3},
    )
    assert res.status_code == 500
    text = res.text
    assert "database is locked" not in text
    assert "sqlite3" not in text
    assert "/some/internal/path.db" not in text
    assert res.json() == {"error": "Internal server error."}


def test_interview_creation_persists_across_a_fresh_storage_call():
    # Simulates what a backend restart looks like from the outside: no
    # in-memory session dict exists anywhere, only the database file - a
    # brand new call to storage.get_session() must still find the session
    # that an earlier, unrelated request created.
    created = create_interview(question_count=2).json()
    reloaded = storage.get_session(created["session_id"])
    assert reloaded["role"] == "Software Engineer"
    assert len(reloaded["questions"]) == 2
