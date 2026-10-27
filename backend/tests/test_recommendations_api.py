import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

import auth
import db
import main
from main import app


@pytest.fixture
def client():
    return TestClient(app)


def register(client, email="alice@example.com", password="correct-horse-1"):
    return client.post("/api/auth/register", json={"email": email, "password": password})


def csrf_headers(client):
    token = client.cookies.get(auth.CSRF_COOKIE_NAME)
    return {"X-CSRF-Token": token} if token else {}


def create_interview(client, category="technical", difficulty="medium", **headers):
    return client.post(
        "/api/interviews",
        json={"role": "Backend Developer", "category": category, "difficulty": difficulty, "question_count": 2},
        headers=headers,
    )


def complete_with_evaluation(client, monkeypatch, total_score, category="technical", difficulty="medium", **headers):
    """Creates an interview, answers it, then completes it with AI
    evaluation mocked on *before* completion - this is the only way to get
    a row into the evaluations table through the real API via the real
    auto-evaluation-on-completion path (main.py's _auto_evaluate_session),
    so recommendation tests exercise the actual persisted data path, not a
    shortcut. Reverts is_configured to False immediately after, so a later
    plain create+complete call sharing this same monkeypatch fixture is
    never affected by this mock leaking forward."""
    created = create_interview(client, category=category, difficulty=difficulty, **headers).json()
    session_id, question_id = created["session_id"], created["questions"][0]["id"]
    client.post(
        f"/api/interviews/{session_id}/answers",
        json={"question_id": question_id, "answer": "An answer."}, headers=headers,
    )

    def fake_evaluate(role, cat, diff, question_text, answer_text):
        return {
            "relevance_score": 25, "correctness_score": 30, "completeness_score": 20, "clarity_score": 8,
            "total_score": total_score, "relevance_assessment": "ok", "correctness_assessment": "ok",
            "explanation": "ok", "strengths": ["x"], "weaknesses": ["y"], "suggestions": ["z"],
            "example_answer": None, "model": "gpt-4o-mini",
        }

    monkeypatch.setattr(main.evaluation_provider, "is_configured", lambda: True)
    monkeypatch.setattr(main.evaluation_provider, "evaluate_answer", fake_evaluate)
    client.post(f"/api/interviews/{session_id}/complete", headers=headers)
    monkeypatch.setattr(main.evaluation_provider, "is_configured", lambda: False)
    return session_id


# ---------- Authentication ----------

def test_unauthenticated_request_rejected(client):
    res = client.get("/api/recommendations")
    assert res.status_code == 401


def test_authenticated_user_with_no_data_gets_generic_recommendation(client):
    register(client)
    res = client.get("/api/recommendations")
    assert res.status_code == 200
    body = res.json()
    assert body["completed_interviews"] == 0
    assert body["evaluated_answers"] == 0
    assert len(body["recommendations"]) == 1
    assert body["recommendations"][0]["key"] == "start_first_interview"
    assert body["recommendations"][0]["evidence_level"] == "generic"


# ---------- Ownership / privacy ----------

def test_user_sees_only_their_own_interviews_and_evaluations(monkeypatch):
    client_a = TestClient(app)
    register(client_a, email="usera@example.com")
    complete_with_evaluation(client_a, monkeypatch, 40, category="technical", **csrf_headers(client_a))

    client_b = TestClient(app)
    register(client_b, email="userb@example.com")
    complete_with_evaluation(client_b, monkeypatch, 90, category="hr", **csrf_headers(client_b))
    complete_with_evaluation(client_b, monkeypatch, 90, category="hr", **csrf_headers(client_b))
    complete_with_evaluation(client_b, monkeypatch, 90, category="hr", **csrf_headers(client_b))

    res_a = client_a.get("/api/recommendations")
    body_a = res_a.json()
    assert body_a["completed_interviews"] == 1
    assert body_a["evaluated_answers"] == 1
    # Only A's own (weak, single-sample) technical result should ever
    # influence A's recommendations - never B's strong HR results.
    assert not any(r["category"] == "hr" for r in body_a["recommendations"])

    res_b = client_b.get("/api/recommendations")
    body_b = res_b.json()
    assert body_b["completed_interviews"] == 3
    assert body_b["evaluated_answers"] == 3
    assert not any(r["category"] == "technical" for r in body_b["recommendations"])


def test_anonymous_interview_is_not_attributed_to_any_account(monkeypatch):
    anon = TestClient(app)
    complete_with_evaluation(anon, monkeypatch, 40, category="technical")

    newcomer = TestClient(app)
    register(newcomer, email="newcomer@example.com")
    res = newcomer.get("/api/recommendations")
    body = res.json()
    assert body["completed_interviews"] == 0
    assert body["evaluated_answers"] == 0
    assert body["recommendations"][0]["key"] == "start_first_interview"


# ---------- Safety / error handling ----------

def test_database_error_does_not_leak_sql_details(monkeypatch):
    def broken(user_id):
        raise sqlite3.OperationalError("database is locked: /some/internal/path.db")

    monkeypatch.setattr(main.storage, "get_user_recommendation_data", broken)
    client = TestClient(app)
    register(client)

    safe_client = TestClient(app, raise_server_exceptions=False)
    for name, value in client.cookies.items():
        safe_client.cookies.set(name, value)
    res = safe_client.get("/api/recommendations")
    assert res.status_code == 500
    text = res.text
    assert "database is locked" not in text
    assert "sqlite3" not in text
    assert res.json() == {"error": "Internal server error."}


def test_unusual_but_valid_category_difficulty_combination_does_not_crash(monkeypatch):
    client = TestClient(app)
    register(client)
    complete_with_evaluation(client, monkeypatch, 92, category="behavioral", difficulty="hard", **csrf_headers(client))
    res = client.get("/api/recommendations")
    assert res.status_code == 200
    assert isinstance(res.json()["recommendations"], list)


def test_response_never_includes_password_or_session_fields(monkeypatch):
    client = TestClient(app)
    register(client)
    complete_with_evaluation(client, monkeypatch, 40, **csrf_headers(client))
    res = client.get("/api/recommendations")
    text = res.text.lower()
    assert "password" not in text
    assert "csrf_token" not in text
    assert "session" not in text or "session" not in res.json()
