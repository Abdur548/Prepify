from __future__ import annotations

import json
import uuid
from pathlib import Path

from prepify.config import Settings, settings
from prepify.phase1.grader import Paper4CodeExecutionGrader
from prepify.phase1.repository import Paper4Repository
from prepify.phase1.schemas import (
    Paper4GradeRequest,
    Phase1ValidationDataset,
    Phase1ValidationReport,
)


def read_validation_dataset(path: Path) -> Phase1ValidationDataset:
    return Phase1ValidationDataset.model_validate(
        json.loads(path.read_text(encoding="utf-8"))
    )


class Phase1ValidationRunner:
    """Hard gate using held-out real submissions with known official marks."""

    def __init__(
        self,
        repository: Paper4Repository,
        grader: Paper4CodeExecutionGrader,
        config: Settings = settings,
    ):
        self.repository = repository
        self.grader = grader
        self.config = config

    def run(self, dataset_path: Path) -> Phase1ValidationReport:
        dataset = read_validation_dataset(dataset_path.resolve())
        run_id = str(uuid.uuid4())
        reasons: list[str] = []
        sample_count = len(dataset.submissions)
        if sample_count < self.config.phase1_validation_min_submissions:
            reasons.append(
                f"Need at least {self.config.phase1_validation_min_submissions} held-out submissions; got {sample_count}."
            )
        if not self.grader.sandbox.images_are_digest_pinned:
            reasons.append("All sandbox image references must be pinned by sha256 digest.")
        observed_languages = {submission.language.value for submission in dataset.submissions}
        required_languages = {"python", "java", "visual_basic"}
        missing_languages = sorted(required_languages - observed_languages)
        if missing_languages:
            reasons.append(
                "Held-out validation must cover every supported Paper 4 language; missing: "
                + ", ".join(missing_languages)
                + "."
            )

        exact_matches = 0
        completed = 0
        outcomes = []
        for submission in dataset.submissions:
            source_path = Path(submission.source_path)
            if not source_path.is_absolute():
                source_path = dataset_path.parent / source_path
            source_path = source_path.resolve()
            source_code = source_path.read_text(encoding="utf-8")
            response = self.grader.grade(
                submission.question_id,
                Paper4GradeRequest(
                    language=submission.language,
                    source_code=source_code,
                ),
                validation_run_id=run_id,
            )
            is_complete = response.status == "completed" and response.marks_awarded is not None
            if is_complete:
                completed += 1
            matched = is_complete and response.marks_awarded == submission.official_mark
            if matched:
                exact_matches += 1
            outcomes.append(
                {
                    "attempt_id": response.attempt_id,
                    "question_id": submission.question_id,
                    "official_mark": submission.official_mark,
                    "predicted_mark": response.marks_awarded,
                    "complete": is_complete,
                    "exact_match": matched,
                    "provenance": submission.provenance,
                }
            )

        exact_rate = exact_matches / sample_count if sample_count else 0.0
        if completed != sample_count:
            reasons.append("Every validation submission must complete without sandbox infrastructure errors.")
        if exact_rate != 1.0:
            reasons.append("Every held-out submission must exactly match its official mark.")
        status = "validated" if not reasons else "blocked"
        evidence = {
            "run_id": run_id,
            "dataset_name": dataset.dataset_name,
            "outcomes": outcomes,
            "languages": sorted(observed_languages),
            "reasons": reasons,
            "sandbox_profile": self.grader.sandbox.profile,
        }
        self.repository.record_validation(
            status=status,
            sample_count=sample_count,
            exact_match_rate=exact_rate,
            evidence=evidence,
        )
        return Phase1ValidationReport(
            run_id=run_id,
            status=status,
            sample_count=sample_count,
            completed_count=completed,
            exact_mark_matches=exact_matches,
            exact_mark_match_rate=exact_rate,
            reasons=reasons,
        )
