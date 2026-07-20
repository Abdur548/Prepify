from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Difficulty(str, Enum):
    easy = "Easy"
    medium = "Medium"
    hard = "Hard"


class MCQGenerateRequest(BaseModel):
    topic_tag: str = Field(min_length=1)
    count: int = Field(default=5, ge=1, le=20)


class MCQ(BaseModel):
    question_text: str = Field(min_length=1)
    options: list[str]
    correct_option_index: int = Field(ge=0, le=3)
    topic_tag: str
    difficulty: Difficulty
    source_chunk_ids: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def exactly_four_unique_options(self) -> "MCQ":
        if len(self.options) != 4:
            raise ValueError("Each MCQ must have exactly four options")
        if len({option.strip().casefold() for option in self.options}) != 4:
            raise ValueError("MCQ options must be unique")
        return self


class MCQGenerateResponse(BaseModel):
    questions: list[MCQ]


class ExplainMode(str, Enum):
    explain = "explain"
    reasoning = "reasoning"
    check_answer = "check_answer"


class QuestionExplainRequest(BaseModel):
    mode: ExplainMode = ExplainMode.explain
    student_answer: str | None = Field(default=None, max_length=20_000)

    @model_validator(mode="after")
    def answer_required_for_check(self) -> "QuestionExplainRequest":
        if self.mode == ExplainMode.check_answer and not (self.student_answer or "").strip():
            raise ValueError("student_answer is required when mode is check_answer")
        return self


class InternalCitation(BaseModel):
    chunk_id: str
    source_type: Literal["question", "mark_scheme"]
    document_id: str
    question_id: str | None = None
    page_number: int | None = None
    point_label: str | None = None


class QuestionExplainResponse(BaseModel):
    question_id: str
    explanation: str
    reasoning_steps: list[str]
    answer_feedback: str | None = None
    scoring_withheld: Literal[True] = True
    citations: list[InternalCitation] = Field(min_length=1)


class OCRBlock(BaseModel):
    text: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    block_type: Literal["question", "mark_scheme", "other"] = "other"
    question_number: str | None = None
    parent_question_number: str | None = None
    marks_available: int | None = Field(default=None, ge=0)
    topic_tag: str | None = None
    point_label: str | None = None
    extraction_method: Literal["qwen3_vl_ocr", "embedded_text"]


class PrepBotTurn(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=4_000)


class PrepBotChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4_000)
    history: list[PrepBotTurn] = Field(default_factory=list, max_length=8)


class PrepBotChatResponse(BaseModel):
    answer: str
    model: str
    stored: Literal[False] = False
