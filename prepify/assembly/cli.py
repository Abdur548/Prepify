from __future__ import annotations

import json
from pathlib import Path

import typer

from prepify.assembly.manifest import AssemblyManifestLoader
from prepify.storage.database import create_schema, session_scope


app = typer.Typer(help="MVP3 reviewed specification and question-pool administration.")


@app.command("load-specification")
def load_specification(path: Path = typer.Argument(..., exists=True, dir_okay=False)) -> None:
    create_schema()
    with session_scope() as session:
        result = AssemblyManifestLoader(session).load_specification(path)
        typer.echo(json.dumps(result, indent=2))


@app.command("load-pool")
def load_pool(path: Path = typer.Argument(..., exists=True, dir_okay=False)) -> None:
    create_schema()
    with session_scope() as session:
        result = AssemblyManifestLoader(session).load_pool(path)
        typer.echo(json.dumps(result, indent=2))


if __name__ == "__main__":
    app()
