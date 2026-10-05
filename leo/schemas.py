"""Pydantic schemas = the structured outputs passed between agents."""
from typing import List, Literal
from pydantic import BaseModel, Field


class Plan(BaseModel):                       # Coordinator -> Explainer / Quiz Master
    status: Literal["ready", "needs_clarification"] = "ready"
    clarifying_question: str = ""
    topic: str = ""
    level: str = "beginner"
    learning_objectives: List[str] = Field(default_factory=list)
    key_concepts: List[str] = Field(default_factory=list)
    teaching_notes: str = ""


class QuizQuestion(BaseModel):               # Quiz Master output
    id: int = 0
    concept: str = ""
    question: str
    question_type: Literal["mcq", "short_answer"] = "short_answer"
    options: List[str] = Field(default_factory=list)
    correct_answer: str = ""
    explanation: str = ""


class Quiz(BaseModel):
    topic: str = ""
    questions: List[QuizQuestion]


class QuestionFeedback(BaseModel):           # Evaluator output (per question)
    id: int = 0
    concept: str = ""
    score: float = 0.0
    is_correct: bool = False
    feedback: str = ""


class Evaluation(BaseModel):                 # Evaluator -> Coordinator
    overall_score: float = 0.0
    question_feedback: List[QuestionFeedback] = Field(default_factory=list)
    weak_concepts: List[str] = Field(default_factory=list)
    needs_reteach: bool = False
    summary: str = ""
    encouragement: str = ""
