import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

import auth
import db
import evaluation_provider
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


def create_interview(client, **headers):
    return client.post(
        "/api/interviews",
        json={"role": "Backend Developer", "category": "technical", "difficulty": "medium", "question_count": 2},
        headers=headers,
    )


def create_and_answer(client, answer="I would use a hash set for O(1) average lookups.", **headers):
    created = create_interview(client, **headers).json()
    session_id, question_id = created["session_id"], created["questions"][0]["id"]
    client.post(
        f"/api/interviews/{session_id}/answers",
        json={"question_id": question_id, "answer": answer},
        headers=headers,
    )
    return session_id, question_id


def enable_evaluation_with_fake_result(monkeypatch, result=None, calls=None):
    result = result or {
        "relevance_score": 25, "correctness_score": 30, "completeness_score": 20, "clarity_score": 8,
        "total_score": 83, "relevance_assessment": "On topic.", "correctness_assessment": "Accurate.",
        "explanation": "Solid answer.", "strengths": ["Clear"], "weaknesses": ["Could be shorter"],
        "suggestions": ["Trim it down"], "example_answer": None, "model": "gpt-4o-mini",
    }

    def fake_evaluate(role, category, difficulty, question_text, answer_text):
        if calls is not None:
            calls.append((question_text, answer_text))
        return dict(result)

    monkeypatch.setattr(main.evaluation_provider, "is_configured", lambda: True)
    monkeypatch.setattr(main.evaluation_provider, "evaluate_answer", fake_evaluate)
    return result


# ---------- Feature disabled / not configured ----------

def test_evaluation_disabled_by_default(client):
    session_id, question_id = create_and_answer(client)
    res = client.post(f"/api/interviews/{session_id}/questions/{question_id}/evaluate")
    assert res.status_code == 503


# ---------- Validation: unanswered / unknown session or question ----------

def test_evaluating_unanswered_question_rejected(client, monkeypatch):
    calls = []
    enable_evaluation_with_fake_result(monkeypatch, calls=calls)
    created = create_interview(client).json()
    session_id, question_id = created["session_id"], created["questions"][0]["id"]
    res = client.post(f"/api/interviews/{session_id}/questions/{question_id}/evaluate")
    assert res.status_code == 409
    assert calls == []  # the provider must never be called for an unanswered question


def test_evaluate_unknown_session_rejected(client):
    res = client.post("/api/interviews/does-not-exist/questions/q1/evaluate")
    assert res.status_code == 404


def test_evaluate_unknown_question_rejected(client, monkeypatch):
    enable_evaluation_with_fake_result(monkeypatch)
    session_id, _question_id = create_and_answer(client)
    res = client.post(f"/api/interviews/{session_id}/questions/not-a-real-question/evaluate")
    assert res.status_code == 404


def test_question_from_a_different_interview_is_not_cross_evaluated(monkeypatch):
    # Interview A and interview B both legitimately use the local id "q1"
    # for their own first question - evaluating B's "q1" must only ever
    # look at B's own question/answer, never leak or reuse A's.
    enable_evaluation_with_fake_result(monkeypatch)
    client_a, client_b = TestClient(app), TestClient(app)
    session_a, question_a = create_and_answer(client_a, answer="Answer belonging to interview A.")
    created_b = create_interview(client_b).json()
    session_b, question_b = created_b["session_id"], created_b["questions"][0]["id"]
    assert question_a == question_b == "q1"

    # B's question is deliberately left unanswered.
    res = client_b.post(f"/api/interviews/{session_b}/questions/{question_b}/evaluate")
    assert res.status_code == 409  # unanswered in B, regardless of A's state

    # A fabricated id that exists nowhere is still a clean 404.
    res2 = client_a.post(f"/api/interviews/{session_a}/questions/does-not-exist-here/evaluate")
    assert res2.status_code == 404


# ---------- Successful evaluation and persistence ----------

def test_successful_evaluation_returns_full_structured_result(monkeypatch):
    result = enable_evaluation_with_fake_result(monkeypatch)
    client = TestClient(app)
    session_id, question_id = create_and_answer(client)

    res = client.post(f"/api/interviews/{session_id}/questions/{question_id}/evaluate")
    assert res.status_code == 200
    body = res.json()
    assert body["session_id"] == session_id
    assert body["question_id"] == question_id
    assert body["total_score"] == result["total_score"]
    assert body["relevance_score"] == 25
    assert body["correctness_score"] == 30
    assert body["completeness_score"] == 20
    assert body["clarity_score"] == 8
    assert body["strengths"] == ["Clear"]
    assert body["weaknesses"] == ["Could be shorter"]
    assert body["suggestions"] == ["Trim it down"]
    assert body["example_answer"] is None
    assert "estimate" in body["note"].lower()  # never claims to be an objective measurement


