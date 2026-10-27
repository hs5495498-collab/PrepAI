from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import JSONResponse

load_dotenv()

import ai_provider
import analytics
import auth
import evaluation_provider
import recommendations
import storage
from questions import pick_questions
from schemas import (
    AnalyticsOut,
    AnswerRequest,
    AnswerResponse,
    CompletionResponse,
    EvaluationOut,
    InterviewCreateRequest,
    InterviewListOut,
    InterviewOut,
    LoginRequest,
    RecommendationsOut,
    RegisterRequest,
    UserOut,
)

app = FastAPI(title="PrepAI Backend")

AI_ERROR_MESSAGES = {
    ai_provider.AIProviderNotConfigured: "AI question generation is not configured on this server.",
    ai_provider.AIProviderTimeout: "The AI question generator took too long to respond. Please try again.",
    ai_provider.AIProviderAuthError: "The AI question generator is misconfigured on this server.",
    ai_provider.AIProviderRateLimited: "The AI question generator is temporarily busy. Please try again shortly.",
    ai_provider.AIProviderUnavailable: "The AI question generator is temporarily unavailable. Please try again.",
    ai_provider.AIProviderInvalidResponse: "The AI question generator returned an unusable response. Please try again.",
}

EVALUATION_ERROR_MESSAGES = {
    evaluation_provider.EvaluationProviderNotConfigured: "AI answer evaluation is not configured on this server.",
    evaluation_provider.EvaluationProviderTimeout: "The AI evaluator took too long to respond. Please try again.",
    evaluation_provider.EvaluationProviderAuthError: "The AI evaluator is misconfigured on this server.",
    evaluation_provider.EvaluationProviderRateLimited: "The AI evaluator is temporarily busy. Please try again shortly.",
    evaluation_provider.EvaluationProviderUnavailable: "The AI evaluator is temporarily unavailable. Please try again.",
    evaluation_provider.EvaluationProviderInvalidResponse: "The AI evaluator returned an unusable response. Please try again.",
}

# Auto-evaluation-on-completion (see _auto_evaluate_session below) runs
# each pending question's evaluation request concurrently, since each is
# an independent, I/O-bound HTTP call to the configured provider - this
# keeps completion latency close to one call's duration instead of
# growing linearly with the number of answered questions, without
# introducing a job queue or other new infrastructure.
MAX_AUTO_EVAL_WORKERS = 4

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
    allow_credentials=True,
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": "Internal server error."})


@app.get("/")
def root():
    return {"message": "PrepAI backend is running."}


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- Authentication helpers ----------

def get_current_user_optional(request: Request) -> Optional[dict]:
    token = request.cookies.get(auth.SESSION_COOKIE_NAME)
    return auth.get_user_for_session(token)


