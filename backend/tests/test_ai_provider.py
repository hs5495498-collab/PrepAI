import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ai_provider


class FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


class FakeClient:
    """Stands in for httpx.Client - generate_questions() never touches the
    network when a fake client is injected like this."""
    def __init__(self, response=None, raise_exc=None):
        self._response = response
        self._raise_exc = raise_exc
        self.calls = 0

    def post(self, url, headers=None, json=None):
        self.calls += 1
        if self._raise_exc:
            raise self._raise_exc
        return self._response


def chat_response(questions):
    return FakeResponse(200, {
        "choices": [{"message": {"content": json.dumps({"questions": questions})}}]
    })


@pytest.fixture(autouse=True)
def ai_enabled(monkeypatch):
    monkeypatch.setenv("AI_QUESTIONS_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    yield


def test_not_configured_when_disabled(monkeypatch):
    monkeypatch.setenv("AI_QUESTIONS_ENABLED", "false")
    with pytest.raises(ai_provider.AIProviderNotConfigured):
        ai_provider.generate_questions("Engineer", "technical", "easy", 3, client=FakeClient())


def test_not_configured_when_key_missing(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ai_provider.AIProviderNotConfigured):
        ai_provider.generate_questions("Engineer", "technical", "easy", 3, client=FakeClient())


def test_successful_generation_returns_valid_unique_ids():
    client = FakeClient(response=chat_response([
        "What is a REST API?", "Explain dependency injection.", "What is Big-O notation?"
    ]))
    result = ai_provider.generate_questions("Backend Developer", "technical", "medium", 3, client=client)
    assert len(result) == 3
    ids = [qid for qid, _text in result]
    assert ids == ["q1", "q2", "q3"]
    assert len(set(ids)) == len(ids)
    assert all(isinstance(text, str) and text for _qid, text in result)
    assert client.calls == 1  # exactly one request - no retries


def test_generation_respects_requested_count_even_if_provider_overdelivers():
    client = FakeClient(response=chat_response(["Q1", "Q2", "Q3", "Q4", "Q5"]))
    result = ai_provider.generate_questions("Engineer", "hr", "easy", 2, client=client)
    assert len(result) == 2


def test_malformed_response_raises_invalid_response():
    bad = FakeResponse(200, {"choices": [{"message": {"content": "not valid json"}}]})
    with pytest.raises(ai_provider.AIProviderInvalidResponse):
        ai_provider.generate_questions("Engineer", "technical", "easy", 3, client=FakeClient(response=bad))


def test_empty_question_list_raises_invalid_response():
    empty = chat_response([])
    with pytest.raises(ai_provider.AIProviderInvalidResponse):
        ai_provider.generate_questions("Engineer", "technical", "easy", 3, client=FakeClient(response=empty))


def test_non_string_and_blank_entries_are_filtered_out():
    mixed = chat_response(["Real question?", "", "   ", 42, None, "Another real one?"])
    result = ai_provider.generate_questions("Engineer", "behavioral", "easy", 5, client=FakeClient(response=mixed))
    texts = [text for _qid, text in result]
    assert texts == ["Real question?", "Another real one?"]


def test_provider_timeout():
    client = FakeClient(raise_exc=httpx.TimeoutException("timed out"))
    with pytest.raises(ai_provider.AIProviderTimeout):
        ai_provider.generate_questions("Engineer", "technical", "easy", 3, client=client)


def test_provider_auth_error():
    client = FakeClient(response=FakeResponse(401, {"error": "invalid api key"}))
    with pytest.raises(ai_provider.AIProviderAuthError):
        ai_provider.generate_questions("Engineer", "technical", "easy", 3, client=client)


def test_provider_rate_limited():
    client = FakeClient(response=FakeResponse(429, {"error": "rate limited"}))
    with pytest.raises(ai_provider.AIProviderRateLimited):
        ai_provider.generate_questions("Engineer", "technical", "easy", 3, client=client)


def test_provider_outage():
    client = FakeClient(response=FakeResponse(500, {"error": "server error"}))
    with pytest.raises(ai_provider.AIProviderUnavailable):
        ai_provider.generate_questions("Engineer", "technical", "easy", 3, client=client)


def test_provider_connection_error():
    client = FakeClient(raise_exc=httpx.ConnectError("could not connect"))
    with pytest.raises(ai_provider.AIProviderUnavailable):
        ai_provider.generate_questions("Engineer", "technical", "easy", 3, client=client)


def test_invalid_question_count_rejected():
    with pytest.raises(ValueError):
        ai_provider.generate_questions("Engineer", "technical", "easy", 0, client=FakeClient())
    with pytest.raises(ValueError):
        ai_provider.generate_questions("Engineer", "technical", "easy", 99, client=FakeClient())


def test_invalid_role_rejected():
    with pytest.raises(ValueError):
        ai_provider.generate_questions("", "technical", "easy", 3, client=FakeClient())
    with pytest.raises(ValueError):
        ai_provider.generate_questions("x" * 200, "technical", "easy", 3, client=FakeClient())


def test_invalid_category_rejected():
    with pytest.raises(ValueError):
        ai_provider.generate_questions("Engineer", "not-a-category", "easy", 3, client=FakeClient())


def test_api_key_never_appears_in_exception_messages():
    client = FakeClient(response=FakeResponse(401, {"error": "invalid api key"}))
    try:
        ai_provider.generate_questions("Engineer", "technical", "easy", 3, client=client)
        assert False, "expected AIProviderAuthError"
    except ai_provider.AIProviderAuthError as exc:
        assert "test-key-not-real" not in str(exc)
