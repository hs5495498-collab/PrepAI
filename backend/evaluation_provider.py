"""AI answer-evaluation service, kept separate from the API route handlers
and from ai_provider.py (question generation). This module ONLY scores and
gives feedback on an already-submitted answer - it never generates
questions, and ai_provider.py never evaluates answers.

It is OFF by default and independent of question generation: both
OPENAI_API_KEY and AI_EVALUATION_ENABLED must be set for evaluate_answer()
to attempt a real request. Turning on AI_QUESTIONS_ENABLED does not enable
this, and vice versa, so a user who only wants AI-generated questions never
accidentally starts paying for evaluation calls too.

The model's own arithmetic is never trusted: this module asks for four
separate dimension scores and computes the 0-100 total itself in Python
(see SCORE_WEIGHTS below), rather than accepting a model-reported total.

Every raised exception message is written by this module, not copied from
the provider's response, and the candidate's submitted answer is never
included in any exception message or log line - only ever sent in the one
outgoing request to the configured provider.
"""
import json
import os

import httpx

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TIMEOUT_SECONDS = 25.0
MAX_TEXT_LENGTH = 4000

# Marks a persisted evaluation row (the existing "model" column, see
# db.py/storage.py - no schema change needed) as having come from the
# mock provider below rather than a real OpenAI call. schemas.py checks
# this exact string to decide whether to attach the SIMULATED label to an
# API response, so it must never collide with a real OpenAI model name.
MOCK_MODEL_NAME = "mock-simulated-v1"
SIMULATED_NOTE = (
    "SIMULATED — NOT AI-GENERATED: this is a deterministic, locally "
    "computed demo evaluation, not a real AI assessment. No OpenAI call "
    "was made and no cost was incurred."
)
PRODUCTION_ENVIRONMENT_NAMES = {"production", "prod"}

# Rubric: documented scoring weights, summing to 100.
SCORE_WEIGHTS = {
    "relevance_score": 30,
    "correctness_score": 35,
    "completeness_score": 25,
    "clarity_score": 10,
}

CATEGORY_LABELS = {"technical": "technical", "hr": "HR", "behavioral": "behavioral"}

TECHNICAL_GUIDANCE = (
    "This is a technical question. Weigh technical accuracy heavily and call out any "
    "important concept the answer is missing or gets wrong."
)
BEHAVIORAL_GUIDANCE = (
    "This is a behavioral/HR question. There is no single correct technical answer - "
    "judge relevance to the question, specificity of the example used, clarity of structure "
    "(e.g. situation/action/result), evidence of genuine reflection, and the candidate's own "
    "contribution. Do not apply a technical-correctness test to this kind of answer."
)


class EvaluationProviderError(Exception):
    """Base class for all evaluation-provider failures."""


class EvaluationProviderNotConfigured(EvaluationProviderError):
    pass


class EvaluationProviderTimeout(EvaluationProviderError):
    pass


class EvaluationProviderAuthError(EvaluationProviderError):
    pass


class EvaluationProviderRateLimited(EvaluationProviderError):
    pass


class EvaluationProviderUnavailable(EvaluationProviderError):
    pass


class EvaluationProviderInvalidResponse(EvaluationProviderError):
    pass


def _is_production_environment() -> bool:
    """Structural safety net for is_mock_enabled(): even if
    MOCK_EVALUATION_ENABLED=true is set by mistake in a production
    deployment's environment, mock mode still refuses to turn on once
    ENVIRONMENT names a real production deployment. Defaults to
    "development" when unset, which is correct for every local setup this
    project documents - a production deployment must set ENVIRONMENT
    explicitly for this check to matter."""
    env_name = os.environ.get("ENVIRONMENT", "development").strip().lower()
    return env_name in PRODUCTION_ENVIRONMENT_NAMES


def _real_provider_configured() -> bool:
    enabled = os.environ.get("AI_EVALUATION_ENABLED", "false").strip().lower() == "true"
    return enabled and bool(os.environ.get("OPENAI_API_KEY"))


def is_mock_enabled() -> bool:
    """True only when a developer has explicitly opted into mock
    evaluation (MOCK_EVALUATION_ENABLED=true), the environment is not
    production (see _is_production_environment above), and the real
    provider isn't already configured - a working real setup always
    takes priority, so mock mode can never silently stand in for a
    genuine AI assessment that was actually available."""
    requested = os.environ.get("MOCK_EVALUATION_ENABLED", "false").strip().lower() == "true"
    if not requested:
        return False
    if _is_production_environment():
        return False
    if _real_provider_configured():
        return False
    return True


def is_configured() -> bool:
    if is_mock_enabled():
        return True
    return _real_provider_configured()


