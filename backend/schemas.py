from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

Category = Literal["technical", "hr", "behavioral"]
Difficulty = Literal["easy", "medium", "hard"]


class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=1, max_length=128)


class UserOut(BaseModel):
    id: int
    email: str
    created_at: str


class InterviewCreateRequest(BaseModel):
    role: str = Field(..., min_length=1, max_length=120)
    category: Category
    difficulty: Difficulty
    question_count: int = Field(..., ge=1, le=15)


class QuestionEvaluationOut(BaseModel):
    total_score: int = Field(..., ge=0, le=100)
    relevance_score: int = Field(..., ge=0, le=30)
    correctness_score: int = Field(..., ge=0, le=35)
    completeness_score: int = Field(..., ge=0, le=25)
    clarity_score: int = Field(..., ge=0, le=10)
    strengths: List[str]
    weaknesses: List[str]
    suggestions: List[str]
    example_answer: Optional[str] = None
    created_at: str


class QuestionOut(BaseModel):
    id: str
    text: str
    answer: Optional[str] = None
    evaluation: Optional[QuestionEvaluationOut] = None


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
    question_bank_note: Optional[str] = None


class AnswerRequest(BaseModel):
    question_id: str = Field(..., min_length=1)
    answer: str = Field(..., max_length=10000)

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


class EvaluationOut(BaseModel):
    session_id: str
    question_id: str
    total_score: int = Field(..., ge=0, le=100)
    relevance_score: int = Field(..., ge=0, le=30)
    correctness_score: int = Field(..., ge=0, le=35)
    completeness_score: int = Field(..., ge=0, le=25)
    clarity_score: int = Field(..., ge=0, le=10)
    relevance_assessment: str
    correctness_assessment: str
    explanation: str
    strengths: List[str]
    weaknesses: List[str]
    suggestions: List[str]
    example_answer: Optional[str] = None
    model: str
    created_at: str
    note: str = "AI-generated estimate for practice purposes - not an objective or official assessment."


class RecommendationOut(BaseModel):
    key: str
    title: str
    explanation: str
    reason: str
    category: Optional[Category] = None
    difficulty: Optional[Difficulty] = None
    action: str
    priority: Literal["high", "medium", "low"]
    evidence: List[str]
    evidence_level: Literal["data", "limited", "generic"]


class RecommendationsOut(BaseModel):
    recommendations: List[RecommendationOut]
    completed_interviews: int
    evaluated_answers: int


class InterviewSummaryOut(BaseModel):
    session_id: str
    role: str
    category: Category
    difficulty: Difficulty
    status: Literal["in_progress", "completed"]
    question_count: int
    answered_count: int
    evaluated_count: int
    average_score: Optional[float] = None
    created_at: str
    completed_at: Optional[str] = None


class InterviewListOut(BaseModel):
    interviews: List[InterviewSummaryOut]
    total: int
    limit: int
    offset: int


class CategoryStatOut(BaseModel):
    count: int
    average_score: float


class DimensionStatOut(BaseModel):
    label: str
    average: float
    max: int


class ProgressPointOut(BaseModel):
    evaluated_at: str
    score: int = Field(..., ge=0, le=100)


class AnalyticsOut(BaseModel):
    total_interviews: int
    completed_interviews: int
    evaluated_answers: int
    completion_rate: Optional[float] = None
    average_score: Optional[float] = None
    highest_score: Optional[int] = None
    most_recent_score: Optional[int] = None
    by_category: dict[str, CategoryStatOut]
    by_dimension: dict[str, DimensionStatOut]
    strongest_dimension: Optional[str] = None
    weakest_dimension: Optional[str] = None
    progress: List[ProgressPointOut]
    progress_sufficient: bool
