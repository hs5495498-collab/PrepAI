"""Tests for default/automatic evaluation on interview completion and the
derived overall-interview score out of 100 (see main.py's
_auto_evaluate_session, _evaluate_one_question, _score_summary).

Per-question provider validation, error handling, and timeout behavior are
already exhaustively covered in test_evaluation_provider.py; idempotency,
ownership, and CSRF for the manual per-question endpoint are covered in
test_evaluation_api.py. This file covers what's new this sprint: the
automatic trigger on /complete, the aggregation rule, partial-failure
honesty, and that the feature is a true no-op when disabled (the default -
no .env file exists in this test run, so AI_EVALUATION_ENABLED is never
actually true here; every "enabled" scenario below uses a mocked provider,
never a real network call).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

import auth
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


def create_interview(client, question_count=3, category="technical", **headers):
    return client.post(
        "/api/interviews",
        json={"role": "Backend Developer", "category": category, "difficulty": "medium", "question_count": question_count},
        headers=headers,
    )


def answer_all(client, session_id, questions, answer_text="A real, substantive answer about the topic.", **headers):
    for q in questions:
        client.post(f"/api/interviews/{session_id}/answers", json={"question_id": q["id"], "answer": answer_text}, headers=headers)


def fixed_fake_evaluate(score_by_question=None, default_score=70, calls=None):
    def fake(role, category, difficulty, question_text, answer_text):
        if calls is not None:
            calls.append((question_text, answer_text))
        score = (score_by_question or {}).get(question_text, default_score)
        return {
            # Dimensions deliberately do NOT sum to `score` - proves the
            # completion summary trusts evaluation_provider's own already-
            # validated total_score field rather than re-deriving it.
            "relevance_score": 20, "correctness_score": 25, "completeness_score": 18, "clarity_score": 7,
            "total_score": score, "relevance_assessment": "ok", "correctness_assessment": "ok",
            "explanation": "ok", "strengths": ["x"], "weaknesses": ["y"], "suggestions": ["z"],
            "example_answer": None, "model": "gpt-4o-mini",
        }
    return fake


# ---------- Disabled (the default): a true no-op ----------

def test_completion_with_evaluation_disabled_is_unaffected(client):
    created = create_interview(client, question_count=2).json()
    session_id = created["session_id"]
    answer_all(client, session_id, created["questions"])
    res = client.post(f"/api/interviews/{session_id}/complete")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "completed"
    assert body["evaluation_status"] == "not_configured"
    assert body["overall_score"] is None
    assert body["evaluated_count"] == 0
    assert all(q["evaluation"] is None for q in body["questions"])


# ---------- Enabled: every answered question gets evaluated ----------

def test_completion_with_evaluation_enabled_evaluates_every_answered_question(monkeypatch):
    client = TestClient(app)
    created = create_interview(client, question_count=3).json()
    session_id = created["session_id"]
    answer_all(client, session_id, created["questions"])

    calls = []
    monkeypatch.setattr(main.evaluation_provider, "is_configured", lambda: True)
    monkeypatch.setattr(main.evaluation_provider, "evaluate_answer", fixed_fake_evaluate(default_score=80, calls=calls))

    res = client.post(f"/api/interviews/{session_id}/complete")
    assert res.status_code == 200
    body = res.json()
    assert body["evaluation_status"] == "complete"
    assert body["evaluated_count"] == 3
    assert body["overall_score"] == 80.0
    assert all(q["evaluation"] is not None and q["evaluation"]["total_score"] == 80 for q in body["questions"])
    assert len(calls) == 3  # one real call per answered question, no more


def test_short_answer_score_is_never_adjusted_by_length(monkeypatch):
    # Proves the aggregation trusts whatever the (mocked) provider decided -
    # a short answer scored low by the provider stays low; this code never
    # applies its own length-based heuristic on top.
    client = TestClient(app)
    created = create_interview(client, question_count=1).json()
    session_id = created["session_id"]
    question_id = created["questions"][0]["id"]
    client.post(f"/api/interviews/{session_id}/answers", json={"question_id": question_id, "answer": "idk"})

    monkeypatch.setattr(main.evaluation_provider, "is_configured", lambda: True)
    monkeypatch.setattr(main.evaluation_provider, "evaluate_answer", fixed_fake_evaluate(default_score=8))
    body = client.post(f"/api/interviews/{session_id}/complete").json()
    assert body["overall_score"] == 8.0


# ---------- Overall score aggregation rule: arithmetic mean, rounded ----------

def test_overall_score_is_the_mean_of_evaluated_question_scores(monkeypatch):
    client = TestClient(app)
    created = create_interview(client, question_count=3).json()
    session_id = created["session_id"]
    questions = created["questions"]
    answer_all(client, session_id, questions)

    scores = {questions[0]["text"]: 60, questions[1]["text"]: 81, questions[2]["text"]: 100}
    monkeypatch.setattr(main.evaluation_provider, "is_configured", lambda: True)
    monkeypatch.setattr(main.evaluation_provider, "evaluate_answer", fixed_fake_evaluate(score_by_question=scores))

    body = client.post(f"/api/interviews/{session_id}/complete").json()
    assert body["overall_score"] == round((60 + 81 + 100) / 3, 1)  # 80.3
    assert body["evaluation_status"] == "complete"


# ---------- Partial failure: honest, never destroys completion ----------

def test_partial_provider_failure_still_completes_and_reports_partial_status(monkeypatch):
    client = TestClient(app)
    created = create_interview(client, question_count=3).json()
    session_id = created["session_id"]
    questions = created["questions"]
    answer_all(client, session_id, questions)
    fail_text = questions[1]["text"]

    def flaky_evaluate(role, category, difficulty, question_text, answer_text):
        if question_text == fail_text:
            raise evaluation_provider.EvaluationProviderUnavailable("simulated outage")
        return fixed_fake_evaluate(default_score=70)(role, category, difficulty, question_text, answer_text)

    monkeypatch.setattr(main.evaluation_provider, "is_configured", lambda: True)
    monkeypatch.setattr(main.evaluation_provider, "evaluate_answer", flaky_evaluate)

    res = client.post(f"/api/interviews/{session_id}/complete")
    assert res.status_code == 200  # a provider outage never fails completion itself
    body = res.json()
    assert body["status"] == "completed"  # the session is still genuinely completed
    assert body["evaluation_status"] == "partial"
    assert body["evaluated_count"] == 2
    assert body["overall_score"] == 70.0  # only the 2 successes - the failure is never counted as 0
    failed_q = [q for q in body["questions"] if q["text"] == fail_text][0]
    assert failed_q["evaluation"] is None


def test_all_evaluations_failing_leaves_a_genuinely_completed_unscored_interview(monkeypatch):
    client = TestClient(app)
    created = create_interview(client, question_count=2).json()
    session_id = created["session_id"]
    answer_all(client, session_id, created["questions"])

    def always_fail(role, category, difficulty, question_text, answer_text):
        raise evaluation_provider.EvaluationProviderTimeout("simulated timeout")

    monkeypatch.setattr(main.evaluation_provider, "is_configured", lambda: True)
    monkeypatch.setattr(main.evaluation_provider, "evaluate_answer", always_fail)

    res = client.post(f"/api/interviews/{session_id}/complete")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "completed"  # answers are never lost or the completion undone
    assert body["evaluation_status"] == "not_evaluated"
    assert body["overall_score"] is None
    assert body["evaluated_count"] == 0


# ---------- Retry after a transient failure, via the existing manual endpoint ----------

def test_failed_question_can_be_retried_after_completion(monkeypatch):
    client = TestClient(app)
    created = create_interview(client, question_count=1).json()
    session_id = created["session_id"]
    question_id = created["questions"][0]["id"]
    client.post(f"/api/interviews/{session_id}/answers", json={"question_id": question_id, "answer": "An answer."})

    def always_fail(role, category, difficulty, question_text, answer_text):
        raise evaluation_provider.EvaluationProviderTimeout("simulated timeout")

    monkeypatch.setattr(main.evaluation_provider, "is_configured", lambda: True)
    monkeypatch.setattr(main.evaluation_provider, "evaluate_answer", always_fail)
    first = client.post(f"/api/interviews/{session_id}/complete").json()
    assert first["evaluation_status"] == "not_evaluated"

    # Provider recovers; retrying via the existing per-question endpoint
    # must still work on an already-completed interview.
    monkeypatch.setattr(main.evaluation_provider, "evaluate_answer", fixed_fake_evaluate(default_score=90))
    retry = client.post(f"/api/interviews/{session_id}/questions/{question_id}/evaluate")
    assert retry.status_code == 200
    assert retry.json()["total_score"] == 90

    final = client.get(f"/api/interviews/{session_id}").json()
    assert final["evaluation_status"] == "complete"
    assert final["overall_score"] == 90.0


# ---------- No duplicate evaluation on refresh or re-completion ----------

def test_no_duplicate_evaluation_on_results_page_refresh_or_recompletion(monkeypatch):
    client = TestClient(app)
    created = create_interview(client, question_count=1).json()
    session_id = created["session_id"]
    question_id = created["questions"][0]["id"]
    client.post(f"/api/interviews/{session_id}/answers", json={"question_id": question_id, "answer": "An answer."})

    calls = []
    monkeypatch.setattr(main.evaluation_provider, "is_configured", lambda: True)
    monkeypatch.setattr(main.evaluation_provider, "evaluate_answer", fixed_fake_evaluate(calls=calls))
    client.post(f"/api/interviews/{session_id}/complete")
    assert len(calls) == 1

    # A results-page refresh is a plain GET (renderBackendSession()'s own
    # call) - must never re-trigger the provider.
    client.get(f"/api/interviews/{session_id}")
    client.get(f"/api/interviews/{session_id}")
    assert len(calls) == 1

    # A second /complete attempt is already rejected (pre-existing
    # AlreadyCompleted behavior) and must still never re-call the provider.
    second = client.post(f"/api/interviews/{session_id}/complete")
    assert second.status_code == 409
    assert len(calls) == 1


# ---------- GET and completion report the exact same derived summary ----------

def test_get_interview_reflects_same_overall_score_as_completion_response(monkeypatch):
    client = TestClient(app)
    created = create_interview(client, question_count=2).json()
    session_id = created["session_id"]
    answer_all(client, session_id, created["questions"])

    monkeypatch.setattr(main.evaluation_provider, "is_configured", lambda: True)
    monkeypatch.setattr(main.evaluation_provider, "evaluate_answer", fixed_fake_evaluate(default_score=65))
    complete_body = client.post(f"/api/interviews/{session_id}/complete").json()
    get_body = client.get(f"/api/interviews/{session_id}").json()
    assert complete_body["overall_score"] == get_body["overall_score"] == 65.0
    assert complete_body["evaluation_status"] == get_body["evaluation_status"] == "complete"
    assert complete_body["evaluated_count"] == get_body["evaluated_count"] == 2


# ---------- Unanswered questions are never force-evaluated ----------

def test_unanswered_questions_are_never_evaluated_or_counted(monkeypatch):
    client = TestClient(app)
    created = create_interview(client, question_count=3).json()
    session_id = created["session_id"]
    questions = created["questions"]
    # Only answer 2 of the 3 questions, then end/complete early.
    answer_all(client, session_id, questions[:2])

    monkeypatch.setattr(main.evaluation_provider, "is_configured", lambda: True)
    monkeypatch.setattr(main.evaluation_provider, "evaluate_answer", fixed_fake_evaluate(default_score=75))
    body = client.post(f"/api/interviews/{session_id}/complete").json()
    assert body["answered_count"] == 2
    assert body["evaluated_count"] == 2  # never 3 - the unanswered question is skipped, not evaluated
    assert body["evaluation_status"] == "complete"  # complete relative to what was actually answered
    unanswered = [q for q in body["questions"] if q["answer"] is None][0]
    assert unanswered["evaluation"] is None


# ---------- Account isolation for the new auto-evaluation path ----------

def test_auto_evaluation_never_leaks_between_accounts(monkeypatch):
    client_a, client_b = TestClient(app), TestClient(app)
    register(client_a, email="autoeval-a@example.com")
    register(client_b, email="autoeval-b@example.com")

    created_a = create_interview(client_a, question_count=1, **csrf_headers(client_a)).json()
    created_b = create_interview(client_b, question_count=1, **csrf_headers(client_b)).json()
    client_a.post(
        f"/api/interviews/{created_a['session_id']}/answers",
        json={"question_id": created_a["questions"][0]["id"], "answer": "Account A's answer."},
        headers=csrf_headers(client_a),
    )
    client_b.post(
        f"/api/interviews/{created_b['session_id']}/answers",
        json={"question_id": created_b["questions"][0]["id"], "answer": "Account B's answer."},
        headers=csrf_headers(client_b),
    )

    monkeypatch.setattr(main.evaluation_provider, "is_configured", lambda: True)
    monkeypatch.setattr(main.evaluation_provider, "evaluate_answer", fixed_fake_evaluate(default_score=55))
    client_a.post(f"/api/interviews/{created_a['session_id']}/complete", headers=csrf_headers(client_a))

    # B hasn't completed anything yet - B's own analytics must show nothing,
    # and B must not be able to read A's evaluated interview.
    b_analytics = client_b.get("/api/analytics").json()
    assert b_analytics["evaluated_answers"] == 0

    cross_read = client_b.get(f"/api/interviews/{created_a['session_id']}")
    assert cross_read.status_code == 404
