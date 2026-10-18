import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import evaluation_provider


class FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


class FakeClient:
    """Stands in for httpx.Client - evaluate_answer() never touches the
    network when a fake client is injected like this."""
    def __init__(self, response=None, raise_exc=None):
        self._response = response
        self._raise_exc = raise_exc
        self.calls = 0
        self.last_payload = None

    def post(self, url, headers=None, json=None):
        self.calls += 1
        self.last_payload = json
        if self._raise_exc:
            raise self._raise_exc
        return self._response


def good_evaluation(**overrides):
    body = {
        "relevance_score": 25,
        "correctness_score": 30,
        "completeness_score": 20,
        "clarity_score": 8,
        "relevance_assessment": "Directly addresses the question.",
        "correctness_assessment": "Technically accurate.",
        "explanation": "A solid, mostly complete answer.",
        "strengths": ["Clear structure", "Correct terminology"],
        "weaknesses": ["Missing an example"],
        "suggestions": ["Add a concrete example"],
        "example_answer": "",
    }
    body.update(overrides)
    return FakeResponse(200, {"choices": [{"message": {"content": json.dumps(body)}}]})


@pytest.fixture(autouse=True)
def evaluation_enabled(monkeypatch):
    monkeypatch.setenv("AI_EVALUATION_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    yield


def evaluate(client, answer="I would use a hash map for O(1) average lookups."):
    return evaluation_provider.evaluate_answer(
        "Backend Developer", "technical", "medium",
        "How would you find duplicates in a large list?", answer, client=client,
    )


# ---------- Configuration ----------

def test_not_configured_when_disabled(monkeypatch):
    monkeypatch.setenv("AI_EVALUATION_ENABLED", "false")
    with pytest.raises(evaluation_provider.EvaluationProviderNotConfigured):
        evaluate(FakeClient())


def test_not_configured_when_key_missing(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(evaluation_provider.EvaluationProviderNotConfigured):
        evaluate(FakeClient())


def test_question_generation_flag_does_not_enable_evaluation(monkeypatch):
    # AI_QUESTIONS_ENABLED is a completely separate switch - turning it on
    # must never silently turn on evaluation.
    monkeypatch.setenv("AI_EVALUATION_ENABLED", "false")
    monkeypatch.setenv("AI_QUESTIONS_ENABLED", "true")
    with pytest.raises(evaluation_provider.EvaluationProviderNotConfigured):
        evaluate(FakeClient())


# ---------- Successful evaluation and scoring ----------

def test_valid_structured_response_and_total_score_calculation():
    client = FakeClient(response=good_evaluation())
    result = evaluate(client)
    assert result["relevance_score"] == 25
    assert result["correctness_score"] == 30
    assert result["completeness_score"] == 20
    assert result["clarity_score"] == 8
    assert result["total_score"] == 25 + 30 + 20 + 8  # computed here, not from the model
    assert result["strengths"] == ["Clear structure", "Correct terminology"]
    assert result["weaknesses"] == ["Missing an example"]
    assert result["suggestions"] == ["Add a concrete example"]
    assert result["example_answer"] is None  # empty string becomes None
    assert result["model"]
    assert client.calls == 1  # exactly one request - no retries


def test_example_answer_passed_through_when_present():
    client = FakeClient(response=good_evaluation(example_answer="A stronger answer would mention hash collisions."))
    result = evaluate(client)
    assert result["example_answer"] == "A stronger answer would mention hash collisions."


def test_perfect_score_dimensions_sum_to_100():
    client = FakeClient(response=good_evaluation(
        relevance_score=30, correctness_score=35, completeness_score=25, clarity_score=10,
    ))
    result = evaluate(client)
    assert result["total_score"] == 100


# ---------- Validation of malformed/out-of-range responses ----------

def test_score_above_dimension_maximum_rejected():
    client = FakeClient(response=good_evaluation(relevance_score=31))
    with pytest.raises(evaluation_provider.EvaluationProviderInvalidResponse):
        evaluate(client)


def test_negative_score_rejected():
    client = FakeClient(response=good_evaluation(correctness_score=-1))
    with pytest.raises(evaluation_provider.EvaluationProviderInvalidResponse):
        evaluate(client)


def test_non_integer_score_rejected():
    client = FakeClient(response=good_evaluation(clarity_score="high"))
    with pytest.raises(evaluation_provider.EvaluationProviderInvalidResponse):
        evaluate(client)


def test_missing_required_field_rejected():
    body = {
        "relevance_score": 20, "correctness_score": 20, "completeness_score": 15, "clarity_score": 5,
        "relevance_assessment": "ok", "correctness_assessment": "ok",
        # "explanation" missing entirely
        "strengths": ["x"], "weaknesses": ["y"], "suggestions": ["z"], "example_answer": "",
    }
    bad = FakeResponse(200, {"choices": [{"message": {"content": json.dumps(body)}}]})
    with pytest.raises(evaluation_provider.EvaluationProviderInvalidResponse):
        evaluate(FakeClient(response=bad))


def test_empty_strengths_list_rejected():
    client = FakeClient(response=good_evaluation(strengths=[]))
    with pytest.raises(evaluation_provider.EvaluationProviderInvalidResponse):
        evaluate(client)


def test_malformed_json_rejected():
    bad = FakeResponse(200, {"choices": [{"message": {"content": "not valid json"}}]})
    with pytest.raises(evaluation_provider.EvaluationProviderInvalidResponse):
        evaluate(FakeClient(response=bad))


# ---------- Provider failures (no automatic retry) ----------

def test_provider_timeout():
    client = FakeClient(raise_exc=httpx.TimeoutException("timed out"))
    with pytest.raises(evaluation_provider.EvaluationProviderTimeout):
        evaluate(client)
    assert client.calls == 1


def test_provider_auth_error():
    client = FakeClient(response=FakeResponse(401, {"error": "invalid api key"}))
    with pytest.raises(evaluation_provider.EvaluationProviderAuthError):
        evaluate(client)


def test_provider_rate_limited():
    client = FakeClient(response=FakeResponse(429, {"error": "rate limited"}))
    with pytest.raises(evaluation_provider.EvaluationProviderRateLimited):
        evaluate(client)


def test_provider_outage():
    client = FakeClient(response=FakeResponse(500, {"error": "server error"}))
    with pytest.raises(evaluation_provider.EvaluationProviderUnavailable):
        evaluate(client)


def test_no_retry_on_any_failure():
    for exc_response in [
        FakeClient(raise_exc=httpx.TimeoutException("x")),
        FakeClient(response=FakeResponse(500, {})),
        FakeClient(response=FakeResponse(429, {})),
    ]:
        try:
            evaluate(exc_response)
        except evaluation_provider.EvaluationProviderError:
            pass
        assert exc_response.calls == 1


# ---------- Blank/behavioral/category handling ----------

def test_blank_answer_rejected_without_calling_provider():
    client = FakeClient(response=good_evaluation())
    with pytest.raises(ValueError):
        evaluate(client, answer="   ")
    assert client.calls == 0


def test_empty_answer_rejected_without_calling_provider():
    client = FakeClient(response=good_evaluation())
    with pytest.raises(ValueError):
        evaluate(client, answer="")
    assert client.calls == 0


def test_behavioral_category_uses_non_technical_guidance_in_prompt():
    client = FakeClient(response=good_evaluation())
    evaluation_provider.evaluate_answer(
        "Product Manager", "behavioral", "medium",
        "Tell me about a time you resolved a conflict.",
        "I listened to both sides and proposed a compromise.",
        client=client,
    )
    system_message = client.last_payload["messages"][0]["content"]
    assert "no single correct technical answer" in system_message
    assert evaluation_provider.TECHNICAL_GUIDANCE not in system_message


def test_technical_category_uses_technical_guidance_in_prompt():
    client = FakeClient(response=good_evaluation())
    evaluate(client)
    system_message = client.last_payload["messages"][0]["content"]
    assert evaluation_provider.TECHNICAL_GUIDANCE in system_message


def test_question_and_answer_are_sent_to_provider():
    client = FakeClient(response=good_evaluation())
    evaluate(client, answer="My specific candidate answer text.")
    user_message = client.last_payload["messages"][1]["content"]
    assert "How would you find duplicates in a large list?" in user_message
    assert "My specific candidate answer text." in user_message


# ---------- Secrets never logged or exposed ----------

def test_api_key_never_appears_in_exception_messages():
    client = FakeClient(response=FakeResponse(401, {"error": "invalid api key"}))
    try:
        evaluate(client)
        assert False, "expected EvaluationProviderAuthError"
    except evaluation_provider.EvaluationProviderAuthError as exc:
        assert "test-key-not-real" not in str(exc)


def test_answer_text_never_appears_in_exception_messages():
    client = FakeClient(response=FakeResponse(500, {"error": "server error"}))
    secret_answer = "my-very-specific-confidential-answer-text"
    try:
        evaluate(client, answer=secret_answer)
        assert False, "expected EvaluationProviderUnavailable"
    except evaluation_provider.EvaluationProviderUnavailable as exc:
        assert secret_answer not in str(exc)
