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


def create_interview(client, category="technical", difficulty="medium", question_count=2, **headers):
    return client.post(
        "/api/interviews",
        json={"role": "Backend Developer", "category": category, "difficulty": difficulty, "question_count": question_count},
        headers=headers,
    )


def complete_with_evaluation(client, monkeypatch, total_score, category="technical", **headers):
    created = create_interview(client, category=category, question_count=1, **headers).json()
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
    return session_id, question_id


# ---------- List endpoint: auth and ownership ----------

def test_list_requires_authentication(client):
    res = client.get("/api/interviews")
    assert res.status_code == 401


def test_authenticated_user_sees_only_their_own_interviews():
    client_a = TestClient(app)
    register(client_a, email="usera@example.com")
    create_interview(client_a, **csrf_headers(client_a))
    create_interview(client_a, **csrf_headers(client_a))

    client_b = TestClient(app)
    register(client_b, email="userb@example.com")
    create_interview(client_b, **csrf_headers(client_b))

    res_a = client_a.get("/api/interviews")
    body_a = res_a.json()
    assert res_a.status_code == 200
    assert body_a["total"] == 2
    assert len(body_a["interviews"]) == 2

    res_b = client_b.get("/api/interviews")
    assert res_b.json()["total"] == 1


def test_anonymous_interviews_excluded_from_everyones_history(client):
    anon = TestClient(app)
    create_interview(anon)  # no login at all

    register(client)
    res = client.get("/api/interviews")
    assert res.json()["total"] == 0
    assert res.json()["interviews"] == []


def test_empty_history_returns_sensible_response(client):
    register(client)
    res = client.get("/api/interviews")
    assert res.status_code == 200
    assert res.json() == {"interviews": [], "total": 0, "limit": 20, "offset": 0}


# ---------- Pagination and ordering ----------

def test_pagination_and_newest_first_ordering(client):
    register(client)
    headers = csrf_headers(client)
    first = create_interview(client, **headers).json()["session_id"]
    second = create_interview(client, **headers).json()["session_id"]
    third = create_interview(client, **headers).json()["session_id"]

    page1 = client.get("/api/interviews?limit=2&offset=0").json()
    assert page1["total"] == 3
    assert len(page1["interviews"]) == 2
    assert [i["session_id"] for i in page1["interviews"]] == [third, second]

    page2 = client.get("/api/interviews?limit=2&offset=2").json()
    assert [i["session_id"] for i in page2["interviews"]] == [first]


def test_limit_is_clamped_to_a_sane_maximum(client):
    register(client)
    res = client.get("/api/interviews?limit=99999")
    assert res.status_code == 200
    assert res.json()["limit"] <= 100


# ---------- Counts and averages ----------

def test_answered_and_evaluated_counts_are_correct(client):
    register(client)
    headers = csrf_headers(client)
    created = create_interview(client, question_count=2, **headers).json()
    session_id = created["session_id"]
    q1, q2 = created["questions"][0]["id"], created["questions"][1]["id"]
    client.post(f"/api/interviews/{session_id}/answers", json={"question_id": q1, "answer": "A1"}, headers=headers)

    res = client.get("/api/interviews").json()
    item = res["interviews"][0]
    assert item["question_count"] == 2
    assert item["answered_count"] == 1
    assert item["evaluated_count"] == 0
    assert item["average_score"] is None  # no evaluations yet - never 0


def test_average_score_uses_only_available_evaluations(client, monkeypatch):
    register(client)
    session_id, question_id = complete_with_evaluation(client, monkeypatch, 80, category="technical", **csrf_headers(client))
    res = client.get("/api/interviews").json()
    item = [i for i in res["interviews"] if i["session_id"] == session_id][0]
    assert item["evaluated_count"] == 1
    assert item["average_score"] == 80.0


# ---------- Detail endpoint includes evaluations ----------

def test_detail_endpoint_includes_evaluation_for_evaluated_question(client, monkeypatch):
    session_id, question_id = complete_with_evaluation(client, monkeypatch, 72)
    res = client.get(f"/api/interviews/{session_id}")
    assert res.status_code == 200
    question = [q for q in res.json()["questions"] if q["id"] == question_id][0]
    assert question["evaluation"] is not None
    assert question["evaluation"]["total_score"] == 72


def test_detail_endpoint_evaluation_is_null_when_not_evaluated(client):
    created = create_interview(client, question_count=1, **csrf_headers(client)).json()
    res = client.get(f"/api/interviews/{created['session_id']}")
    assert res.json()["questions"][0]["evaluation"] is None


def test_other_users_interview_detail_not_revealed():
    client_a = TestClient(app)
    register(client_a, email="usera2@example.com")
    created = create_interview(client_a, **csrf_headers(client_a)).json()

    client_b = TestClient(app)
    register(client_b, email="userb2@example.com")
    res = client_b.get(f"/api/interviews/{created['session_id']}")
    assert res.status_code == 404
    assert "role" not in res.json()  # no private fields leaked alongside the error


def test_unknown_interview_id_returns_same_404_as_inaccessible_one(client):
    register(client)
    res = client.get("/api/interviews/totally-unknown-id")
    assert res.status_code == 404


def test_second_interview_avoids_recently_asked_questions_when_logged_in(client):
    # End-to-end proof that create_interview() actually wires in
    # storage.get_recent_question_texts() (unit-tested directly in
    # test_storage.py) - with 15 technical/medium questions in the bank and
    # only 5 used by the first interview, 10 suitable alternatives remain,
    # so the second interview must not repeat any of the first's.
    register(client)
    first = create_interview(client, category="technical", difficulty="medium", question_count=5, **csrf_headers(client)).json()
    first_texts = {q["text"] for q in first["questions"]}

    second = create_interview(client, category="technical", difficulty="medium", question_count=5, **csrf_headers(client)).json()
    second_texts = {q["text"] for q in second["questions"]}

    assert not (first_texts & second_texts), "the second interview repeated a question from the first, even though 10 other suitable questions existed"


def test_anonymous_interviews_are_not_restricted_by_recent_question_history(client):
    # Anonymous sessions have no persistent identity to track recent
    # questions against (see storage.get_recent_question_texts), so this
    # must succeed normally rather than erroring - it simply isn't subject
    # to the exclusion feature at all.
    first = create_interview(client, category="technical", difficulty="medium", question_count=5).json()
    second = create_interview(client, category="technical", difficulty="medium", question_count=5).json()
    assert len(first["questions"]) == 5
    assert len(second["questions"]) == 5
