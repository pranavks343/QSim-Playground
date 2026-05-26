"""Command-line interface for QSim Playground."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from core.ir import ProblemIR
from core.parser import ParseFailure, ParserError, ParseSuccess, parse
from core.templates import get_template, list_templates

app = typer.Typer(help="QSim Playground command-line tools.", no_args_is_help=True)
console = Console(width=140)
error_console = Console(stderr=True, width=140)


def _pretty_json(data: dict[str, object]) -> None:
    json_text = json.dumps(data, indent=2, sort_keys=True)
    console.print(json_text, markup=False, highlight=True, soft_wrap=True)


def _print_parser_errors(errors: list[ParserError]) -> None:
    error_console.print("[bold red]parse failed[/bold red]")
    for error in errors:
        location = "unknown location"
        if error.line is not None and error.column is not None:
            location = f"line {error.line}, column {error.column}"
        error_console.print(f"[red]- {error.message}[/red] ({location})")
        if error.ast_node:
            error_console.print(f"  [dim]AST: {error.ast_node}[/dim]")
    if errors:
        error_console.print("[bold]Supported patterns:[/bold]")
        for pattern in errors[0].supported_patterns:
            error_console.print(f"  - {pattern}")


@app.command("load")
def load_template(
    template: Annotated[str, typer.Option("--template", "-t", help="Template name to load.")],
) -> None:
    """Load a hardcoded template and print normalized IR JSON."""

    try:
        problem = get_template(template)
    except KeyError as exc:
        error_console.print(f"[bold red]template not found:[/bold red] {template}")
        error_console.print(str(exc))
        raise typer.Exit(1) from exc

    _pretty_json(problem.to_dict())


@app.command("parse")
def parse_file(
    file: Annotated[Path, typer.Option("--file", "-f", exists=True, dir_okay=False, readable=True)],
) -> None:
    """Parse a NumPy optimization snippet and print normalized IR JSON."""

    source = file.read_text(encoding="utf-8")
    result = parse(source)
    if isinstance(result, ParseFailure):
        _print_parser_errors(result.errors)
        raise typer.Exit(1)

    if not isinstance(result, ParseSuccess):
        error_console.print("[bold red]unexpected parser result[/bold red]")
        raise typer.Exit(1)

    _pretty_json(result.ir.to_dict())


@app.command("list-templates")
def list_template_metadata() -> None:
    """List available hardcoded templates."""

    table = Table(title="QSim Templates")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Display Name", no_wrap=True)
    table.add_column("Difficulty", no_wrap=True)
    table.add_column("Variables", justify="right", no_wrap=True)
    table.add_column("Constraints", justify="right", no_wrap=True)
    table.add_column("Expected Optimal", justify="right", no_wrap=True)
    table.add_column("Tags", no_wrap=True)

    for metadata in list_templates():
        expected = (
            "unknown"
            if metadata.expected_optimal_value is None
            else f"{metadata.expected_optimal_value:g}"
        )
        table.add_row(
            metadata.name,
            metadata.display_name,
            metadata.difficulty,
            str(metadata.variable_count),
            str(metadata.constraint_count),
            expected,
            ", ".join(metadata.domain_tags),
        )

    console.print(table)


@app.command("validate")
def validate_ir(
    file: Annotated[Path, typer.Option("--file", "-f", exists=True, dir_okay=False, readable=True)],
) -> None:
    """Validate a JSON file as ProblemIR."""

    try:
        raw = json.loads(file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        error_console.print(f"[bold red]invalid json:[/bold red] {exc}")
        raise typer.Exit(1) from exc

    if not isinstance(raw, dict):
        error_console.print("[bold red]invalid IR:[/bold red] top-level JSON must be an object")
        raise typer.Exit(1)

    try:
        ProblemIR.from_dict(raw)
    except ValidationError as exc:
        error_console.print("[bold red]invalid[/bold red]")
        error_console.print(exc)
        raise typer.Exit(1) from exc

    console.print("[bold green]valid[/bold green]")


if __name__ == "__main__":
    app()
