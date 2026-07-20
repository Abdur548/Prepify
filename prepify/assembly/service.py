from __future__ import annotations

import hashlib
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from prepify.assembly.schemas import (
    AnswerSurface,
    AssembleExamRequest,
    AssembledExamResponse,
    AssembledQuestion,
    MCQAnswerResponse,
    SourceType,
)
from prepify.storage.models import (
    ExamAssembly,
    IngestionBlock,
    PaperSpecification,
    Question,
    QuestionPresentation,
)


@dataclass(frozen=True)
class Candidate:
    source_id: str
    source_type: SourceType
    answer_surface: AnswerSurface
    display_text: str
    marks_available: int
    topic_tag: str
    assessment_objective_marks: dict[str, int]
    subparts: list[dict]
    resources: list[dict]
    source_series: str
    source_paper_code: str
    source_question_number: str
    mark_scheme_chunk_ids: list[str]
    options: list[str] | None = None
    correct_option_index: int | None = None


class ExamAssembler:
    def __init__(self, session: Session):
        self.session = session

    def assemble(self, request: AssembleExamRequest) -> AssembledExamResponse:
        spec = self.session.scalar(
            select(PaperSpecification).where(
                PaperSpecification.paper_number == request.paper_number,
                PaperSpecification.review_status == "approved",
            )
        )
        if spec is None:
            raise LookupError(
                "No reviewed historical-question-paper specification exists for this paper"
            )
        candidates = self._candidates(request.paper_number)
        selected: list[Candidate] = []
        topic_marks: dict[str, int] = defaultdict(int)
        objective_marks: dict[str, int] = defaultdict(int)
        target_topics = {
            key: value * spec.total_marks for key, value in spec.topic_weights.items()
        }
        target_objectives = {
            key: value * spec.total_marks
            for key, value in spec.assessment_objective_weights.items()
        }
        expanded_slots: list[dict] = []
        for slot in spec.slots:
            expanded_slots.extend([slot] * int(slot["count"]))

        used: set[str] = set()
        selected_series: set[str] = set()
        for slot_index, slot in enumerate(expanded_slots):
            eligible = [
                candidate
                for candidate in candidates
                if candidate.source_id not in used
                and candidate.answer_surface.value == slot["answer_surface"]
                and candidate.marks_available == int(slot["marks"])
                and candidate.source_type.value in slot["allowed_source_types"]
                and candidate.topic_tag in target_topics
            ]
            if not eligible:
                raise LookupError(
                    f"Validated pool cannot fill slot {slot_index + 1}: "
                    f"{slot['answer_surface']} / {slot['marks']} marks"
                )

            def score(candidate: Candidate) -> tuple[float, float]:
                topic_deficit = target_topics[candidate.topic_tag] - topic_marks[candidate.topic_tag]
                objective_deficit = sum(
                    max(target_objectives.get(ao, 0) - objective_marks[ao], 0)
                    * marks
                    for ao, marks in candidate.assessment_objective_marks.items()
                )
                digest = hashlib.sha256(
                    f"{request.seed}|{slot_index}|{candidate.source_id}".encode("utf-8")
                ).digest()
                tie_break = int.from_bytes(digest[:8], "big") / 2**64
                series_bonus = (
                    spec.total_marks * 10
                    if len(selected_series) < spec.minimum_source_series
                    and candidate.source_series not in selected_series
                    else 0
                )
                return topic_deficit + objective_deficit + series_bonus, tie_break

            chosen = max(eligible, key=score)
            selected.append(chosen)
            used.add(chosen.source_id)
            selected_series.add(chosen.source_series)
            topic_marks[chosen.topic_tag] += chosen.marks_available
            for objective, marks in chosen.assessment_objective_marks.items():
                objective_marks[objective] += marks

        if sum(item.marks_available for item in selected) != spec.total_marks:
            raise RuntimeError("assembled marks do not match the reviewed paper specification")
        if len(selected_series) < spec.minimum_source_series:
            raise LookupError(
                "Validated pool cannot satisfy the minimum historical-series diversity"
            )
        max_slot_marks = max(int(slot["marks"]) for slot in expanded_slots)
        for label, targets, actual in (
            ("topic", target_topics, topic_marks),
            ("assessment objective", target_objectives, objective_marks),
        ):
            if any(abs(actual[key] - target) > max_slot_marks for key, target in targets.items()):
                raise LookupError(
                    f"Validated pool cannot satisfy the reviewed {label} weighting within one question slot"
                )

        internal_questions: list[dict[str, Any]] = []
        response_questions: list[AssembledQuestion] = []
        source_mix = Counter(item.source_type.value for item in selected)
        for index, candidate in enumerate(selected, start=1):
            item_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{request.seed}:{index}:{candidate.source_id}"))
            capability = self._grader_capability(candidate.answer_surface)
            payload = {
                "item_id": item_id,
                "source_id": candidate.source_id,
                "source_type": candidate.source_type.value,
                "source_series": candidate.source_series,
                "source_paper_code": candidate.source_paper_code,
                "source_question_number": candidate.source_question_number,
                "answer_surface": candidate.answer_surface.value,
                "display_text": candidate.display_text,
                "marks_available": candidate.marks_available,
                "topic_tag": candidate.topic_tag,
                "assessment_objective_marks": candidate.assessment_objective_marks,
                "subparts": candidate.subparts,
                "resources": candidate.resources,
                "options": candidate.options,
                "correct_option_index": candidate.correct_option_index,
                "mark_scheme_chunk_ids": candidate.mark_scheme_chunk_ids,
                "grader_capability": capability,
            }
            internal_questions.append(payload)
            response_questions.append(
                AssembledQuestion.model_validate(
                    {
                        key: value
                        for key, value in payload.items()
                        if key not in {"correct_option_index", "mark_scheme_chunk_ids"}
                    }
                )
            )
        assembly = ExamAssembly(
            paper_number=spec.paper_number,
            title=spec.title,
            time_limit_minutes=spec.time_limit_minutes,
            total_marks=spec.total_marks,
            strict_timer=True,
            seed=request.seed,
            source_mix=dict(source_mix),
            source_series=sorted(selected_series),
            questions=internal_questions,
        )
        self.session.add(assembly)
        self.session.flush()
        return AssembledExamResponse(
            assembly_id=assembly.id,
            paper_number=assembly.paper_number,
            title=assembly.title,
            time_limit_minutes=assembly.time_limit_minutes,
            total_marks=assembly.total_marks,
            strict_timer=True,
            source_mix=assembly.source_mix,
            source_series=assembly.source_series,
            questions=response_questions,
        )

    def grade_mcq(
        self, assembly_id: str, item_id: str, selected_option_index: int
    ) -> MCQAnswerResponse:
        assembly = self.session.get(ExamAssembly, assembly_id)
        if assembly is None:
            raise KeyError(assembly_id)
        item = next((entry for entry in assembly.questions if entry["item_id"] == item_id), None)
        if item is None:
            raise KeyError(item_id)
        if item["answer_surface"] != "mcq" or item["correct_option_index"] is None:
            raise ValueError("assembled item is not an MCQ")
        correct_index = int(item["correct_option_index"])
        correct = selected_option_index == correct_index
        return MCQAnswerResponse(
            correct=correct,
            correct_option_index=correct_index,
            feedback=(
                "Correct. Your selection matches the validated concept answer."
                if correct
                else "Not yet. Review the linked topic explanation before trying a new practice set."
            ),
        )

    def get(self, assembly_id: str) -> AssembledExamResponse:
        assembly = self.session.get(ExamAssembly, assembly_id)
        if assembly is None:
            raise KeyError(assembly_id)
        questions = [
            AssembledQuestion.model_validate(
                {
                    key: value
                    for key, value in item.items()
                    if key not in {"correct_option_index", "mark_scheme_chunk_ids"}
                }
            )
            for item in assembly.questions
        ]
        return AssembledExamResponse(
            assembly_id=assembly.id,
            paper_number=assembly.paper_number,
            title=assembly.title,
            time_limit_minutes=assembly.time_limit_minutes,
            total_marks=assembly.total_marks,
            strict_timer=True,
            source_mix=assembly.source_mix,
            source_series=assembly.source_series,
            questions=questions,
        )

    def _candidates(self, paper_number: int) -> list[Candidate]:
        candidates: list[Candidate] = []
        rows = self.session.execute(
            select(Question, QuestionPresentation)
            .join(QuestionPresentation, QuestionPresentation.question_id == Question.id)
            .where(
                Question.paper_number == paper_number,
                QuestionPresentation.validation_status == "validated",
                QuestionPresentation.delivery_authorized.is_(True),
            )
        ).all()
        for question, presentation in rows:
            if presentation.requires_resources or presentation.resources:
                continue
            if not question.linked_mark_scheme_id:
                continue
            mark_scheme_chunks = list(
                self.session.scalars(
                    select(IngestionBlock).where(
                        IngestionBlock.question_id == question.id,
                        IngestionBlock.document_id == question.linked_mark_scheme_id,
                        IngestionBlock.block_type == "mark_scheme",
                        IngestionBlock.review_status.in_(("auto_trusted", "approved")),
                    )
                )
            )
            if not mark_scheme_chunks:
                continue
            candidates.append(
                Candidate(
                    source_id=question.id,
                    source_type=SourceType.past_paper,
                    answer_surface=AnswerSurface(presentation.answer_surface),
                    display_text=presentation.display_text,
                    marks_available=int(question.marks_available or 0),
                    topic_tag=str(question.topic_tag),
                    assessment_objective_marks=dict(
                        presentation.assessment_objective_marks or {}
                    ),
                    subparts=list(presentation.subparts or []),
                    resources=[],
                    source_series=question.series,
                    source_paper_code=question.paper_code,
                    source_question_number=question.question_number,
                    mark_scheme_chunk_ids=[chunk.id for chunk in mark_scheme_chunks],
                )
            )
        return candidates

    @staticmethod
    def _grader_capability(surface: AnswerSurface) -> str:
        if surface in {AnswerSurface.mcq, AnswerSurface.code}:
            return "available"
        return "gated"