def _build_payload(role: str, category: str, difficulty: str, question_text: str, answer_text: str) -> dict:
    category_label = CATEGORY_LABELS.get(category, category)
    guidance = TECHNICAL_GUIDANCE if category == "technical" else BEHAVIORAL_GUIDANCE
    system = (
        "You are an interview coach evaluating ONE candidate answer to ONE mock interview "
        "question, for practice purposes only - this is not a real hiring decision. "
        "Score strictly on relevance, correctness, completeness and clarity. "
        "A long answer full of impressive-sounding terms is not automatically a good answer - "
        "judge substance, not length or vocabulary. Do not reward wording that merely echoes "
        "the question. An empty, off-topic, or nonsensical answer must score very low on every "
        "dimension. " + guidance
    )
    user = (
        "Role: {role}\nCategory: {category}\nDifficulty: {difficulty}\n\n"
        "Question: {question}\n\nCandidate's answer: {answer}\n\n"
        "Score this answer on these dimensions, each as an integer within its own range:\n"
        "- relevance_score: 0-30 (does it actually address the question asked)\n"
        "- correctness_score: 0-35 (technical/factual accuracy, or soundness of reasoning for non-technical questions)\n"
        "- completeness_score: 0-25 (covers the important points, doesn't leave out key parts)\n"
        "- clarity_score: 0-10 (organized, easy to follow)\n"
        "Also give: a one-sentence relevance_assessment, a one-sentence correctness_assessment, "
        "a short explanation of the overall score, 1-4 specific strengths, 1-4 specific "
        "weaknesses or missing concepts, 1-4 actionable suggestions, and - only if genuinely "
        "useful - a short example_answer showing a stronger response (leave it an empty string "
        "if the given answer is already strong and there is nothing meaningfully better to add)."
    ).format(role=role, category=category_label, difficulty=difficulty, question=question_text, answer=answer_text)
    return {
        "model": os.environ.get("OPENAI_MODEL", DEFAULT_MODEL),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "answer_evaluation",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "relevance_score": {"type": "integer", "minimum": 0, "maximum": 30},
                        "correctness_score": {"type": "integer", "minimum": 0, "maximum": 35},
                        "completeness_score": {"type": "integer", "minimum": 0, "maximum": 25},
                        "clarity_score": {"type": "integer", "minimum": 0, "maximum": 10},
                        "relevance_assessment": {"type": "string"},
                        "correctness_assessment": {"type": "string"},
                        "explanation": {"type": "string"},
                        "strengths": {"type": "array", "items": {"type": "string"}},
                        "weaknesses": {"type": "array", "items": {"type": "string"}},
                        "suggestions": {"type": "array", "items": {"type": "string"}},
                        "example_answer": {"type": "string"},
                    },
                    "required": [
                        "relevance_score", "correctness_score", "completeness_score", "clarity_score",
                        "relevance_assessment", "correctness_assessment", "explanation",
                        "strengths", "weaknesses", "suggestions", "example_answer",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        "temperature": 0.2,
    }


def _clean_text_list(raw, field_name: str):
    if not isinstance(raw, list):
        raise EvaluationProviderInvalidResponse(field_name + " was not a list")
    cleaned = [t.strip() for t in raw if isinstance(t, str) and t.strip()]
    if not cleaned:
        raise EvaluationProviderInvalidResponse(field_name + " contained no usable text")
    return cleaned


def _validate_score(raw, field_name: str, maximum: int) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise EvaluationProviderInvalidResponse(field_name + " was not an integer")
    if raw < 0 or raw > maximum:
        raise EvaluationProviderInvalidResponse(field_name + " was out of range")
    return raw


