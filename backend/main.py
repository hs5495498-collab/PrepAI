from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import JSONResponse

import storage
from questions import pick_questions
from schemas import (
    AnswerRequest,
    AnswerResponse,
    CompletionResponse,
    InterviewCreateRequest,
    InterviewOut,
)

app = FastAPI(title="PrepAI Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
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


def _to_interview_out(session: dict) -> InterviewOut:
    return InterviewOut(
        session_id=session["id"],
        role=session["role"],
        category=session["category"],
        difficulty=session["difficulty"],
        status=session["status"],
        questions=session["questions"],
        total_questions=len(session["questions"]),
        answered_count=storage.answered_count(session),
    )


@app.post("/api/interviews", response_model=InterviewOut, status_code=201)
def create_interview(payload: InterviewCreateRequest):
    questions = pick_questions(payload.category, payload.difficulty, payload.question_count)
    session = storage.create_session(payload.role, payload.category, payload.difficulty, questions)
    return _to_interview_out(session)


@app.get("/api/interviews/{session_id}", response_model=InterviewOut)
def get_interview(session_id: str):
    try:
        session = storage.get_session(session_id)
    except storage.SessionNotFound:
        raise HTTPException(status_code=404, detail="Interview session not found.")
    return _to_interview_out(session)


@app.post("/api/interviews/{session_id}/answers", response_model=AnswerResponse)
def submit_answer(session_id: str, payload: AnswerRequest):
    try:
        session = storage.record_answer(session_id, payload.question_id, payload.answer)
    except storage.SessionNotFound:
        raise HTTPException(status_code=404, detail="Interview session not found.")
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
def complete_interview(session_id: str):
    try:
        session = storage.complete_session(session_id)
    except storage.SessionNotFound:
        raise HTTPException(status_code=404, detail="Interview session not found.")
    except storage.AlreadyCompleted:
        raise HTTPException(status_code=409, detail="This interview is already completed.")
    return CompletionResponse(
        session_id=session["id"],
        role=session["role"],
        category=session["category"],
        difficulty=session["difficulty"],
        status=session["status"],
        questions=session["questions"],
        answered_count=storage.answered_count(session),
        total_questions=len(session["questions"]),
    )
