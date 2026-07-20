from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class AnswerSurface(str, Enum):
    mcq = "mcq"
    pseudocode = "pseudocode"
    code = "code"
    written = "written"


class SourceType(str, Enum):
    past_paper = "past_paper"
    validated_mcq = "validated_mcq"


class PaperSlot(BaseModel):
    answer_surface: AnswerSurface
    marks: int = Field(ge=1)
    count: int = Field(ge=1, le=50)
    allowed_source_types: list[SourceType] = Field(min_length=1)


class PaperSpecificationManifest(BaseModel):
    paper_number: int = Field(ge=1, le=4)
    title: str = Field(min_length=3, max_length=256)
    time_limit_minutes: int = Field(ge=1, le=360)
    total_marks: int = Field(ge=1, le=300)
    topic_weights: dict[str, float] = Field(min_length=1)
    assessment_objective_weights: dict[str, float] = Field(min_length=1)
    slots: list[PaperSlot] = Field(min_length=1)
    minimum_source_series: int = Field(default=2, ge=2, le=10)
    source_question_paper_ids: list[str] = Field(min_length=1)
    source_chunk_ids: list[str] = Field(min_length=1)
    verified_by: str = Field(min_length=3, max_length=256)

    @model_validator(mode="after")
    def coherent_specification(self) -> "PaperSpecificationManifest":
        slot_marks = sum(slot.marks * slot.count for slot in self.slots)
        if slot_marks != self.total_marks:
            raise ValueError(
                f"slot structure totals {slot_marks} marks, expected {self.total_marks}"
            )
        if any(
            source_type != SourceType.past_paper
            for slot in self.slots
            for source_type in slot.allowed_source_types
        ):
            raise ValueError("assembled exams may contain reviewed past-paper questions only")
        if sum(slot.count for slot in self.slots) < self.minimum_source_series:
            raise ValueError("slot count cannot satisfy the minimum source-series requirement")
        for label, weights in (
            ("topic", self.topic_weights),
            ("assessment objective", self.assessment_objective_weights),
        ):
            if any(weight <= 0 for weight in weights.values()):
                raise ValueError(f"{label} weights must be positive")
            total = sum(weights.values())
            if not (0.99 <= total <= 1.01 or 99 <= total <= 101):
                raise ValueError(f"{label} weights must total 1.0 or 100")
        return self


class PresentationSubpart(BaseModel):
    label: str = Field(min_length=1, max_length=32)
    marks_available: int = Field(ge=1)
    prompt: str = Field(min_length=1)


class PresentationResource(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    media_type: str = "text/plain"
    content: str = Field(max_length=500_000)


class PastPaperPresentationManifest(BaseModel):
    question_id: str
    answer_surface: Literal["pseudocode", "code", "written"]
    display_text: str = Field(min_length=1, max_length=100_000)
    subparts: list[PresentationSubpart] = Field(default_factory=list)
    resources: list[PresentationResource] = Field(default_factory=list)
    assessment_objective_marks: dict[str, int] = Field(min_length=1)
    requires_resources: bool = False
    delivery_authorized: Literal[True]
    verified_by: str = Field(min_length=3, max_length=256)

    @model_validator(mode="after")
    def surface_shape(self) -> "PastPaperPresentationManifest":
        if self.answer_surface == "written" and not self.subparts:
            raise ValueError("written presentations require segmented subparts")
        if self.requires_resources or self.resources:
            raise ValueError("insert/data-file dependent questions are deferred from assembly")
        if any(value < 0 for value in self.assessment_objective_marks.values()):
            raise ValueError("assessment-objective marks cannot be negative")
        return self


class ValidatedMCQManifest(BaseModel):
    question_text: str = Field(min_length=1)
    options: list[str]
    correct_option_index: int = Field(ge=0, le=3)
    topic_tag: str
    difficulty: Literal["Easy", "Medium", "Hard"]
    source_chunk_ids: list[str] = Field(min_length=1)
    assessment_objective_marks: dict[str, int] = Field(min_length=1)
    marks_available: int = Field(default=1, ge=1)
    verified_by: str = Field(min_length=3, max_length=256)

    @model_validator(mode="after")
    def valid_options(self) -> "ValidatedMCQManifest":
        if len(self.options) != 4 or len({item.strip().casefold() for item in self.options}) != 4:
            raise ValueError("validated MCQs require four unique options")
        if sum(self.assessment_objective_marks.values()) != self.marks_available:
            raise ValueError("MCQ assessment-objective marks must equal marks_available")
        return self


class QuestionPoolManifest(BaseModel):
    past_paper_questions: list[PastPaperPresentationManifest] = Field(default_factory=list)
    validated_mcqs: list[ValidatedMCQManifest] = Field(default_factory=list)


class AssembleExamRequest(BaseModel):
    paper_number: int = Field(ge=1, le=4)
    seed: str = Field(default="prepify", min_length=1, max_length=128)
    strict_timer: Literal[True] = True
    allow_novel_generation: Literal[False] = False


class AssembledResource(BaseModel):
    name: str
    media_type: str
    content: str


class AssembledSubpart(BaseModel):
    label: str
    marks_available: int
    prompt: str


class AssembledQuestion(BaseModel):
    item_id: str
    source_id: str
    source_type: SourceType
    source_series: str | None = None
    source_paper_code: str | None = None
    source_question_number: str | None = None
    answer_surface: AnswerSurface
    display_text: str
    marks_available: int
    topic_tag: str
    subparts: list[AssembledSubpart] = Field(default_factory=list)
    resources: list[AssembledResource] = Field(default_factory=list)
    options: list[str] | None = None
    assessment_objective_marks: dict[str, int]
    grader_capability: Literal["available", "gated", "not_required"]


class AssembledExamResponse(BaseModel):
    assembly_id: str
    paper_number: int
    title: str
    time_limit_minutes: int
    total_marks: int
    strict_timer: Literal[True]
    source_mix: dict[str, int]
    source_series: list[str]
    questions: list[AssembledQuestion]


class MCQAnswerRequest(BaseModel):
    selected_option_index: int = Field(ge=0, le=3)


class MCQAnswerResponse(BaseModel):
    correct: bool
    correct_option_index: int
    feedback: str
