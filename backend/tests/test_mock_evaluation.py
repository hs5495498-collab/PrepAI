"""Tests for the development-only mock (simulated) answer-evaluation mode
(see evaluation_provider.py's is_mock_enabled()/_mock_evaluate_answer()).

This mode exists so the full interview workflow - results page, overall
score, history, analytics - can be exercised without an OpenAI API key and
without ever making a real network call. Every test below either asserts
no network call happens (the mock path never constructs an httpx.Client)
or explicitly disables the feature and checks the real-provider code path
is never reached either, so this file makes zero external API calls.

Covers: deterministic (never random) scoring and feedback, reuse of the
exact same persistence/overall-score pipeline the real provider uses,
clear SIMULATED labeling in both API response shapes (EvaluationOut and
the nested QuestionEvaluationOut), disabled-by-default behavior, and the
production-safety gate (MOCK_EVALUATION_ENABLED is refused once
ENVIRONMENT names a production deployment, and whenever the real
provider is already configured)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

import evaluation_provider
import main
from main import app


@pytest.fixture
def client():
    return TestClient(app)


def create_interview(client, question_count=2, **headers):
    return client.post(
        "/api/interviews",
        json={"role": "Backend Developer", "category": "technical", "difficulty": "medium", "question_count": question_count},
        headers=headers,
    )


def create_and_answer(client, answer="A reasonably detailed answer about the topic at hand.", question_count=2):
    created = create_interview(client, question_count=question_count).json()
    session_id = created["session_id"]
    for q in created["questions"]:
        client.post(f"/api/interviews/{session_id}/answers", json={"question_id": q["id"], "answer": answer})
    return session_id, created["questions"]


def clear_real_provider_env(monkeypatch):
    monkeypatch.delenv("AI_EVALUATION_ENABLED", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def clear_mock_env(monkeypatch):
    monkeypatch.delenv("MOCK_EVALUATION_ENABLED", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)


@pytest.fixture(autouse=True)
def clean_evaluation_env(monkeypatch):
    """Every test here starts from a known-clean slate for all four env
    vars that control which evaluation path (none/mock/real) is active,
    regardless of whatever a developer's own backend/.env happens to set -
    each test then opts in to exactly the combination it wants to check."""
    clear_real_provider_env(monkeypatch)
    clear_mock_env(monkeypatch)
    yield


# ---------- Unit: is_mock_enabled() / is_configured() gating ----------

def test_mock_disabled_by_default(monkeypatch):
    assert evaluation_provider.is_mock_enabled() is False
    assert evaluation_provider.is_configured() is False


def test_mock_enabled_with_explicit_flag(monkeypatch):
    monkeypatch.setenv("MOCK_EVALUATION_ENABLED", "true")
    assert evaluation_provider.is_mock_enabled() is True
    assert evaluation_provider.is_configured() is True


@pytest.mark.parametrize("env_value", ["production", "Production", "PROD", "prod"])
def test_mock_cannot_be_enabled_in_production(monkeypatch, env_value):
    monkeypatch.setenv("MOCK_EVALUATION_ENABLED", "true")
    monkeypatch.setenv("ENVIRONMENT", env_value)
    assert evaluation_provider.is_mock_enabled() is False
    # Real provider is also unset in this test, so nothing is configured -
    # mock being refused must not accidentally fall back to "configured".
    assert evaluation_provider.is_configured() is False


def test_mock_enabled_explicitly_in_development(monkeypatch):
    monkeypatch.setenv("MOCK_EVALUATION_ENABLED", "true")
    monkeypatch.setenv("ENVIRONMENT", "development")
    assert evaluation_provider.is_mock_enabled() is True


def test_real_provider_takes_priority_over_mock(monkeypatch):
    """A working real configuration must never be silently replaced by
    mock results - see evaluation_provider.is_mock_enabled()'s docstring."""
    monkeypatch.setenv("MOCK_EVALUATION_ENABLED", "true")
    monkeypatch.setenv("AI_EVALUATION_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    assert evaluation_provider.is_mock_enabled() is False
    assert evaluation_provider.is_configured() is True  # still configured, just via the real path


def test_evaluate_answer_raises_not_configured_when_mock_and_real_both_off(monkeypatch):
    with pytest.raises(evaluation_provider.EvaluationProviderNotConfigured):
        evaluation_provider.evaluate_answer("Backend Developer", "technical", "medium", "Q?", "An answer.")


def test_evaluate_answer_raises_not_configured_when_mock_blocked_in_production(monkeypatch):
    monkeypatch.setenv("MOCK_EVALUATION_ENABLED", "true")
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(evaluation_provider.EvaluationProviderNotConfigured):
        evaluation_provider.evaluate_answer("Backend Developer", "technical", "medium", "Q?", "An answer.")


# ---------- Unit: deterministic mock scoring and labeling ----------

def test_mock_evaluation_shape_and_score_calculation(monkeypatch):
    monkeypatch.setenv("MOCK_EVALUATION_ENABLED", "true")
    result = evaluation_provider.evaluate_answer(
        "Backend Developer", "technical", "medium",
        "How would you find duplicates in a large list?",
        "I would use a hash set to track seen items in a single O(n) pass.",
    )
    for name, maximum in evaluation_provider.SCORE_WEIGHTS.items():
        assert 0 <= result[name] <= maximum
    # Same overall-score calculation as the real provider: the total is the
    # server-computed sum of the four dimension scores, never a separate
    # or model-reported figure.
    assert result["total_score"] == sum(result[name] for name in evaluation_provider.SCORE_WEIGHTS)
    assert result["model"] == evaluation_provider.MOCK_MODEL_NAME
    for field in ("relevance_assessment", "correctness_assessment", "explanation"):
        assert "SIMULATED" in result[field] and "NOT AI-GENERATED" in result[field]
    assert result["strengths"] and result["weaknesses"] and result["suggestions"]
    assert result["example_answer"] is None


def test_mock_evaluation_is_deterministic_not_random(monkeypatch):
    monkeypatch.setenv("MOCK_EVALUATION_ENABLED", "true")
    args = ("Backend Developer", "technical", "medium", "Explain hash maps.", "A short but specific answer about hashing.")
    first = evaluation_provider.evaluate_answer(*args)
    second = evaluation_provider.evaluate_answer(*args)
    assert first["total_score"] == second["total_score"]
    assert first["relevance_score"] == second["relevance_score"]
    assert first["correctness_score"] == second["correctness_score"]
    assert first["completeness_score"] == second["completeness_score"]
    assert first["clarity_score"] == second["clarity_score"]


def test_mock_evaluation_rewards_longer_more_substantive_answers(monkeypatch):
    monkeypatch.setenv("MOCK_EVALUATION_ENABLED", "true")
    short = evaluation_provider.evaluate_answer("Backend Developer", "technical", "medium", "Q?", "Yes.")
    long = evaluation_provider.evaluate_answer(
        "Backend Developer", "technical", "medium", "Q?",
        "I would use a hash set to track which items have already been seen while iterating "
        "through the list once, giving O(n) time and O(n) extra space, and I would mention the "
        "trade-off against sorting first if memory is constrained.",
    )
    assert long["total_score"] >= short["total_score"]


def test_mock_evaluation_never_calls_the_network(monkeypatch):
    """A client explicitly injected as None must still never be swapped for
    a real httpx.Client when mock mode is on - the mock path returns
    before any httpx usage is reached."""
    monkeypatch.setenv("MOCK_EVALUATION_ENABLED", "true")

    class ExplodingClient:
        def post(self, *a, **kw):
            raise AssertionError("mock mode must never make an HTTP request")

    result = evaluation_provider.evaluate_answer(
        "Backend Developer", "technical", "medium", "Q?", "An answer.", client=ExplodingClient(),
    )
    assert result["model"] == evaluation_provider.MOCK_MODEL_NAME


# ---------- API: manual per-question evaluate endpoint ----------

def test_evaluate_endpoint_disabled_by_default(client):
    session_id, questions = create_and_answer(client, question_count=1)
    res = client.post(f"/api/interviews/{session_id}/questions/{questions[0]['id']}/evaluate")
    assert res.status_code == 503


def test_evaluate_endpoint_returns_labeled_simulated_result(client, monkeypatch):
    monkeypatch.setenv("MOCK_EVALUATION_ENABLED", "true")
    session_id, questions = create_and_answer(client, question_count=1)
    res = client.post(f"/api/interviews/{session_id}/questions/{questions[0]['id']}/evaluate")
    assert res.status_code == 200
    body = res.json()
    assert body["model"] == "mock-simulated-v1"
    assert body["is_simulated"] is True
    assert "SIMULATED" in body["note"] and "NOT AI-GENERATED" in body["note"]
    assert body["total_score"] == sum(body[k] for k in ("relevance_score", "correctness_score", "completeness_score", "clarity_score"))


def test_evaluate_endpoint_blocked_in_production_even_if_requested(client, monkeypatch):
    monkeypatch.setenv("MOCK_EVALUATION_ENABLED", "true")
    monkeypatch.setenv("ENVIRONMENT", "production")
    session_id, questions = create_and_answer(client, question_count=1)
    res = client.post(f"/api/interviews/{session_id}/questions/{questions[0]['id']}/evaluate")
    assert res.status_code == 503


# ---------- API: completion, overall score, and persistence ----------

def test_completion_auto_evaluates_with_mock_and_persists(client, monkeypatch):
    monkeypatch.setenv("MOCK_EVALUATION_ENABLED", "true")
    created = create_interview(client, question_count=3).json()
    session_id = created["session_id"]
    for q in created["questions"]:
        client.post(f"/api/interviews/{session_id}/answers", json={"question_id": q["id"], "answer": "A substantive, specific answer about the topic."})

    completion = client.post(f"/api/interviews/{session_id}/complete")
    assert completion.status_code == 200
    body = completion.json()
    assert body["evaluation_status"] == "complete"
    assert body["evaluated_count"] == 3
    assert body["overall_score"] is not None

    # Re-fetch via GET /api/interviews/{id} (the results/history data path,
    # via QuestionEvaluationOut) - same overall_score (requirement: same
    # calculation as the real provider path, see main.py's _score_summary),
    # and each question's evaluation is clearly labeled simulated there too.
    fetched = client.get(f"/api/interviews/{session_id}").json()
    assert fetched["overall_score"] == body["overall_score"]
    assert fetched["evaluation_status"] == "complete"
    for q in fetched["questions"]:
        assert q["evaluation"] is not None
        assert q["evaluation"]["model"] == "mock-simulated-v1"
        assert q["evaluation"]["is_simulated"] is True
        assert "SIMULATED" in q["evaluation"]["note"]

    # Overall score is exactly the mean of the per-question total scores -
    # the same arithmetic _score_summary always uses, regardless of
    # provider.
    expected = round(sum(q["evaluation"]["total_score"] for q in fetched["questions"]) / len(fetched["questions"]), 1)
    assert fetched["overall_score"] == expected


def test_completion_with_mock_blocked_in_production_stays_unevaluated(client, monkeypatch):
    monkeypatch.setenv("MOCK_EVALUATION_ENABLED", "true")
    monkeypatch.setenv("ENVIRONMENT", "production")
    created = create_interview(client, question_count=1).json()
    session_id = created["session_id"]
    client.post(f"/api/interviews/{session_id}/answers", json={"question_id": created["questions"][0]["id"], "answer": "An answer."})

    completion = client.post(f"/api/interviews/{session_id}/complete")
    assert completion.status_code == 200
    body = completion.json()
    assert body["evaluation_status"] == "not_configured"
    assert body["evaluated_count"] == 0
    assert body["overall_score"] is None
    for q in body["questions"]:
        assert q["evaluation"] is None


def test_completion_with_evaluation_fully_disabled_is_unaffected(client):
    created = create_interview(client, question_count=1).json()
    session_id = created["session_id"]
    client.post(f"/api/interviews/{session_id}/answers", json={"question_id": created["questions"][0]["id"], "answer": "An answer."})
    res = client.post(f"/api/interviews/{session_id}/complete")
    assert res.status_code == 200
    body = res.json()
    assert body["evaluation_status"] == "not_configured"
    assert body["overall_score"] is None
    assert body["evaluated_count"] == 0


# ---------- Real evaluation path (EvaluationOut) is untouched by this feature ----------

def test_real_evaluation_note_text_is_unchanged_when_mock_is_off(client, monkeypatch):
    """Guards against the EvaluationOut.note default regressing for
    genuine AI evaluations - only a mock-labeled result should ever get
    the SIMULATED note; everything else keeps the original wording."""
    def fake_evaluate(role, category, difficulty, question_text, answer_text):
        return {
            "relevance_score": 25, "correctness_score": 30, "completeness_score": 20, "clarity_score": 8,
            "total_score": 83, "relevance_assessment": "On topic.", "correctness_assessment": "Accurate.",
            "explanation": "Solid answer.", "strengths": ["Clear"], "weaknesses": ["Could be shorter"],
            "suggestions": ["Trim it down"], "example_answer": None, "model": "gpt-4o-mini",
        }
    monkeypatch.setattr(main.evaluation_provider, "is_configured", lambda: True)
    monkeypatch.setattr(main.evaluation_provider, "evaluate_answer", fake_evaluate)

    session_id, questions = create_and_answer(client, question_count=1)
    res = client.post(f"/api/interviews/{session_id}/questions/{questions[0]['id']}/evaluate")
    assert res.status_code == 200
    body = res.json()
    assert body["is_simulated"] is False
    assert body["note"] == "AI-generated estimate for practice purposes - not an objective or official assessment."