def _validate_text(raw, field_name: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise EvaluationProviderInvalidResponse(field_name + " was missing or empty")
    return raw.strip()


def _parse_and_validate(parsed: dict) -> dict:
    scores = {name: _validate_score(parsed.get(name), name, maximum) for name, maximum in SCORE_WEIGHTS.items()}
    total_score = sum(scores.values())  # computed here, never taken from the model
    result = dict(scores)
    result["total_score"] = total_score
    result["relevance_assessment"] = _validate_text(parsed.get("relevance_assessment"), "relevance_assessment")
    result["correctness_assessment"] = _validate_text(parsed.get("correctness_assessment"), "correctness_assessment")
    result["explanation"] = _validate_text(parsed.get("explanation"), "explanation")
    result["strengths"] = _clean_text_list(parsed.get("strengths"), "strengths")
    result["weaknesses"] = _clean_text_list(parsed.get("weaknesses"), "weaknesses")
    result["suggestions"] = _clean_text_list(parsed.get("suggestions"), "suggestions")
    example_answer = parsed.get("example_answer")
    result["example_answer"] = example_answer.strip() if isinstance(example_answer, str) and example_answer.strip() else None
    return result


def _mock_dimension_scores(answer_text: str) -> dict:
    """Deterministic (never random - see module docstring's req #8) scores
    for each rubric dimension, derived only from the answer's own length:
    the same answer_text always produces the exact same scores, run after
    run, machine after machine - there is no hidden state and no call to
    random/time/uuid anywhere in this function. A longer, more substantive
    answer scores higher, within a safe 35%-95% band of each dimension's
    maximum, so a demo shows believable variation without ever reaching
    a suspicious-looking 0 or a perfect 100 for ordinary input."""
    word_count = len(answer_text.split())
    coverage = min(word_count / 100.0, 1.0)
    ratio = 0.35 + (0.95 - 0.35) * coverage
    return {name: max(0, min(maximum, round(maximum * ratio))) for name, maximum in SCORE_WEIGHTS.items()}


def _mock_evaluate_answer(category: str, answer_text: str) -> dict:
    """The mock provider: builds the exact same result shape
    evaluate_answer() returns for a real OpenAI call (same keys, same
    score ranges, server-computed total), so every downstream consumer -
    storage, _score_summary, the results/history/analytics pages - works
    identically regardless of which provider produced it. Every text field
    is explicitly, repeatedly labeled simulated so it can never be mistaken
    for genuine AI feedback (req #4/#8); model=MOCK_MODEL_NAME is the
    persisted, API-visible marker schemas.py uses to attach that label."""
    scores = _mock_dimension_scores(answer_text)
    result = dict(scores)
    result["total_score"] = sum(scores.values())
    category_label = CATEGORY_LABELS.get(category, category)
    result["relevance_assessment"] = SIMULATED_NOTE + " (Simulated relevance check for this " + category_label + " question.)"
    result["correctness_assessment"] = SIMULATED_NOTE + " (Simulated correctness check - no real content analysis was performed.)"
    result["explanation"] = (
        SIMULATED_NOTE + " This score was derived locally from the answer's length, "
        "so the interview workflow, results page, history, and analytics can be demonstrated "
        "and tested without an OpenAI API key or any paid API call."
    )
    result["strengths"] = ["(Simulated) An answer was submitted for this question."]
    result["weaknesses"] = ["(Simulated) This feedback is not based on real content analysis - enable genuine AI evaluation for that."]
    result["suggestions"] = ["(Simulated) Set AI_EVALUATION_ENABLED=true and a real OPENAI_API_KEY to get genuine AI feedback."]
    result["example_answer"] = None
    result["model"] = MOCK_MODEL_NAME
    return result


def evaluate_answer(role: str, category: str, difficulty: str, question_text: str, answer_text: str, client: httpx.Client = None) -> dict:
    """Returns a dict with relevance_score, correctness_score, completeness_score,
    clarity_score, total_score (computed here, not from the model), the three
    assessment/explanation strings, strengths/weaknesses/suggestions lists, an
    optional example_answer, and model (the model name actually used).
    Raises an EvaluationProviderError subclass on any failure.

    When is_mock_enabled() is true, this returns a deterministic simulated
    result (see _mock_evaluate_answer) and makes no network call at all -
    every other validation/shape guarantee below still applies."""
    if not is_configured():
        raise EvaluationProviderNotConfigured("AI answer evaluation is not configured")
    if not answer_text or not answer_text.strip():
        raise ValueError("answer_text must not be blank")
    if not question_text or not question_text.strip():
        raise ValueError("question_text must not be blank")
    if len(answer_text) > MAX_TEXT_LENGTH:
        answer_text = answer_text[:MAX_TEXT_LENGTH]

    if is_mock_enabled():
        return _mock_evaluate_answer(category, answer_text)

    api_key = os.environ["OPENAI_API_KEY"]
    model = os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)
    payload = _build_payload(role, category, difficulty, question_text, answer_text)

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
            raise EvaluationProviderTimeout("the AI provider did not respond in time")
        except httpx.RequestError:
            raise EvaluationProviderUnavailable("could not reach the AI provider")

        if response.status_code in (401, 403):
            raise EvaluationProviderAuthError("the AI provider rejected the configured credentials")
        if response.status_code == 429:
            raise EvaluationProviderRateLimited("the AI provider is rate-limiting requests right now")
        if response.status_code >= 500:
            raise EvaluationProviderUnavailable("the AI provider is currently unavailable")
        if response.status_code != 200:
            raise EvaluationProviderUnavailable("the AI provider returned an unexpected error")

        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            parsed = json.loads(content)
        except (KeyError, IndexError, ValueError, TypeError):
            raise EvaluationProviderInvalidResponse("the provider's response could not be parsed")

        result = _parse_and_validate(parsed)
        result["model"] = model
        return result
    finally:
        if owns_client:
            http_client.close()