def test_evaluation_persists_after_reopening_the_database(monkeypatch):
    enable_evaluation_with_fake_result(monkeypatch)
    client = TestClient(app)
    session_id, question_id = create_and_answer(client)
    client.post(f"/api/interviews/{session_id}/questions/{question_id}/evaluate")

    # A brand-new connection, independent of anything the app has open -
    # simulates reading the data back after a restart.
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT * FROM evaluations WHERE interview_id = ? AND question_id = ?", (session_id, question_id)
        ).fetchone()
        assert row is not None
        assert row["total_score"] == 83
    finally:
        conn.close()

    reloaded = storage_get_evaluation(session_id, question_id)
    assert reloaded is not None
    assert reloaded["total_score"] == 83


def storage_get_evaluation(session_id, question_id):
    import storage
    return storage.get_evaluation(session_id, question_id)


# ---------- Idempotency ----------

def test_duplicate_evaluation_request_does_not_call_provider_twice(monkeypatch):
    calls = []
    enable_evaluation_with_fake_result(monkeypatch, calls=calls)
    client = TestClient(app)
    session_id, question_id = create_and_answer(client)

    first = client.post(f"/api/interviews/{session_id}/questions/{question_id}/evaluate")
    second = client.post(f"/api/interviews/{session_id}/questions/{question_id}/evaluate")
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert len(calls) == 1  # the provider was only ever actually called once


# ---------- Failure does not create a false success ----------

def test_failed_evaluation_does_not_persist_a_record(monkeypatch):
    def fake_fail(role, category, difficulty, question_text, answer_text):
        raise evaluation_provider.EvaluationProviderUnavailable("down")

    monkeypatch.setattr(main.evaluation_provider, "is_configured", lambda: True)
    monkeypatch.setattr(main.evaluation_provider, "evaluate_answer", fake_fail)
    client = TestClient(app)
    session_id, question_id = create_and_answer(client)

    res = client.post(f"/api/interviews/{session_id}/questions/{question_id}/evaluate")
    assert res.status_code == 503

    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT * FROM evaluations WHERE interview_id = ? AND question_id = ?", (session_id, question_id)
        ).fetchone()
        assert row is None
    finally:
        conn.close()


# ---------- Authentication, ownership, CSRF ----------

def test_anonymous_can_evaluate_an_unowned_interview(monkeypatch):
    # Preserves the existing anonymous/offline demo policy - no account is
    # invented or required just to use evaluation on an anonymous interview.
    enable_evaluation_with_fake_result(monkeypatch)
    anon = TestClient(app)
    session_id, question_id = create_and_answer(anon)
    res = anon.post(f"/api/interviews/{session_id}/questions/{question_id}/evaluate")
    assert res.status_code == 200


def test_user_a_cannot_evaluate_user_bs_interview(monkeypatch):
    enable_evaluation_with_fake_result(monkeypatch)
    client_a = TestClient(app)
    register(client_a, email="usera@example.com")
    session_id, question_id = create_and_answer(client_a, **csrf_headers(client_a))

    client_b = TestClient(app)
    register(client_b, email="userb@example.com")
    res = client_b.post(
        f"/api/interviews/{session_id}/questions/{question_id}/evaluate", headers=csrf_headers(client_b)
    )
    assert res.status_code == 404

    # And no evaluation was recorded by the intrusion attempt.
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT * FROM evaluations WHERE interview_id = ? AND question_id = ?", (session_id, question_id)
        ).fetchone()
        assert row is None
    finally:
        conn.close()


def test_evaluate_requires_csrf_header_when_authenticated(monkeypatch):
    enable_evaluation_with_fake_result(monkeypatch)
    client = TestClient(app)
    register(client)
    session_id, question_id = create_and_answer(client, **csrf_headers(client))

    res = client.post(f"/api/interviews/{session_id}/questions/{question_id}/evaluate")  # no CSRF header
    assert res.status_code == 403


def test_logged_in_owner_can_evaluate_their_own_interview(monkeypatch):
    enable_evaluation_with_fake_result(monkeypatch)
    client = TestClient(app)
    register(client)
    session_id, question_id = create_and_answer(client, **csrf_headers(client))

    res = client.post(f"/api/interviews/{session_id}/questions/{question_id}/evaluate", headers=csrf_headers(client))
    assert res.status_code == 200
