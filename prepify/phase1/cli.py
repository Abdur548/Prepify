from __future__ import annotations

import json
from pathlib import Path

import typer

from prepify.phase1.grader import Paper4CodeExecutionGrader
from prepify.phase1.manifest import Paper4ManifestLoader
from prepify.phase1.repository import Paper4Repository
from prepify.phase1.sandbox import DockerSandbox
from prepify.phase1.validation import Phase1ValidationRunner
from prepify.storage.database import create_schema, session_scope
from prepify.storage.models import GradingPhaseValidation


app = typer.Typer(help="MVP2 Phase 1 Paper 4 grading administration.")


@app.command("load-manifest")
def load_manifest(path: Path = typer.Argument(..., exists=True, dir_okay=False)) -> None:
    create_schema()
    # Fail closed before any file or test-definition mutation begins.
    with session_scope() as session:
        Paper4Repository(session).record_validation(
            status="blocked",
            sample_count=0,
            exact_match_rate=0.0,
            evidence={"invalidation_reason": "Paper 4 manifest load initiated"},
        )
    with session_scope() as session:
        result = Paper4ManifestLoader(session).load(path)
        typer.echo(json.dumps(result, indent=2))


@app.command()
def validate(dataset: Path = typer.Argument(..., exists=True, dir_okay=False)) -> None:
    create_schema()
    # Commit the blocked state before executing any untrusted held-out submission.
    with session_scope() as session:
        Paper4Repository(session).record_validation(
            status="blocked",
            sample_count=0,
            exact_match_rate=0.0,
            evidence={"invalidation_reason": "Phase 1 validation run initiated"},
        )
    with session_scope() as session:
        repository = Paper4Repository(session)
        grader = Paper4CodeExecutionGrader(repository)
        report = Phase1ValidationRunner(repository, grader).run(dataset)
        typer.echo(report.model_dump_json(indent=2))
        if report.status != "validated":
            raise typer.Exit(code=2)


@app.command()
def status() -> None:
    with session_scope() as session:
        row = session.get(GradingPhaseValidation, "paper4_execution")
        effective_status = Paper4Repository(session).validation_status(
            sandbox_profile=DockerSandbox().profile
        )
        typer.echo(
            json.dumps(
                {
                    "phase": "paper4_execution",
                    "status": effective_status,
                    "stored_status": row.status if row else "blocked",
                    "sample_count": row.sample_count if row else 0,
                    "exact_mark_match_rate": row.exact_mark_match_rate if row else 0.0,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    app()
