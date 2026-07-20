from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def uuid4_str() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    syllabus_code: Mapped[str] = mapped_column(String(8), index=True)
    series: Mapped[str] = mapped_column(String(16), index=True)
    document_type: Mapped[str] = mapped_column(String(32), index=True)
    paper_code: Mapped[str | None] = mapped_column(String(8), nullable=True, index=True)
    paper_number: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    variant: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_path: Mapped[str] = mapped_column(Text, unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    blocks: Mapped[list["IngestionBlock"]] = relationship(back_populates="document")


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint("document_id", "question_number", name="uq_question_document_number"),
        Index("ix_question_lookup", "paper_code", "series", "question_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    paper_code: Mapped[str] = mapped_column(String(8), index=True)
    series: Mapped[str] = mapped_column(String(16), index=True)
    paper_number: Mapped[int] = mapped_column(Integer, index=True)
    question_number: Mapped[str] = mapped_column(String(32), index=True)
    parent_question_id: Mapped[str | None] = mapped_column(ForeignKey("questions.id"), nullable=True)
    topic_tag: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    marks_available: Mapped[int | None] = mapped_column(Integer, nullable=True)
    linked_mark_scheme_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    linked_insert_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IngestionBlock(Base):
    __tablename__ = "ingestion_blocks"
    __table_args__ = (
        UniqueConstraint("document_id", "fingerprint", name="uq_block_document_fingerprint"),
        Index("ix_block_review_queue", "review_status", "indexed"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    question_id: Mapped[str | None] = mapped_column(ForeignKey("questions.id"), nullable=True, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    page_number: Mapped[int] = mapped_column(Integer)
    block_type: Mapped[str] = mapped_column(String(32), index=True)
    question_number: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    parent_question_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    point_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    topic_tag: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    marks_available: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extraction_method: Mapped[str] = mapped_column(String(32))
    raw_text: Mapped[str] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(String(24), index=True)
    review_reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    indexed: Mapped[bool] = mapped_column(Boolean, default=False)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    document: Mapped[Document] = relationship(back_populates="blocks")


class InteractionEvent(Base):
    __tablename__ = "interaction_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    question_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    topic_tag: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Paper4TestCase(Base):
    __tablename__ = "paper4_test_cases"
    __table_args__ = (
        UniqueConstraint("question_id", "ordinal", name="uq_paper4_case_ordinal"),
        UniqueConstraint("question_id", "name", name="uq_paper4_case_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(128))
    stdin: Mapped[str] = mapped_column(Text, default="")
    arguments: Mapped[list[str]] = mapped_column(JSON, default=list)
    expected_stdout: Mapped[str] = mapped_column(Text)
    marks_available: Mapped[int] = mapped_column(Integer)
    comparison_mode: Mapped[str] = mapped_column(String(32), default="trim_trailing")
    expected_source_chunk_id: Mapped[str] = mapped_column(
        ForeignKey("ingestion_blocks.id"), index=True
    )
    verified_by: Mapped[str] = mapped_column(String(256))
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Paper4ResourceFile(Base):
    __tablename__ = "paper4_resource_files"
    __table_args__ = (
        UniqueConstraint("question_id", "filename", name="uq_paper4_resource_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id"), index=True)
    insert_document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    verified_by: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Paper4GradingAttempt(Base):
    __tablename__ = "paper4_grading_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id"), index=True)
    language: Mapped[str] = mapped_column(String(32), index=True)
    student_input: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), index=True)
    marks_awarded: Mapped[int | None] = mapped_column(Integer, nullable=True)
    marks_available: Mapped[int] = mapped_column(Integer)
    certified: Mapped[bool] = mapped_column(Boolean, default=False)
    validation_status: Mapped[str] = mapped_column(String(32), default="blocked")
    per_test_results: Mapped[list[dict]] = mapped_column(JSON, default=list)
    sandbox_profile: Mapped[dict] = mapped_column(JSON, default=dict)
    validation_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GradingPhaseValidation(Base):
    __tablename__ = "grading_phase_validations"

    phase: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default="blocked", index=True)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    exact_mark_match_rate: Mapped[float] = mapped_column(Float, default=0.0)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PaperSpecification(Base):
    __tablename__ = "paper_specifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    paper_number: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(256))
    time_limit_minutes: Mapped[int] = mapped_column(Integer)
    total_marks: Mapped[int] = mapped_column(Integer)
    topic_weights: Mapped[dict] = mapped_column(JSON)
    assessment_objective_weights: Mapped[dict] = mapped_column(JSON)
    slots: Mapped[list[dict]] = mapped_column(JSON)
    minimum_source_series: Mapped[int] = mapped_column(Integer, default=2)
    source_document_ids: Mapped[list[str]] = mapped_column(JSON)
    source_chunk_ids: Mapped[list[str]] = mapped_column(JSON)
    review_status: Mapped[str] = mapped_column(String(32), default="approved", index=True)
    verified_by: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class QuestionPresentation(Base):
    __tablename__ = "question_presentations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id"), unique=True, index=True)
    answer_surface: Mapped[str] = mapped_column(String(32), index=True)
    display_text: Mapped[str] = mapped_column(Text)
    subparts: Mapped[list[dict]] = mapped_column(JSON, default=list)
    resources: Mapped[list[dict]] = mapped_column(JSON, default=list)
    assessment_objective_marks: Mapped[dict] = mapped_column(JSON, default=dict)
    requires_resources: Mapped[bool] = mapped_column(Boolean, default=False)
    delivery_authorized: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    validation_status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    verified_by: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ValidatedMCQ(Base):
    __tablename__ = "validated_mcqs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    question_text: Mapped[str] = mapped_column(Text)
    options: Mapped[list[str]] = mapped_column(JSON)
    correct_option_index: Mapped[int] = mapped_column(Integer)
    topic_tag: Mapped[str] = mapped_column(String(128), index=True)
    difficulty: Mapped[str] = mapped_column(String(16))
    source_chunk_ids: Mapped[list[str]] = mapped_column(JSON)
    assessment_objective_marks: Mapped[dict] = mapped_column(JSON, default=dict)
    marks_available: Mapped[int] = mapped_column(Integer, default=1)
    validation_status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    verified_by: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExamAssembly(Base):
    __tablename__ = "exam_assemblies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    paper_number: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(256))
    time_limit_minutes: Mapped[int] = mapped_column(Integer)
    total_marks: Mapped[int] = mapped_column(Integer)
    strict_timer: Mapped[bool] = mapped_column(Boolean, default=True)
    seed: Mapped[str] = mapped_column(String(128))
    source_mix: Mapped[dict] = mapped_column(JSON)
    source_series: Mapped[list[str]] = mapped_column(JSON, default=list)
    questions: Mapped[list[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
