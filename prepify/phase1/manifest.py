from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from prepify.config import Settings, settings
from prepify.phase1.schemas import Paper4Manifest
from prepify.storage.models import (
    IngestionBlock,
    GradingPhaseValidation,
    Paper4ResourceFile,
    Paper4TestCase,
    Question,
)


RESERVED_FILENAMES = {"submission.py", "main.java", "program.vb", "submission.vbproj"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_manifest(path: Path) -> Paper4Manifest:
    return Paper4Manifest.model_validate(json.loads(path.read_text(encoding="utf-8")))


class Paper4ManifestLoader:
    """Loads human-verified expected outputs; no LLM derives grading cases."""

    def __init__(self, session: Session, config: Settings = settings):
        self.session = session
        self.config = config

    def load(self, manifest_path: Path) -> dict:
        manifest_path = manifest_path.resolve()
        manifest = read_manifest(manifest_path)
        question = self.session.get(Question, manifest.question_id)
        if question is None:
            raise KeyError(manifest.question_id)
        if question.paper_number != 4:
            raise ValueError("Phase 1 manifests can be loaded for Paper 4 questions only")
        test_marks = sum(item.marks_available for item in manifest.test_cases)
        if question.marks_available is None:
            raise ValueError("Question marks_available must be verified before loading a manifest")
        if test_marks != question.marks_available:
            raise ValueError(
                f"Test marks total {test_marks}, but question marks_available is {question.marks_available}"
            )
        if manifest.resources and not question.linked_insert_id:
            raise ValueError("Resource files require a linked Paper 4 insert document")

        for test_case in manifest.test_cases:
            source = self.session.get(IngestionBlock, test_case.expected_source_chunk_id)
            if source is None:
                raise ValueError(
                    f"Unknown expected-output source chunk: {test_case.expected_source_chunk_id}"
                )
            if source.block_type != "mark_scheme" or source.question_id != question.id:
                raise ValueError("Each expected output must cite this question's mark-scheme chunk")
            if source.review_status not in {"auto_trusted", "approved"}:
                raise ValueError("Expected-output source chunk has not passed OCR review")

        resource_root = Path(self.config.phase1_resource_root).resolve()
        resource_root.mkdir(parents=True, exist_ok=True)
        target_dir = (resource_root / question.id).resolve()
        if target_dir.parent != resource_root:
            raise ValueError("question id produced an unsafe resource path")
        staged_dir = Path(tempfile.mkdtemp(prefix=f"{question.id}-", dir=resource_root))
        staged_resources: list[tuple] = []
        total_size = 0
        try:
            for resource in manifest.resources:
                if resource.filename.casefold() in RESERVED_FILENAMES:
                    raise ValueError(f"resource filename is reserved: {resource.filename}")
                source_path = Path(resource.source_path)
                if not source_path.is_absolute():
                    source_path = manifest_path.parent / source_path
                source_path = source_path.resolve()
                if not source_path.is_file():
                    raise ValueError(f"resource file does not exist: {source_path}")
                size = source_path.stat().st_size
                total_size += size
                if total_size > self.config.sandbox_max_resource_bytes:
                    raise ValueError("manifest resources exceed sandbox size limit")
                staged_path = staged_dir / resource.filename
                shutil.copy2(source_path, staged_path)
                staged_resources.append((resource, size, _sha256(staged_path)))

            if target_dir.exists():
                shutil.rmtree(target_dir)
            staged_dir.replace(target_dir)
        except Exception:
            shutil.rmtree(staged_dir, ignore_errors=True)
            raise

        self.session.execute(
            delete(Paper4TestCase).where(Paper4TestCase.question_id == question.id)
        )
        self.session.execute(
            delete(Paper4ResourceFile).where(Paper4ResourceFile.question_id == question.id)
        )
        for ordinal, test_case in enumerate(manifest.test_cases, start=1):
            self.session.add(
                Paper4TestCase(
                    question_id=question.id,
                    ordinal=ordinal,
                    name=test_case.name,
                    stdin=test_case.stdin,
                    arguments=test_case.arguments,
                    expected_stdout=test_case.expected_stdout,
                    marks_available=test_case.marks_available,
                    comparison_mode=test_case.comparison_mode.value,
                    expected_source_chunk_id=test_case.expected_source_chunk_id,
                    verified_by=manifest.verified_by,
                )
            )
        for resource, size, digest in staged_resources:
            self.session.add(
                Paper4ResourceFile(
                    question_id=question.id,
                    insert_document_id=question.linked_insert_id,
                    filename=resource.filename,
                    storage_path=str(target_dir / resource.filename),
                    sha256=digest,
                    size_bytes=size,
                    verified_by=manifest.verified_by,
                )
            )
        validation = self.session.get(GradingPhaseValidation, "paper4_execution")
        if validation is not None:
            validation.status = "blocked"
            validation.validated_at = None
            validation.evidence = {
                "invalidation_reason": "Paper 4 test/resource manifest changed",
                "question_id": question.id,
            }
        self.session.flush()
        return {
            "question_id": question.id,
            "test_cases": len(manifest.test_cases),
            "marks_available": test_marks,
            "resources": len(staged_resources),
            "verified_by": manifest.verified_by,
        }
