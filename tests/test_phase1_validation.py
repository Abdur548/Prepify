import json
from dataclasses import replace
from types import SimpleNamespace

from prepify.config import settings
from prepify.phase1.validation import Phase1ValidationRunner
from prepify.phase1.repository import Paper4Repository
from prepify.storage.models import Base, GradingPhaseValidation
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


class FakeValidationRepository:
    def __init__(self):
        self.recorded = None

    def record_validation(self, **kwargs):
        self.recorded = kwargs


class FakeValidationGrader:
    def __init__(self, pinned=True):
        self.sandbox = SimpleNamespace(
            images_are_digest_pinned=pinned,
            profile={"images": "pinned" if pinned else "tags"},
        )

    def grade(self, question_id, request, validation_run_id=None):
        return SimpleNamespace(
            attempt_id=f"attempt-{question_id}-{request.language.value}",
            status="completed",
            marks_awarded=1,
        )


def write_dataset(tmp_path, languages):
    submissions = []
    for index, language in enumerate(languages):
        source = tmp_path / f"submission-{index}.txt"
        source.write_text("print(1)", encoding="utf-8")
        submissions.append(
            {
                "question_id": f"q{index}",
                "language": language,
                "source_path": str(source),
                "official_mark": 1,
                "provenance": "Officially marked held-out response",
                "held_out": True,
            }
        )
    dataset = tmp_path / "validation.json"
    dataset.write_text(
        json.dumps({"dataset_name": "real held-out set", "submissions": submissions}),
        encoding="utf-8",
    )
    return dataset


def test_validation_remains_blocked_without_all_languages(tmp_path) -> None:
    repository = FakeValidationRepository()
    runner = Phase1ValidationRunner(
        repository,
        FakeValidationGrader(pinned=True),
        replace(settings, phase1_validation_min_submissions=2),
    )

    report = runner.run(write_dataset(tmp_path, ["python", "java"]))

    assert report.status == "blocked"
    assert any("visual_basic" in reason for reason in report.reasons)
    assert repository.recorded["status"] == "blocked"


def test_validation_can_open_gate_only_with_pinned_images_full_coverage_and_exact_marks(
    tmp_path,
) -> None:
    repository = FakeValidationRepository()
    runner = Phase1ValidationRunner(
        repository,
        FakeValidationGrader(pinned=True),
        replace(settings, phase1_validation_min_submissions=3),
    )

    report = runner.run(
        write_dataset(tmp_path, ["python", "java", "visual_basic"])
    )

    assert report.status == "validated"
    assert report.exact_mark_match_rate == 1.0
    assert repository.recorded["status"] == "validated"


def test_changed_sandbox_profile_blocks_stale_validation() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            GradingPhaseValidation(
                phase="paper4_execution",
                status="validated",
                sample_count=20,
                exact_mark_match_rate=1.0,
                evidence={"sandbox_profile": {"images": "validated"}},
            )
        )
        session.flush()
        repository = Paper4Repository(session)

        assert repository.validation_status(
            sandbox_profile={"images": "validated"}
        ) == "validated"
        assert repository.validation_status(
            sandbox_profile={"images": "changed"}
        ) == "blocked"
