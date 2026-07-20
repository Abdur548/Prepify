import json

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from prepify.assembly.manifest import AssemblyManifestLoader
from prepify.assembly.schemas import AssembleExamRequest, PaperSpecificationManifest
from prepify.assembly.service import ExamAssembler
from prepify.storage.models import (
    Base,
    Document,
    ExamAssembly,
    IngestionBlock,
    PaperSpecification,
    Question,
    QuestionPresentation,
)


def add_document(session, tmp_path, kind, paper_code, paper_number, series):
    document = Document(
        syllabus_code="9618",
        series=series,
        document_type=kind,
        paper_code=paper_code,
        paper_number=paper_number,
        variant=int(paper_code[-1]),
        source_path=str(tmp_path / f"9618_{series}_{kind}_{paper_code}.pdf"),
        sha256=(f"{kind}-{series}" * 16)[:64].ljust(64, "a"),
    )
    session.add(document)
    session.flush()
    return document


def add_written_candidate(session, qp, ms, number, topic, ao):
    question = Question(
        document_id=qp.id,
        paper_code=qp.paper_code,
        series=qp.series,
        paper_number=qp.paper_number,
        question_number=number,
        marks_available=2,
        topic_tag=topic,
        linked_mark_scheme_id=ms.id,
    )
    session.add(question)
    session.flush()
    session.add_all(
        [
            IngestionBlock(
                document_id=qp.id,
                question_id=question.id,
                fingerprint=(f"q-{qp.series}-{number}" * 16)[:64].ljust(64, "q"),
                page_number=1,
                block_type="question",
                question_number=number,
                extraction_method="embedded_text",
                raw_text=f"Explain {topic}.",
                review_status="auto_trusted",
            ),
            IngestionBlock(
                document_id=ms.id,
                question_id=question.id,
                fingerprint=(f"m-{ms.series}-{number}" * 16)[:64].ljust(64, "m"),
                page_number=1,
                block_type="mark_scheme",
                question_number=number,
                point_label="MP1",
                extraction_method="embedded_text",
                raw_text=f"Reviewed marking evidence for {topic}.",
                review_status="approved",
            ),
            QuestionPresentation(
                question_id=question.id,
                answer_surface="written",
                display_text=f"Explain {topic}.",
                subparts=[{"label": "(a)", "marks_available": 2, "prompt": "Explain."}],
                resources=[],
                assessment_objective_marks={ao: 2},
                requires_resources=False,
                delivery_authorized=True,
                validation_status="validated",
                verified_by="Teacher A",
            ),
        ]
    )
    session.flush()
    return question


def test_assembler_uses_multiple_series_and_private_mark_scheme_evidence(tmp_path) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        qp1 = add_document(session, tmp_path, "question_paper", "31", 3, "s23")
        ms1 = add_document(session, tmp_path, "mark_scheme", "31", 3, "s23")
        qp2 = add_document(session, tmp_path, "question_paper", "31", 3, "w24")
        ms2 = add_document(session, tmp_path, "mark_scheme", "31", 3, "w24")
        first = add_written_candidate(session, qp1, ms1, "1", "Artificial Intelligence", "AO1")
        second = add_written_candidate(session, qp2, ms2, "2", "Recursion", "AO2")
        session.add(
            PaperSpecification(
                paper_number=3,
                title="Paper 3 Advanced Theory",
                time_limit_minutes=90,
                total_marks=4,
                topic_weights={"Artificial Intelligence": 0.5, "Recursion": 0.5},
                assessment_objective_weights={"AO1": 0.5, "AO2": 0.5},
                slots=[{
                    "answer_surface": "written",
                    "marks": 2,
                    "count": 2,
                    "allowed_source_types": ["past_paper"],
                }],
                minimum_source_series=2,
                source_document_ids=[qp1.id, qp2.id],
                source_chunk_ids=["reviewed-question-chunks"],
                review_status="approved",
                verified_by="Teacher A",
            )
        )
        session.flush()

        result = ExamAssembler(session).assemble(
            AssembleExamRequest(paper_number=3, seed="deterministic")
        )

        assert result.time_limit_minutes == 90
        assert result.total_marks == 4
        assert result.source_series == ["s23", "w24"]
        assert {item.source_id for item in result.questions} == {first.id, second.id}
        assert {item.source_series for item in result.questions} == {"s23", "w24"}
        assert all(item.source_type.value == "past_paper" for item in result.questions)
        serialized = result.model_dump(mode="json")
        assert "mark_scheme_chunk_ids" not in serialized["questions"][0]
        stored = session.get(ExamAssembly, result.assembly_id)
        assert all(item["mark_scheme_chunk_ids"] for item in stored.questions)


def test_full_exam_spec_rejects_generated_mcq_sources() -> None:
    with pytest.raises(ValidationError, match="past-paper questions only"):
        PaperSpecificationManifest(
            paper_number=1,
            title="Paper 1",
            time_limit_minutes=90,
            total_marks=2,
            topic_weights={"Data Representation": 1.0},
            assessment_objective_weights={"AO1": 1.0},
            slots=[{
                "answer_surface": "mcq",
                "marks": 1,
                "count": 2,
                "allowed_source_types": ["validated_mcq"],
            }],
            source_question_paper_ids=["one", "two"],
            source_chunk_ids=["chunk"],
            verified_by="Teacher",
        )


def test_novel_generation_cannot_be_enabled_silently() -> None:
    with pytest.raises(ValidationError):
        AssembleExamRequest(paper_number=1, allow_novel_generation=True)


def test_strict_exam_timer_cannot_be_disabled() -> None:
    with pytest.raises(ValidationError):
        AssembleExamRequest(paper_number=1, strict_timer=False)


def test_question_pool_rejects_insert_dependent_questions(tmp_path) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        qp = add_document(session, tmp_path, "question_paper", "41", 4, "s23")
        ms = add_document(session, tmp_path, "mark_scheme", "41", 4, "s23")
        question = add_written_candidate(
            session,
            qp,
            ms,
            "1",
            "File Processing and Exception Handling",
            "AO3",
        )
        manifest_path = tmp_path / "pool.json"
        manifest_path.write_text(
            json.dumps({
                "past_paper_questions": [{
                    "question_id": question.id,
                    "answer_surface": "code",
                    "display_text": "Read Records.txt and output the result.",
                    "resources": [{
                        "name": "Records.txt",
                        "media_type": "text/plain",
                        "content": "A104,73",
                    }],
                    "assessment_objective_marks": {"AO3": 2},
                    "requires_resources": True,
                    "delivery_authorized": True,
                    "verified_by": "Teacher A",
                }]
            }),
            encoding="utf-8",
        )

        with pytest.raises(ValidationError, match="deferred from assembly"):
            AssemblyManifestLoader(session).load_pool(manifest_path)


def test_specification_rejects_guessed_or_incomplete_weights() -> None:
    with pytest.raises(ValidationError, match="weights must total"):
        PaperSpecificationManifest(
            paper_number=1,
            title="Paper 1",
            time_limit_minutes=90,
            total_marks=2,
            topic_weights={"Data Representation": 0.4},
            assessment_objective_weights={"AO1": 1.0},
            slots=[{
                "answer_surface": "written",
                "marks": 1,
                "count": 2,
                "allowed_source_types": ["past_paper"],
            }],
            source_question_paper_ids=["one", "two"],
            source_chunk_ids=["chunk"],
            verified_by="Teacher",
        )
