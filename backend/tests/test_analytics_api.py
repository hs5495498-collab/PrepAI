import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

import auth
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


def create_interview(client, category="technical", **headers):
    return client.post(
        "/api/interviews",
        json={"role": "Backend Developer", "category": category, "difficulty": "medium", "question_count": 1},
        headers=headers,
    )


def complete_with_evaluation(client, monkeypatch, total_score, category="technical", **headers):
    created = create_interview(client, category=category, **headers).json()
    session_id, question_id = created["session_id"], created["questions"][0]["id"]
    client.post(f"/api/interviews/{session_id}/answers", json={"question_id": question_id, "answer": "An answer."}, headers=headers)
    client.post(f"/api/interviews/{session_id}/complete", headers=headers)

    def fake_evaluate(role, cat, diff, question_text, answer_text):
        return {
            "relevance_score": 25, "correctness_score": 30, "completeness_score": 20, "clarity_score": 8,
            "total_score": total_score, "relevance_assessment": "ok", "correctness_assessment": "ok",
            "explanation": "ok", "strengths": ["x"], "weaknesses": ["y"], "suggestions": ["z"],
            "example_answer": None, "model": "gpt-4o-mini",
        }

    monkeypatch.setattr(main.evaluation_provider, "is_configured", lambda: True)
    monkeypatch.setattr(main.evaluation_provider, "evaluate_answer", fake_evaluate)
    client.post(f"/api/interviews/{session_id}/questions/{question_id}/evaluate", headers=headers)
    return session_id


def test_requires_authentication(client):
    res = client.get("/api/analytics")
    assert res.status_code == 401


def test_empty_account_gets_honest_empty_state(client):
    register(client)
    res = client.get("/api/analytics")
    assert res.status_code == 200
    body = res.json()
    assert body["total_interviews"] == 0
    assert body["average_score"] is None
    assert body["completion_rate"] is None
    assert body["progress"] == []


def test_one_users_data_never_affects_another_users_analytics(monkeypatch):
    client_a = TestClient(app)
    register(client_a, email="usera@example.com")
    complete_with_evaluation(client_a, monkeypatch, 30, category="technical", **csrf_headers(client_a))

    client_b = TestClient(app)
    register(client_b, email="userb@example.com")
    complete_with_evaluation(client_b, monkeypatch, 95, category="hr", **csrf_headers(client_b))

    body_a = client_a.get("/api/analytics").json()
    body_b = client_b.get("/api/analytics").json()
    assert body_a["average_score"] == 30.0
    assert body_b["average_score"] == 95.0
    assert "hr" not in body_a["by_category"]
    assert "technical" not in body_b["by_category"]


def test_anonymous_interview_not_counted_in_any_accounts_analytics(monkeypatch):
    anon = TestClient(app)
    complete_with_evaluation(anon, monkeypatch, 40)

    newcomer = TestClient(app)
    register(newcomer, email="newcomer@example.com")
    body = newcomer.get("/api/analytics").json()
    assert body["total_interviews"] == 0
    assert body["evaluated_answers"] == 0


def test_response_includes_recognizable_fields(monkeypatch):
    client = TestClient(app)
    register(client)
    complete_with_evaluation(client, monkeypatch, 85, **csrf_headers(client))
    body = client.get("/api/analytics").json()
    assert body["average_score"] == 85.0
    assert body["highest_score"] == 85
    assert body["most_recent_score"] == 85
    assert "technical" in body["by_category"]
    assert set(body["by_dimension"].keys()) == {
        "relevance_score", "correctness_score", "completeness_score", "clarity_score"
    }
