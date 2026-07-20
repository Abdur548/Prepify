from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from prepify.assembly.schemas import (
    PaperSpecificationManifest,
    QuestionPoolManifest,
)
from prepify.storage.models import (
    Document,
    IngestionBlock,
    PaperSpecification,
    Question,
    QuestionPresentation,
    ValidatedMCQ,
)
from prepify.topics import resolve_topic


class AssemblyManifestLoader:
    def __init__(self, session: Session):
        self.session = session

    def load_specification(self, path: Path) -> dict:
        manifest = PaperSpecificationManifest.model_validate_json(
            path.read_text(encoding="utf-8")
        )
        source_documents: list[Document] = []
        for document_id in manifest.source_question_paper_ids:
            document = self.session.get(Document, document_id)
            if document is None or document.document_type != "question_paper":
                raise ValueError("paper specification must cite ingested question papers")
            if document.paper_number != manifest.paper_number:
                raise ValueError("source question papers must match the specified paper number")
            source_documents.append(document)
        source_series = {document.series for document in source_documents}
        if len(source_series) < manifest.minimum_source_series:
            raise ValueError(
                "paper specification does not cite enough distinct historical series"
            )
        self._validate_chunks(
            manifest.source_chunk_ids,
            expected_types={"question"},
            document_ids={document.id for document in source_documents},
        )
        for topic_tag in manifest.topic_weights:
            resolve_topic(topic_tag)
        spec = self.session.scalar(
            select(PaperSpecification).where(
                PaperSpecification.paper_number == manifest.paper_number
            )
        )
        if spec is None:
            spec = PaperSpecification(paper_number=manifest.paper_number)
            self.session.add(spec)
        spec.title = manifest.title
        spec.time_limit_minutes = manifest.time_limit_minutes
        spec.total_marks = manifest.total_marks
        spec.topic_weights = self._normalized(manifest.topic_weights)
        spec.assessment_objective_weights = self._normalized(
            manifest.assessment_objective_weights
        )
        spec.slots = [slot.model_dump(mode="json") for slot in manifest.slots]
        spec.minimum_source_series = manifest.minimum_source_series
        spec.source_document_ids = manifest.source_question_paper_ids
        spec.source_chunk_ids = manifest.source_chunk_ids
        spec.review_status = "approved"
        spec.verified_by = manifest.verified_by
        self.session.flush()
        return {
            "paper_number": spec.paper_number,
            "time_limit_minutes": spec.time_limit_minutes,
            "total_marks": spec.total_marks,
            "slots": len(spec.slots),
            "verified_by": spec.verified_by,
        }

    def load_pool(self, path: Path) -> dict:
        manifest = QuestionPoolManifest.model_validate_json(
            path.read_text(encoding="utf-8")
        )
        loaded_real = 0
        for item in manifest.past_paper_questions:
            question = self.session.get(Question, item.question_id)
            if question is None:
                raise ValueError(f"unknown question: {item.question_id}")
            expected_surface = {1: "written", 2: "pseudocode", 3: "written", 4: "code"}[
                question.paper_number
            ]
            if item.answer_surface != expected_surface:
                raise ValueError(
                    f"Paper {question.paper_number} requires the {expected_surface} surface"
                )
            if question.marks_available is None:
                raise ValueError("question marks_available must be verified before presentation")
            if sum(item.assessment_objective_marks.values()) != question.marks_available:
                raise ValueError("question assessment-objective marks must equal marks_available")
            if (
                item.subparts
                and sum(part.marks_available for part in item.subparts)
                != question.marks_available
            ):
                raise ValueError("sub-part marks must equal question marks_available")
            if item.requires_resources or item.resources:
                raise ValueError("insert/data-file dependent questions are deferred")
            trusted_question = self.session.scalar(
                select(IngestionBlock).where(
                    IngestionBlock.question_id == question.id,
                    IngestionBlock.block_type == "question",
                    IngestionBlock.review_status.in_(("auto_trusted", "approved")),
                )
            )
            if trusted_question is None:
                raise ValueError("question has no reviewed ingestion block")
            if not question.linked_mark_scheme_id:
                raise ValueError("question has no matching mark-scheme document")
            trusted_mark_scheme = self.session.scalar(
                select(IngestionBlock).where(
                    IngestionBlock.question_id == question.id,
                    IngestionBlock.document_id == question.linked_mark_scheme_id,
                    IngestionBlock.block_type == "mark_scheme",
                    IngestionBlock.review_status.in_(("auto_trusted", "approved")),
                )
            )
            if trusted_mark_scheme is None:
                raise ValueError("question has no reviewed matching mark-scheme block")
            if not question.topic_tag:
                raise ValueError("question needs an official topic_tag before assembly")
            resolve_topic(question.topic_tag)
            row = self.session.scalar(
                select(QuestionPresentation).where(
                    QuestionPresentation.question_id == question.id
                )
            )
            if row is None:
                row = QuestionPresentation(question_id=question.id)
                self.session.add(row)
            row.answer_surface = item.answer_surface
            row.display_text = item.display_text
            row.subparts = [part.model_dump(mode="json") for part in item.subparts]
            row.resources = [resource.model_dump(mode="json") for resource in item.resources]
            row.assessment_objective_marks = item.assessment_objective_marks
            row.requires_resources = item.requires_resources
            row.delivery_authorized = True
            row.validation_status = "validated"
            row.verified_by = item.verified_by
            loaded_real += 1

        loaded_mcq = 0
        for item in manifest.validated_mcqs:
            resolve_topic(item.topic_tag)
            self._validate_chunks(
                item.source_chunk_ids,
                expected_types={"question", "mark_scheme"},
            )
            row = self.session.scalar(
                select(ValidatedMCQ).where(
                    ValidatedMCQ.question_text == item.question_text,
                    ValidatedMCQ.topic_tag == item.topic_tag,
                )
            )
            if row is None:
                row = ValidatedMCQ()
                self.session.add(row)
            row.question_text = item.question_text
            row.options = item.options
            row.correct_option_index = item.correct_option_index
            row.topic_tag = item.topic_tag
            row.difficulty = item.difficulty
            row.source_chunk_ids = item.source_chunk_ids
            row.assessment_objective_marks = item.assessment_objective_marks
            row.marks_available = item.marks_available
            row.validation_status = "validated"
            row.verified_by = item.verified_by
            loaded_mcq += 1
        self.session.flush()
        return {
            "past_paper_questions": loaded_real,
            "validated_mcqs": loaded_mcq,
        }

    def _validate_chunks(
        self,
        chunk_ids: list[str],
        *,
        expected_types: set[str],
        document_ids: set[str] | None = None,
    ) -> None:
        for chunk_id in chunk_ids:
            chunk = self.session.get(IngestionBlock, chunk_id)
            if chunk is None:
                raise ValueError(f"unknown source chunk: {chunk_id}")
            if chunk.block_type not in expected_types:
                raise ValueError(f"chunk {chunk_id} has the wrong source type")
            if document_ids is not None and chunk.document_id not in document_ids:
                raise ValueError(f"chunk {chunk_id} is not from a cited question paper")
            if chunk.review_status not in {"auto_trusted", "approved"}:
                raise ValueError(f"chunk {chunk_id} has not passed OCR review")

    @staticmethod
    def _normalized(weights: dict[str, float]) -> dict[str, float]:
        total = sum(weights.values())
        return {key: value / total for key, value in weights.items()}
