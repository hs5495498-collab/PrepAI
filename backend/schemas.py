from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

Category = Literal["technical", "hr", "behavioral"]
Difficulty = Literal["easy", "medium", "hard"]


class InterviewCreateRequest(BaseModel):
    role: str = Field(..., min_length=1, max_length=120)
    category: Category
    difficulty: Difficulty
    question_count: int = Field(..., ge=1, le=15)


class QuestionOut(BaseModel):
    id: str
    text: str
    answer: Optional[str] = None


class InterviewOut(BaseModel):
    session_id: str
    role: str
    category: Category
    difficulty: Difficulty
    status: Literal["in_progress", "completed"]
    questions: List[QuestionOut]
    total_questions: int
    answered_count: int
    question_source: Literal["fixed", "ai"] = "fixed"


class AnswerRequest(BaseModel):
    question_id: str = Field(..., min_length=1)
    answer: str

    @field_validator("answer")
    @classmethod
    def answer_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("answer must not be blank")
        return v.strip()


class AnswerResponse(BaseModel):
    session_id: str
    question_id: str
    status: Literal["answer_recorded"]
    answered_count: int
    total_questions: int


class CompletionResponse(BaseModel):
    session_id: str
    role: str
    category: Category
    difficulty: Difficulty
    status: Literal["completed"]
    questions: List[QuestionOut]
    answered_count: int
    total_questions: int
    question_source: Literal["fixed", "ai"] = "fixed"
