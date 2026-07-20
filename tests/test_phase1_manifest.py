import json
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from prepify.config import settings
from prepify.phase1.manifest import Paper4ManifestLoader
from prepify.storage.models import (
    Base,
    Document,
    GradingPhaseValidation,
    IngestionBlock,
    Paper4ResourceFile,
    Paper4TestCase,
    Question,
)


def test_manifest_requires_reviewed_mark_scheme_evidence_and_links_resources(
    tmp_path: Path,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    resource = tmp_path / "data.txt"
    resource.write_text("supplied data", encoding="utf-8")
    with Session(engine) as session:
        qp = Document(
            syllabus_code="9618",
            series="s23",
            document_type="question_paper",
            paper_code="41",
            paper_number=4,
            variant=1,
            source_path=str(tmp_path / "qp.pdf"),
            sha256="a" * 64,
        )
        ms = Document(
            syllabus_code="9618",
            series="s23",
            document_type="mark_scheme",
            paper_code="41",
            paper_number=4,
            variant=1,
            source_path=str(tmp_path / "ms.pdf"),
            sha256="b" * 64,
        )
        insert = Document(
            syllabus_code="9618",
            series="s23",
            document_type="insert",
            paper_code="41",
            paper_number=4,
            variant=1,
            source_path=str(tmp_path / "in.pdf"),
            sha256="c" * 64,
        )
        session.add_all([qp, ms, insert])
        session.flush()
        question = Question(
            document_id=qp.id,
            paper_code="41",
            series="s23",
            paper_number=4,
            question_number="1",
            marks_available=2,
            linked_mark_scheme_id=ms.id,
            linked_insert_id=insert.id,
        )
        session.add(question)
        session.flush()
        evidence = IngestionBlock(
            document_id=ms.id,
            question_id=question.id,
            fingerprint="d" * 64,
            page_number=2,
            block_type="mark_scheme",
            question_number="1",
            extraction_method="embedded_text",
            raw_text="Expected output is 4",
            review_status="approved",
            review_reasons=[],
        )
        session.add(evidence)
        validation = GradingPhaseValidation(
            phase="paper4_execution",
            status="validated",
            sample_count=20,
            exact_mark_match_rate=1.0,
            evidence={"sandbox_profile": {"images": "old"}},
        )
        session.add(validation)
        session.flush()
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "question_id": question.id,
                    "verified_by": "Teacher A, 2026-07-14",
                    "resources": [
                        {"filename": "data.txt", "source_path": str(resource)}
                    ],
                    "test_cases": [
                        {
                            "name": "official example",
                            "stdin": "2\n",
                            "expected_stdout": "4\n",
                            "marks_available": 2,
                            "expected_source_chunk_id": evidence.id,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        config = replace(
            settings,
            phase1_resource_root=str(tmp_path / "managed-resources"),
        )

        result = Paper4ManifestLoader(session, config).load(manifest_path)

        assert result["marks_available"] == 2
        assert len(list(session.scalars(select(Paper4TestCase)))) == 1
        stored = session.scalar(select(Paper4ResourceFile))
        assert stored is not None
        assert Path(stored.storage_path).read_text(encoding="utf-8") == "supplied data"
        assert validation.status == "blocked"
        assert validation.evidence["question_id"] == question.id


def test_manifest_rejects_path_like_resource_names() -> None:
    from prepify.phase1.schemas import Paper4ManifestResource

    with pytest.raises(ValueError):
        Paper4ManifestResource(filename="../secret.txt", source_path="secret.txt")
