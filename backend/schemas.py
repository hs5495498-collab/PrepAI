from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

import evaluation_provider

Category = Literal["technical", "hr", "behavioral"]
Difficulty = Literal["easy", "medium", "hard"]
# "not_configured": AI evaluation is off, so no score is expected at all.
# "not_evaluated": configured, but nothing evaluated yet for this session.
# "partial": some but not all answered questions are evaluated.
# "complete": every answered question has a valid evaluation.
EvaluationStatus = Literal["not_configured", "not_evaluated", "partial", "complete"]


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
    # model/is_simulated/note: present so the results/history/analytics
    # pages (which all read this nested object, not EvaluationOut below)
    # can tell a mock evaluation apart from a real one too - see
    # evaluation_provider.MOCK_MODEL_NAME and the validator below.
    model: Optional[str] = None
    is_simulated: bool = False
    note: Optional[str] = None

    @model_validator(mode="after")
    def _flag_simulated(self):
        if self.model == evaluation_provider.MOCK_MODEL_NAME:
            self.is_simulated = True
            if self.note is None:
                self.note = evaluation_provider.SIMULATED_NOTE
        return self


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
    # Derived every time from this session's own persisted per-question
    # evaluations (see main.py's _score_summary) - never stored separately,
    # so it can never drift from them. overall_score is the mean of every
    # answered, evaluated question's total_score, or None when nothing is
    # evaluated yet - never a fabricated or zero-substituted score.
    evaluated_count: int = 0
    overall_score: Optional[float] = None
    evaluation_status: EvaluationStatus = "not_configured"


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
    evaluated_count: int = 0
    overall_score: Optional[float] = None
    evaluation_status: EvaluationStatus = "not_configured"


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
    is_simulated: bool = False
    note: Optional[str] = None

    @model_validator(mode="after")
    def _flag_simulated(self):
        if self.model == evaluation_provider.MOCK_MODEL_NAME:
            self.is_simulated = True
            if self.note is None:
                self.note = evaluation_provider.SIMULATED_NOTE
        elif self.note is None:
            self.note = "AI-generated estimate for practice purposes - not an objective or official assessment."
        return self


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
