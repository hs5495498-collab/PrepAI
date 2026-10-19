"""AI question-generation service, kept separate from the API route handlers.

This talks to OpenAI's Chat Completions API (structured JSON output) to
generate interview QUESTIONS ONLY - never answers, scores, or feedback.
It is OFF by default: both OPENAI_API_KEY and AI_QUESTIONS_ENABLED must be
set for generate_questions() to attempt a real request, so simply having a
leftover key in the environment can never silently start incurring cost.

Every raised exception message is written by this module, not copied from
the provider's response, so the API key and raw provider payloads are never
exposed to a caller or logged.
"""
import json
import os

import httpx

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TIMEOUT_SECONDS = 20.0
MIN_QUESTION_COUNT = 1
MAX_QUESTION_COUNT = 15
MAX_ROLE_LENGTH = 120
MAX_QUESTION_TEXT_LENGTH = 300

CATEGORY_LABELS = {"technical": "technical", "hr": "HR", "behavioral": "behavioral"}


class AIProviderError(Exception):
    """Base class for all AI-provider failures."""


class AIProviderNotConfigured(AIProviderError):
    pass


class AIProviderTimeout(AIProviderError):
    pass


class AIProviderAuthError(AIProviderError):
    pass


class AIProviderRateLimited(AIProviderError):
    pass


class AIProviderUnavailable(AIProviderError):
    pass


class AIProviderInvalidResponse(AIProviderError):
    pass


def is_configured() -> bool:
    enabled = os.environ.get("AI_QUESTIONS_ENABLED", "false").strip().lower() == "true"
    return enabled and bool(os.environ.get("OPENAI_API_KEY"))


def _build_payload(role: str, category: str, difficulty: str, count: int) -> dict:
    category_label = CATEGORY_LABELS.get(category, category)
    system = (
        "You write short, realistic mock-interview questions for a practice-interview app. "
        "Output only the questions requested - no answers, no scoring, no commentary."
    )
    user = (
        "Generate {count} {difficulty}-difficulty {category} interview questions for a candidate "
        "interviewing for the role of \"{role}\". Each question must be a single, self-contained "
        "sentence a real interviewer could ask out loud."
    ).format(count=count, difficulty=difficulty, category=category_label, role=role)
    return {
        "model": os.environ.get("OPENAI_MODEL", DEFAULT_MODEL),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "interview_questions",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "questions": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["questions"],
                    "additionalProperties": False,
                },
            },
        },
        "temperature": 0.7,
    }


def _clean_questions(raw_questions, count: int):
    if not isinstance(raw_questions, list):
        raise AIProviderInvalidResponse("the provider did not return a list of questions")
    cleaned = []
    seen = set()
    for q in raw_questions:
        if not isinstance(q, str):
            continue
        text = q.strip()
        if not text or len(text) > MAX_QUESTION_TEXT_LENGTH or text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
    if not cleaned:
        raise AIProviderInvalidResponse("the provider returned no usable questions")
    if len(cleaned) < count:
        # Never silently hand back fewer questions than requested and let a
        # caller present it as if the full count were AI-generated - an
        # under-delivering provider response is treated the same as any
        # other invalid response.
        raise AIProviderInvalidResponse(
            "the provider returned {} usable question(s), fewer than the {} requested".format(len(cleaned), count)
        )
    return cleaned[:count]


def generate_questions(role: str, category: str, difficulty: str, count: int, client: httpx.Client = None):
    """Returns a list of (question_id, text) tuples, e.g. [("q1", "..."), ("q2", "...")].
    Raises an AIProviderError subclass on any failure - callers decide what to show the user."""
    if not is_configured():
        raise AIProviderNotConfigured("AI question generation is not configured")
    if not role or not role.strip() or len(role) > MAX_ROLE_LENGTH:
        raise ValueError("role must be a non-empty string of at most {} characters".format(MAX_ROLE_LENGTH))
    if category not in CATEGORY_LABELS:
        raise ValueError("unknown category")
    if not (MIN_QUESTION_COUNT <= count <= MAX_QUESTION_COUNT):
        raise ValueError("question_count out of allowed range")

    api_key = os.environ["OPENAI_API_KEY"]
    payload = _build_payload(role, category, difficulty, count)

    owns_client = client is None
    http_client = client if client is not None else httpx.Client(timeout=DEFAULT_TIMEOUT_SECONDS)
    try:
        try:
            response = http_client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
                json=payload,
            )
        except httpx.TimeoutException:
            raise AIProviderTimeout("the AI provider did not respond in time")
        except httpx.RequestError:
            raise AIProviderUnavailable("could not reach the AI provider")

        if response.status_code in (401, 403):
            raise AIProviderAuthError("the AI provider rejected the configured credentials")
        if response.status_code == 429:
            raise AIProviderRateLimited("the AI provider is rate-limiting requests right now")
        if response.status_code >= 500:
            raise AIProviderUnavailable("the AI provider is currently unavailable")
        if response.status_code != 200:
            raise AIProviderUnavailable("the AI provider returned an unexpected error")

        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            raw_questions = parsed["questions"]
        except (KeyError, IndexError, ValueError, TypeError):
            raise AIProviderInvalidResponse("the provider's response could not be parsed")

        cleaned = _clean_questions(raw_questions, count)
        return [("q{}".format(idx + 1), text) for idx, text in enumerate(cleaned)]
    finally:
        if owns_client:
            http_client.close()