def require_user(request: Request) -> dict:
    user = get_current_user_optional(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return user


def _require_csrf(request: Request, user: dict) -> None:
    header_token = request.headers.get("X-CSRF-Token")
    if not header_token or header_token != user.get("csrf_token"):
        raise HTTPException(status_code=403, detail="Missing or invalid CSRF token.")


def _set_auth_cookies(response: Response, session: dict) -> None:
    max_age = auth.session_lifetime_days() * 24 * 60 * 60
    secure = auth.session_cookie_secure()
    response.set_cookie(
        auth.SESSION_COOKIE_NAME, session["token"],
        max_age=max_age, httponly=True, samesite="lax", secure=secure, path="/",
    )
    response.set_cookie(
        auth.CSRF_COOKIE_NAME, session["csrf_token"],
        max_age=max_age, httponly=False, samesite="lax", secure=secure, path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(auth.SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(auth.CSRF_COOKIE_NAME, path="/")


def _check_ownership(session: dict, user: Optional[dict]) -> None:
    """An interview with no owner (user_id is NULL) keeps today's open,
    anonymous-demo behavior for everyone. An owned interview is only
    visible to its owner - anyone else gets the same 404 a nonexistent
    session would, so private interviews are never confirmed to exist."""
    owner_id = session.get("user_id")
    if owner_id is not None and (user is None or user["id"] != owner_id):
        raise HTTPException(status_code=404, detail="Interview session not found.")


# ---------- Auth routes ----------

@app.post("/api/auth/register", response_model=UserOut, status_code=201)
def register(payload: RegisterRequest, response: Response):
    normalized_email = auth.normalize_email(payload.email)
    if not auth.is_valid_email(normalized_email):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    try:
        user = auth.create_user(normalized_email, payload.password)
    except auth.EmailAlreadyRegistered:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    session = auth.create_session_for_user(user["id"])
    _set_auth_cookies(response, session)
    return UserOut(id=user["id"], email=user["email"], created_at=user["created_at"])


@app.post("/api/auth/login", response_model=UserOut)
def login(payload: LoginRequest, response: Response):
    try:
        user = auth.authenticate(payload.email, payload.password)
    except auth.InvalidCredentials:
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    session = auth.create_session_for_user(user["id"])
    _set_auth_cookies(response, session)
    return UserOut(id=user["id"], email=user["email"], created_at=user["created_at"])


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, user: Optional[dict] = Depends(get_current_user_optional)):
    if user is not None:
        _require_csrf(request, user)
    auth.delete_session(request.cookies.get(auth.SESSION_COOKIE_NAME))
    _clear_auth_cookies(response)
    return {"status": "logged_out"}


@app.get("/api/auth/me", response_model=UserOut)
def me(user: dict = Depends(require_user)):
    return UserOut(id=user["id"], email=user["email"], created_at=user["created_at"])


# ---------- Interview routes ----------

def _score_summary(session: dict):
    """Returns (overall_score, evaluated_count, evaluation_status), derived
    consistently from this session's own persisted per-question evaluations
    every time - never stored separately, so it can never drift from them.

    overall_score is the simple arithmetic mean of every answered,
    evaluated question's total_score (each already 0-100 on an equally
    weighted rubric - see evaluation_provider.SCORE_WEIGHTS), rounded to 1
    decimal place; None when no answered question has a valid evaluation
    yet - never 0, and never counting an unanswered question.

    evaluation_status is "not_configured" (AI evaluation is off, so no
    score is expected at all), "not_evaluated" (configured, but nothing
    evaluated yet for this session), "partial" (some but not all answered
    questions are evaluated), or "complete" (every answered question is)."""
    answered = [q for q in session["questions"] if q["answer"] is not None and q["answer"].strip()]
    evaluated = [q for q in answered if q["evaluation"] is not None]
    if not evaluated:
        overall_score = None
        status = "not_configured" if not evaluation_provider.is_configured() else "not_evaluated"
    else:
        overall_score = round(sum(q["evaluation"]["total_score"] for q in evaluated) / len(evaluated), 1)
        status = "complete" if len(evaluated) == len(answered) else "partial"
    return overall_score, len(evaluated), status


def _to_interview_out(session: dict, question_bank_note: Optional[str] = None) -> InterviewOut:
    overall_score, evaluated_count, evaluation_status = _score_summary(session)
    return InterviewOut(
        session_id=session["id"],
        role=session["role"],
        category=session["category"],
        difficulty=session["difficulty"],
        status=session["status"],
        questions=session["questions"],
        total_questions=len(session["questions"]),
        answered_count=storage.answered_count(session),
        question_source=session["question_source"],
        question_bank_note=question_bank_note,
        evaluated_count=evaluated_count,
        overall_score=overall_score,
        evaluation_status=evaluation_status,
    )


def _evaluate_one_question(session: dict, question_id: str) -> dict:
    """Core evaluation logic shared by the manual per-question endpoint
    below and _auto_evaluate_session(). Returns the saved evaluation dict
    (the existing one if this question was already evaluated - idempotent,
    never re-calls the provider or creates a second row). Raises
    storage.QuestionNotFound / storage.AnswerNotFound /
    evaluation_provider.EvaluationProviderError exactly as the endpoint
    used to inline - callers decide how to handle each (an HTTP error for
    the manual endpoint, a silent skip for the best-effort auto path)."""
    existing = storage.get_evaluation(session["id"], question_id)
    if existing is not None:
        return existing
    if not evaluation_provider.is_configured():
        raise evaluation_provider.EvaluationProviderNotConfigured("AI answer evaluation is not configured")
    qa = storage.get_question_for_evaluation(session["id"], question_id)
    result = evaluation_provider.evaluate_answer(
        session["role"], session["category"], session["difficulty"],
        qa["question_text"], qa["answer_text"],
    )
    return storage.save_evaluation(session["id"], question_id, result)


def _auto_evaluate_session(session: dict) -> None:
    """Best-effort: evaluate every answered-but-not-yet-evaluated question
    in this session via the configured provider, concurrently (see
    MAX_AUTO_EVAL_WORKERS). Never raises and never undoes completion - a
    provider failure, for one question or all of them, just leaves that
    question's evaluation missing (QuestionOut.evaluation stays None,
    visible to the caller as a partial/not_evaluated status) and still
    retryable later through the existing manual evaluate endpoint. A
    no-op - and so exactly as fast as before this feature existed - when
    evaluation_provider.is_configured() is False (the default)."""
    if not evaluation_provider.is_configured():
        return
    pending_ids = [
        q["id"] for q in session["questions"]
        if q["answer"] is not None and q["answer"].strip() and q["evaluation"] is None
    ]
    if not pending_ids:
        return

    def _try_one(question_id):
        try:
            _evaluate_one_question(session, question_id)
        except (storage.QuestionNotFound, storage.AnswerNotFound, evaluation_provider.EvaluationProviderError):
            pass
        except Exception:
            # Defense in depth (e.g. a transient storage error under
            # concurrent writes): this question just stays unevaluated and
            # can be retried later - never let it crash completion.
            pass

    with ThreadPoolExecutor(max_workers=min(len(pending_ids), MAX_AUTO_EVAL_WORKERS)) as pool:
        list(pool.map(_try_one, pending_ids))


def _pick_fixed_questions(payload: InterviewCreateRequest, user: Optional[dict]):
    """The fixed-bank path shared by the no-AI-configured case and the
    AI-generation-failed fallback below: randomized per call (never the
    same fixed order every time), and - for a signed-in account - avoids
    repeating that account's own recently-asked questions in this exact
    category/difficulty when enough other suitable questions exist."""
    exclude_texts = None
    if user is not None:
        exclude_texts = storage.get_recent_question_texts(user["id"], payload.category, payload.difficulty)
    questions, insufficient = pick_questions(
        payload.category, payload.difficulty, payload.question_count, exclude_texts=exclude_texts
    )
    note = None
    if insufficient:
        note = (
            "Only {} distinct fixed sample question(s) are available for this category, "
            "fewer than the {} requested - showing all of them once instead of repeating any."
        ).format(len(questions), payload.question_count)
    return questions, note


@app.post("/api/interviews", response_model=InterviewOut, status_code=201)
def create_interview(payload: InterviewCreateRequest, request: Request, user: Optional[dict] = Depends(get_current_user_optional)):
    if user is not None:
        _require_csrf(request, user)
    question_bank_note = None
    if ai_provider.is_configured():
        try:
            questions = ai_provider.generate_questions(
                payload.role, payload.category, payload.difficulty, payload.question_count
            )
            question_source = "ai"
        except ai_provider.AIProviderError as exc:
            # Never block starting an interview just because the AI
            # generator failed - fall back to the fixed bank instead, and
            # say so honestly rather than ever presenting a fallback
            # question as AI-generated (question_source stays "fixed").
            reason = AI_ERROR_MESSAGES.get(type(exc), "The AI question generator is currently unavailable.")
            questions, fallback_note = _pick_fixed_questions(payload, user)
            question_source = "fixed"
            question_bank_note = reason + " Fixed sample questions were used instead."
            if fallback_note:
                question_bank_note += " " + fallback_note
    else:
        questions, question_bank_note = _pick_fixed_questions(payload, user)
        question_source = "fixed"
    session = storage.create_session(
        payload.role, payload.category, payload.difficulty, questions, question_source,
        user_id=(user["id"] if user is not None else None),
    )
    return _to_interview_out(session, question_bank_note)


MAX_HISTORY_LIMIT = 100
DEFAULT_HISTORY_LIMIT = 20


@app.get("/api/interviews", response_model=InterviewListOut)
def list_interviews(user: dict = Depends(require_user), limit: int = DEFAULT_HISTORY_LIMIT, offset: int = 0):
    # require_user - history is always tied to a real account; anonymous
    # interviews are intentionally excluded (see storage.list_user_interviews).
    limit = max(1, min(limit, MAX_HISTORY_LIMIT))
    offset = max(0, offset)
    items, total = storage.list_user_interviews(user["id"], limit, offset)
    return InterviewListOut(interviews=items, total=total, limit=limit, offset=offset)


@app.get("/api/interviews/{session_id}", response_model=InterviewOut)
def get_interview(session_id: str, user: Optional[dict] = Depends(get_current_user_optional)):
    try:
        session = storage.get_session(session_id)
    except storage.SessionNotFound:
        raise HTTPException(status_code=404, detail="Interview session not found.")
    _check_ownership(session, user)
    return _to_interview_out(session)


@app.post("/api/interviews/{session_id}/answers", response_model=AnswerResponse)
def submit_answer(session_id: str, payload: AnswerRequest, request: Request, user: Optional[dict] = Depends(get_current_user_optional)):
    if user is not None:
        _require_csrf(request, user)
    try:
        session = storage.get_session(session_id)
    except storage.SessionNotFound:
        raise HTTPException(status_code=404, detail="Interview session not found.")
    _check_ownership(session, user)
    try:
        session = storage.record_answer(session_id, payload.question_id, payload.answer)
    except storage.AlreadyCompleted:
        raise HTTPException(status_code=409, detail="This interview is already completed; answers can no longer be submitted.")
    except storage.QuestionNotFound:
        raise HTTPException(status_code=404, detail="Question not found in this interview session.")
    except storage.DuplicateAnswer:
        raise HTTPException(status_code=409, detail="This question has already been answered.")
    return AnswerResponse(
        session_id=session_id,
        question_id=payload.question_id,
        status="answer_recorded",
        answered_count=storage.answered_count(session),
        total_questions=len(session["questions"]),
    )


@app.post("/api/interviews/{session_id}/complete", response_model=CompletionResponse)
def complete_interview(session_id: str, request: Request, user: Optional[dict] = Depends(get_current_user_optional)):
    if user is not None:
        _require_csrf(request, user)
    try:
        session = storage.get_session(session_id)
    except storage.SessionNotFound:
        raise HTTPException(status_code=404, detail="Interview session not found.")
    _check_ownership(session, user)
    try:
        session = storage.complete_session(session_id)
    except storage.AlreadyCompleted:
        raise HTTPException(status_code=409, detail="This interview is already completed.")

    # Default evaluation: best-effort, never blocks or undoes completion -
    # see _auto_evaluate_session's docstring. Reload afterward to pick up
    # whatever got evaluated (or didn't) before computing the summary.
    _auto_evaluate_session(session)
    session = storage.get_session(session_id)

    overall_score, evaluated_count, evaluation_status = _score_summary(session)
    return CompletionResponse(
        session_id=session["id"],
        role=session["role"],
        category=session["category"],
        difficulty=session["difficulty"],
        status=session["status"],
        questions=session["questions"],
        answered_count=storage.answered_count(session),
        total_questions=len(session["questions"]),
        question_source=session["question_source"],
        evaluated_count=evaluated_count,
        overall_score=overall_score,
        evaluation_status=evaluation_status,
    )


@app.post("/api/interviews/{session_id}/questions/{question_id}/evaluate", response_model=EvaluationOut)
def evaluate_answer(session_id: str, question_id: str, request: Request, user: Optional[dict] = Depends(get_current_user_optional)):
    if user is not None:
        _require_csrf(request, user)
    try:
        session = storage.get_session(session_id)
    except storage.SessionNotFound:
        raise HTTPException(status_code=404, detail="Interview session not found.")
    _check_ownership(session, user)

    try:
        saved = _evaluate_one_question(session, question_id)
    except storage.QuestionNotFound:
        raise HTTPException(status_code=404, detail="Question not found in this interview session.")
    except storage.AnswerNotFound:
        raise HTTPException(status_code=409, detail="This question has not been answered yet, so it cannot be evaluated.")
    except evaluation_provider.EvaluationProviderError as exc:
        message = EVALUATION_ERROR_MESSAGES.get(type(exc), "AI answer evaluation is currently unavailable.")
        raise HTTPException(status_code=503, detail=message)
    return EvaluationOut(session_id=session_id, **saved)


@app.get("/api/recommendations", response_model=RecommendationsOut)
def get_recommendations(user: dict = Depends(require_user)):
    # require_user (not the optional variant) - recommendations are always
    # tied to a real account; there is no anonymous/offline equivalent.
    data = storage.get_user_recommendation_data(user["id"])
    recs = recommendations.build_recommendations(data["completed_interviews"], data["evaluations"])
    return RecommendationsOut(
        recommendations=recs,
        completed_interviews=data["completed_interviews"],
        evaluated_answers=len(data["evaluations"]),
    )


@app.get("/api/analytics", response_model=AnalyticsOut)
def get_analytics(user: dict = Depends(require_user)):
    # Reuses the exact same ownership-filtered query as /api/recommendations
    # (storage.get_user_recommendation_data) rather than a second data path.
    data = storage.get_user_recommendation_data(user["id"])
    summary = analytics.build_summary(data["total_interviews"], data["completed_interviews"], data["evaluations"])
    return AnalyticsOut(**summary)
