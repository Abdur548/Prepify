from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from prepify.ingestion.filenames import parse_document_identity
from prepify.ingestion.ocr import PDFExtractor
from prepify.ingestion.verification import review_decision
from prepify.retrieval.indexer import QdrantIndexer
from prepify.storage.models import Document
from prepify.storage.repository import Repository


@dataclass(frozen=True)
class IngestionSummary:
    files_processed: int
    blocks_persisted: int
    blocks_indexed: int
    pending_review: int


class IngestionPipeline:
    def __init__(self, session: Session):
        self.session = session
        self.repository = Repository(session)
        self.extractor = PDFExtractor()

    def ingest_directory(self, source_dir: Path) -> IngestionSummary:
        pdfs = sorted(source_dir.rglob("*.pdf"))
        if not pdfs:
            raise ValueError(f"No PDF files found under {source_dir}")
        block_count = 0
        for path in pdfs:
            identity = parse_document_identity(path)
            document = self.repository.upsert_document(path, identity)
            for parsed in self.extractor.extract(path, identity):
                row = self.repository.upsert_block(
                    document,
                    parsed,
                    review_decision(parsed),
                )
                self.repository.upsert_question(document, row)
                block_count += 1
        self.repository.link_documents_and_blocks()
        self.session.flush()
        indexed = self.index_ready()
        pending = len(self.repository.pending_blocks())
        return IngestionSummary(len(pdfs), block_count, indexed, pending)

    def index_ready(self) -> int:
        ready = self.repository.ready_blocks()
        if not ready:
            return 0
        rows: list[tuple] = []
        for block in ready:
            document = self.session.get(Document, block.document_id)
            if document is not None:
                rows.append((block, document))
        indexed_ids = QdrantIndexer().index(rows)
        self.repository.mark_indexed(indexed_ids)
        return len(indexed_ids)

