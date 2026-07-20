from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from prepify.ingestion.filenames import parse_document_identity
from prepify.ingestion.ocr import segment_embedded_text
from prepify.ingestion.verification import review_decision
from prepify.schemas import OCRBlock
from prepify.storage.models import Base
from prepify.storage.repository import Repository


def test_question_and_mark_scheme_share_link_key() -> None:
    question = parse_document_identity(Path("9618_s23_qp_21.pdf"))
    mark_scheme = parse_document_identity(Path("9618_s23_ms_21.pdf"))

    assert question.document_type == "question_paper"
    assert mark_scheme.document_type == "mark_scheme"
    assert question.paper_number == 2
    assert question.variant == 1
    assert question.link_key == mark_scheme.link_key
    with pytest.raises(ValueError, match="only matching question papers and mark schemes"):
        parse_document_identity(Path("9618_s23_in_21.pdf"))
    with pytest.raises(ValueError, match="only matching question papers and mark schemes"):
        parse_document_identity(Path("9618_s23_er.pdf"))


def test_qwen_pseudocode_is_held_for_review() -> None:
    block = OCRBlock(
        text="FOR Index ← 1 TO 10\n  Total ← Total + Values[Index]\nNEXT Index",
        page_number=3,
        block_type="question",
        question_number="6(a)",
        extraction_method="qwen3_vl_ocr",
    )

    decision = review_decision(block)

    assert decision.status == "pending_review"
    assert "assignment_arrow" in decision.reasons
    assert "pseudocode_control" in decision.reasons


def test_embedded_text_is_not_sent_to_ocr_review_queue() -> None:
    block = OCRBlock(
        text="Value ← Value DIV 2",
        page_number=1,
        block_type="question",
        extraction_method="embedded_text",
    )

    assert review_decision(block).status == "auto_trusted"


def test_repository_links_question_and_matching_mark_scheme(tmp_path: Path) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    paths = {
        kind: tmp_path / f"9618_s23_{kind}_21.pdf"
        for kind in ("qp", "ms")
    }
    for path in paths.values():
        path.write_bytes(b"test-pdf-placeholder")

    with Session(engine) as session:
        repository = Repository(session)
        documents = {
            kind: repository.upsert_document(path, parse_document_identity(path))
            for kind, path in paths.items()
        }
        qp = OCRBlock(
            text="6(a) Explain the stopping condition.",
            page_number=2,
            block_type="question",
            question_number="6(a)",
            extraction_method="embedded_text",
        )
        ms = OCRBlock(
            text="6(a) Identifies the stopping condition.",
            page_number=4,
            block_type="mark_scheme",
            question_number="6(a)",
            point_label="MP1",
            extraction_method="embedded_text",
        )
        qp_row = repository.upsert_block(documents["qp"], qp, review_decision(qp))
        question = repository.upsert_question(documents["qp"], qp_row)
        ms_row = repository.upsert_block(documents["ms"], ms, review_decision(ms))

        repository.link_documents_and_blocks()
        session.flush()

        assert question is not None
        assert question.linked_mark_scheme_id == documents["ms"].id
        assert question.linked_insert_id is None
        assert ms_row.question_id == question.id


def test_embedded_parser_carries_question_number_into_subparts() -> None:
    identity = parse_document_identity("9618_s23_qp_21.pdf")
    blocks = segment_embedded_text(
        "(d) Describe the algorithm.\n(i) State its stopping condition.",
        page_number=3,
        identity=identity,
        previous_question="8(c)",
    )

    assert [block.question_number for block in blocks] == ["8(d)", "8(d)(i)"]
    assert blocks[1].parent_question_number == "8(d)"
