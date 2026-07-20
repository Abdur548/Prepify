from __future__ import annotations

import json
from pathlib import Path

import typer

from prepify.ingestion.pipeline import IngestionPipeline
from prepify.storage.database import create_schema, session_scope
from prepify.storage.repository import Repository


app = typer.Typer(help="Prepify 9618 ingestion and OCR review workflow.")


@app.command("init-db")
def init_db() -> None:
    create_schema()
    typer.echo("Postgres schema is ready.")


@app.command()
def ingest(source_dir: Path = typer.Argument(..., exists=True, file_okay=False)) -> None:
    create_schema()
    with session_scope() as session:
        summary = IngestionPipeline(session).ingest_directory(source_dir)
        typer.echo(json.dumps(summary.__dict__, indent=2))


@app.command()
def reviews() -> None:
    with session_scope() as session:
        rows = Repository(session).pending_blocks()
        for row in rows:
            typer.echo(
                json.dumps(
                    {
                        "block_id": row.id,
                        "document_id": row.document_id,
                        "page_number": row.page_number,
                        "question_number": row.question_number,
                        "reasons": row.review_reasons,
                        "text": row.raw_text,
                    },
                    ensure_ascii=False,
                )
            )
        typer.echo(f"Pending review: {len(rows)}", err=True)


@app.command()
def approve(block_id: str) -> None:
    with session_scope() as session:
        repository = Repository(session)
        try:
            repository.approve_block(block_id)
        except KeyError as exc:
            raise typer.BadParameter(f"Unknown block id: {block_id}") from exc
        indexed = IngestionPipeline(session).index_ready()
        typer.echo(f"Approved {block_id}; indexed {indexed} ready block(s).")


if __name__ == "__main__":
    app()
