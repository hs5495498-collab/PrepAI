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


def is_configured() -> bool:
    enabled = os.environ.get("AI_EVALUATION_ENABLED", "false").strip().lower() == "true"
    return enabled and bool(os.environ.get("OPENAI_API_KEY"))


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


def evaluate_answer(role: str, category: str, difficulty: str, question_text: str, answer_text: str, client: httpx.Client = None) -> dict:
    """Returns a dict with relevance_score, correctness_score, completeness_score,
    clarity_score, total_score (computed here, not from the model), the three
    assessment/explanation strings, strengths/weaknesses/suggestions lists, an
    optional example_answer, and model (the model name actually used).
    Raises an EvaluationProviderError subclass on any failure."""
    if not is_configured():
        raise EvaluationProviderNotConfigured("AI answer evaluation is not configured")
    if not answer_text or not answer_text.strip():
        raise ValueError("answer_text must not be blank")
    if not question_text or not question_text.strip():
        raise ValueError("question_text must not be blank")
    if len(answer_text) > MAX_TEXT_LENGTH:
        answer_text = answer_text[:MAX_TEXT_LENGTH]

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
