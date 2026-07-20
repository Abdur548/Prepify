from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from prepify.phase1.schemas import Paper4Language, Paper4TestResult
from prepify.storage.models import (
    GradingPhaseValidation,
    Paper4GradingAttempt,
    Paper4ResourceFile,
    Paper4TestCase,
    Question,
    utcnow,
)


PHASE_NAME = "paper4_execution"


@dataclass(frozen=True)
class Paper4Context:
    question: Question
    test_cases: list[Paper4TestCase]
    resources: list[Paper4ResourceFile]
    validation_status: str


class Paper4Repository:
    def __init__(self, session: Session):
        self.session = session

    def get_context(
        self, question_id: str, *, sandbox_profile: dict | None = None
    ) -> Paper4Context:
        question = self.session.get(Question, question_id)
        if question is None:
            raise KeyError(question_id)
        if question.paper_number != 4:
            raise ValueError("Phase 1 grades Paper 4 questions only")
        test_cases = list(
            self.session.scalars(
                select(Paper4TestCase)
                .where(
                    Paper4TestCase.question_id == question_id,
                    Paper4TestCase.active.is_(True),
                )
                .order_by(Paper4TestCase.ordinal)
            )
        )
        if not test_cases:
            raise LookupError("No verified execution test manifest is configured for this question")
        resources = list(
            self.session.scalars(
                select(Paper4ResourceFile).where(Paper4ResourceFile.question_id == question_id)
            )
        )
        return Paper4Context(
            question,
            test_cases,
            resources,
            self.validation_status(sandbox_profile=sandbox_profile),
        )

    def validation_status(self, *, sandbox_profile: dict | None = None) -> str:
        row = self.session.get(GradingPhaseValidation, PHASE_NAME)
        if row is None or row.status != "validated":
            return "blocked"
        if sandbox_profile is not None and row.evidence.get("sandbox_profile") != sandbox_profile:
            return "blocked"
        return "validated"

    def start_attempt(
        self,
        *,
        question_id: str,
        language: Paper4Language,
        source_code: str,
        marks_available: int,
        validation_status: str,
        sandbox_profile: dict,
        validation_run_id: str | None,
    ) -> Paper4GradingAttempt:
        attempt = Paper4GradingAttempt(
            question_id=question_id,
            language=language.value,
            student_input=source_code,
            status="running",
            marks_available=marks_available,
            certified=False,
            validation_status=validation_status,
            sandbox_profile=sandbox_profile,
            validation_run_id=validation_run_id,
        )
        self.session.add(attempt)
        self.session.flush()
        return attempt

    def finish_attempt(
        self,
        attempt: Paper4GradingAttempt,
        *,
        status: str,
        marks_awarded: int | None,
        certified: bool,
        results: list[Paper4TestResult],
    ) -> None:
        attempt.status = status
        attempt.marks_awarded = marks_awarded
        attempt.certified = certified
        attempt.per_test_results = [result.model_dump(mode="json") for result in results]
        attempt.completed_at = utcnow()

    def record_validation(
        self,
        *,
        status: str,
        sample_count: int,
        exact_match_rate: float,
        evidence: dict,
    ) -> GradingPhaseValidation:
        row = self.session.get(GradingPhaseValidation, PHASE_NAME)
        if row is None:
            row = GradingPhaseValidation(phase=PHASE_NAME)
            self.session.add(row)
        row.status = status
        row.sample_count = sample_count
        row.exact_mark_match_rate = exact_match_rate
        row.evidence = evidence
        row.updated_at = utcnow()
        row.validated_at = utcnow() if status == "validated" else None
        self.session.flush()
        return row
