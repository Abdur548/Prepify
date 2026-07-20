from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from prepify.ingestion.filenames import DocumentIdentity
from prepify.ingestion.verification import ReviewDecision
from prepify.schemas import OCRBlock
from prepify.storage.models import Document, IngestionBlock, InteractionEvent, Question, utcnow


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def block_fingerprint(block: OCRBlock) -> str:
    value = f"{block.page_number}|{block.block_type}|{block.question_number}|{block.text}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class Repository:
    def __init__(self, session: Session):
        self.session = session

    def upsert_document(self, path: Path, identity: DocumentIdentity) -> Document:
        source_path = str(path.resolve())
        document = self.session.scalar(select(Document).where(Document.source_path == source_path))
        if document is None:
            document = Document(
                syllabus_code=identity.syllabus_code,
                series=identity.series,
                document_type=identity.document_type,
                paper_code=identity.paper_code,
                paper_number=identity.paper_number,
                variant=identity.variant,
                source_path=source_path,
                sha256=sha256_file(path),
            )
            self.session.add(document)
            self.session.flush()
        return document

    def upsert_block(
        self,
        document: Document,
        block: OCRBlock,
        decision: ReviewDecision,
    ) -> IngestionBlock:
        fingerprint = block_fingerprint(block)
        row = self.session.scalar(
            select(IngestionBlock).where(
                IngestionBlock.document_id == document.id,
                IngestionBlock.fingerprint == fingerprint,
            )
        )
        if row is None:
            row = IngestionBlock(
                document_id=document.id,
                fingerprint=fingerprint,
                page_number=block.page_number,
                block_type=block.block_type,
                question_number=block.question_number,
                parent_question_number=block.parent_question_number,
                point_label=block.point_label,
                topic_tag=block.topic_tag,
                marks_available=block.marks_available,
                extraction_method=block.extraction_method,
                raw_text=block.text,
                review_status=decision.status,
                review_reasons=list(decision.reasons),
            )
            self.session.add(row)
            self.session.flush()
        return row

    def upsert_question(self, document: Document, block: IngestionBlock) -> Question | None:
        if document.document_type != "question_paper" or not block.question_number:
            return None
        question = self.session.scalar(
            select(Question).where(
                Question.document_id == document.id,
                Question.question_number == block.question_number,
            )
        )
        if question is None:
            question = Question(
                document_id=document.id,
                paper_code=document.paper_code or str(document.paper_number),
                series=document.series,
                paper_number=document.paper_number or 0,
                question_number=block.question_number,
                topic_tag=block.topic_tag,
                marks_available=block.marks_available,
            )
            self.session.add(question)
            self.session.flush()
        else:
            question.topic_tag = question.topic_tag or block.topic_tag
            question.marks_available = question.marks_available or block.marks_available
        block.question_id = question.id
        return question

    def link_documents_and_blocks(self) -> None:
        documents = list(self.session.scalars(select(Document)))
        by_key: dict[tuple[str, str, str | None, str], Document] = {
            (doc.syllabus_code, doc.series, doc.paper_code, doc.document_type): doc
            for doc in documents
        }
        questions = list(self.session.scalars(select(Question)))
        for question in questions:
            qp = self.session.get(Document, question.document_id)
            if qp is None:
                continue
            base = (qp.syllabus_code, qp.series, qp.paper_code)
            mark_scheme = by_key.get((*base, "mark_scheme"))
            question.linked_mark_scheme_id = mark_scheme.id if mark_scheme else None
            question.linked_insert_id = None

            if mark_scheme:
                self._attach_blocks(mark_scheme.id, question)

        for question in questions:
            qp = self.session.get(Document, question.document_id)
            if qp is None:
                continue
            blocks = list(
                self.session.scalars(
                    select(IngestionBlock).where(IngestionBlock.question_id == question.id)
                )
            )
            parent_number = next((b.parent_question_number for b in blocks if b.parent_question_number), None)
            if parent_number:
                parent = self.session.scalar(
                    select(Question).where(
                        Question.document_id == qp.id,
                        Question.question_number == parent_number,
                    )
                )
                question.parent_question_id = parent.id if parent else None

    def _attach_blocks(self, document_id: str, question: Question) -> None:
        rows = list(
            self.session.scalars(
                select(IngestionBlock).where(IngestionBlock.document_id == document_id)
            )
        )
        for row in rows:
            if row.question_number == question.question_number:
                row.question_id = question.id

    def ready_blocks(self) -> list[IngestionBlock]:
        return list(
            self.session.scalars(
                select(IngestionBlock).where(
                    IngestionBlock.review_status.in_(("auto_trusted", "approved")),
                    IngestionBlock.indexed.is_(False),
                )
            )
        )

    def pending_blocks(self) -> list[IngestionBlock]:
        return list(
            self.session.scalars(
                select(IngestionBlock).where(IngestionBlock.review_status == "pending_review")
            )
        )

    def approve_block(self, block_id: str) -> IngestionBlock:
        block = self.session.get(IngestionBlock, block_id)
        if block is None:
            raise KeyError(block_id)
        block.review_status = "approved"
        return block

    def mark_indexed(self, block_ids: list[str]) -> None:
        for block_id in block_ids:
            block = self.session.get(IngestionBlock, block_id)
            if block:
                block.indexed = True
                block.indexed_at = utcnow()

    def get_question(self, question_id: str) -> Question | None:
        return self.session.get(Question, question_id)

    def log_event(
        self,
        event_type: str,
        *,
        question_id: str | None = None,
        topic_tag: str | None = None,
        payload: dict | None = None,
    ) -> None:
        self.session.add(
            InteractionEvent(
                event_type=event_type,
                question_id=question_id,
                topic_tag=topic_tag,
                payload=payload or {},
            )
        )
