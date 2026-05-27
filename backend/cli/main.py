"""Command-line interface for QSim Playground."""

from __future__ import annotations

import asyncio
import json
import os
import warnings
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, Annotated
from uuid import uuid4

import typer
from langchain_core._api.deprecation import LangChainPendingDeprecationWarning
from pydantic import BaseModel, ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from core.ir import ProblemIR
from core.parser import ParseFailure, ParserError, ParseSuccess, parse
from core.templates import get_template, list_templates

warnings.filterwarnings(
    "ignore",
    category=LangChainPendingDeprecationWarning,
)

if TYPE_CHECKING:
    from core.orchestrator import (
        AgentFactory,
        CriticFactory,
        PipelineEvent,
        PipelineState,
        RefinerFactory,
    )

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


def _load_problem_from_options(template: str | None, file: Path | None) -> ProblemIR:
    if (template is None and file is None) or (template is not None and file is not None):
        error_console.print("[bold red]choose exactly one input:[/bold red] --template or --file")
        raise typer.Exit(1)

    if template is not None:
        try:
            return get_template(template)
        except KeyError as exc:
            error_console.print(f"[bold red]template not found:[/bold red] {template}")
            error_console.print(str(exc))
            raise typer.Exit(1) from exc

    if file is None:
        error_console.print("[bold red]missing input file[/bold red]")
        raise typer.Exit(1)

    result = parse(file.read_text(encoding="utf-8"))
    if isinstance(result, ParseFailure):
        _print_parser_errors(result.errors)
        raise typer.Exit(1)
    if not isinstance(result, ParseSuccess):
        error_console.print("[bold red]unexpected parser result[/bold red]")
        raise typer.Exit(1)
    return result.ir


async def _verbose_event_printer(event: PipelineEvent) -> None:
    error_console.print(
        f"[dim]{event.timestamp.isoformat()}[/dim] "
        f"[cyan]{event.event_type}[/cyan] {event.payload}"
    )


def _pipeline_factories() -> (
    tuple[
        dict[str, AgentFactory] | None,
        CriticFactory | None,
        RefinerFactory | None,
    ]
):
    if os.environ.get("QSIM_RUN_MODE") == "gemini":
        return None, None, None
    from core.local_pipeline import (
        local_agent_factories,
        local_critic_factory,
        local_refiner_factory,
    )

    return local_agent_factories(), local_critic_factory(), local_refiner_factory()


def _jsonable(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, ProblemIR):
        return value.to_dict()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items() if key != "qaoa_circuit"}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    return value


def _pipeline_state_to_dict(state: PipelineState, wall_clock_ms: float) -> dict[str, object]:
    return {
        "ir": state["ir"].to_dict(),
        "run_id": state["run_id"],
        "template_metadata": _jsonable(state.get("template_metadata")),
        "qubos": _jsonable(state.get("qubos", {})),
        "scorecards": _jsonable(state.get("scorecards", {})),
        "comparison_table": _jsonable(state.get("comparison_table")),
        "critic_verdict": _jsonable(state.get("critic_verdict")),
        "refined_qubo": _jsonable(state.get("refined_qubo")),
        "circuit_data": _jsonable(state.get("circuit_data")),
        "sim_result": _jsonable(state.get("sim_result")),
        "classical_result": _jsonable(state.get("classical_result")),
        "events": _jsonable(state.get("events", [])),
        "errors": _jsonable(state.get("errors", [])),
        "pipeline_failed": state.get("pipeline_failed", False),
        "wall_clock_ms": round(wall_clock_ms, 3),
    }


async def _run_pipeline(
    problem: ProblemIR,
    run_id: str,
    verbose: bool,
    agent_factories: dict[str, AgentFactory] | None,
    critic_factory: CriticFactory | None,
    refiner_factory: RefinerFactory | None,
) -> PipelineState:
    from core.orchestrator import run_pipeline

    return await run_pipeline(
        problem,
        run_id=run_id,
        event_callback=_verbose_event_printer if verbose else None,
        agent_factories=agent_factories,
        critic_factory=critic_factory,
        refiner_factory=refiner_factory,
    )


def _score_style(score: float) -> str:
    if score >= 7.5:
        return "green"
    if score >= 5.0:
        return "yellow"
    return "red"


def _print_run_summary(state: PipelineState, wall_clock_ms: float) -> None:
    problem = state["ir"]
    console.print(
        Panel.fit(
            (
                f"[bold]{problem.name}[/bold]\n"
                f"Variables: {len(problem.variables)} | Constraints: {len(problem.constraints)} | "
                f"Run: {state['run_id']}"
            ),
            title="QSim Pipeline",
            border_style="cyan",
        )
    )

    console.print("[bold]Agent Formulations[/bold]")
    for agent_name, qubo in state.get("qubos", {}).items():
        justification = qubo.justification
        if len(justification) > 220:
            justification = f"{justification[:217]}..."
        console.print(
            Panel(
                f"[bold]{qubo.strategy}[/bold]\n"
                f"Qubits: {qubo.estimated_qubits}\n"
                f"[dim]{justification}[/dim]",
                title=agent_name,
                border_style="blue",
            )
        )

    table = Table(title="Comparison")
    table.add_column("Rank", justify="right")
    table.add_column("Agent")
    table.add_column("Score", justify="right")
    table.add_column("Qubits", justify="right")
    table.add_column("Sparsity", justify="right")
    table.add_column("Condition", justify="right")
    table.add_column("Sensitivity", justify="right")
    for index, scorecard in enumerate(state["comparison_table"].scorecards, start=1):
        style = _score_style(scorecard.composite_score)
        table.add_row(
            str(index),
            scorecard.agent_name,
            f"[{style}]{scorecard.composite_score:.3f}[/{style}]",
            str(scorecard.qubit_count),
            f"{scorecard.sparsity:.3f}",
            f"{scorecard.condition_number:.3g}",
            f"{scorecard.penalty_sensitivity:.3f}",
        )
    console.print(table)

    verdict = state["critic_verdict"]
    console.print(
        Panel(
            f"[italic]{verdict.rationale}[/italic]\n\n"
            f"Winner: [bold green]{verdict.winner_agent}[/bold green] | "
            f"Runner-up: {verdict.runner_up_agent} | Confidence: {verdict.confidence}",
            title="Critic Verdict",
            border_style="magenta",
        )
    )

    refined = state["refined_qubo"]
    console.print("[bold]Refiner Improvements[/bold]")
    for improvement in refined.improvements_made:
        console.print(f"  - {improvement}")

    sim = state["sim_result"]
    console.print(
        Panel(
            f"Best bitstring: [bold]{sim.best_bitstring}[/bold]\n"
            f"Objective: {sim.best_objective:.6g}\n"
            f"Quality vs classical: {sim.quality_vs_classical:.2f}%\n"
            f"Shots: {sim.total_shots}",
            title="Simulation Results",
            border_style="green",
        )
    )

    comparison = Table(title="Execution Comparison")
    comparison.add_column("Backend")
    comparison.add_column("Best Objective", justify="right")
    comparison.add_column("Runtime", justify="right")
    comparison.add_column("Status")
    classical = state["classical_result"]
    comparison.add_row(
        "Classical",
        f"{classical.best_objective:.6g}",
        f"{classical.runtime_ms:.2f} ms",
        classical.method,
    )
    comparison.add_row(
        "Simulator",
        f"{sim.best_objective:.6g}",
        f"{sim.runtime_ms:.2f} ms",
        "Aer QAOA",
    )
    comparison.add_row("Hardware", "—", "—", "[dim]Day 6+[/dim]")
    console.print(comparison)
    console.print(f"[bold]Total wall-clock:[/bold] {wall_clock_ms / 1000.0:.2f}s")


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


@app.command("run")
def run_command(
    template: Annotated[
        str | None,
        typer.Option("--template", "-t", help="Template name to run."),
    ] = None,
    file: Annotated[
        Path | None,
        typer.Option("--file", "-f", exists=True, dir_okay=False, readable=True),
    ] = None,
    output_json: Annotated[
        Path | None,
        typer.Option("--output-json", help="Write full pipeline state JSON to this path."),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Stream pipeline events to stderr."),
    ] = False,
) -> None:
    """Run the full QUBO pipeline for a template or parsed NumPy file."""

    problem = _load_problem_from_options(template, file)
    run_id = f"cli-{uuid4().hex[:12]}"
    started = perf_counter()
    agent_factories, critic_factory, refiner_factory = _pipeline_factories()

    try:
        state = asyncio.run(
            _run_pipeline(
                problem,
                run_id,
                verbose,
                agent_factories,
                critic_factory,
                refiner_factory,
            )
        )
    except Exception as exc:
        error_console.print(f"[bold red]pipeline failed:[/bold red] {exc}")
        raise typer.Exit(1) from exc

    wall_clock_ms = (perf_counter() - started) * 1000.0
    if state.get("pipeline_failed", False):
        error_console.print("[bold red]pipeline failed[/bold red]")
        for error in state.get("errors", []):
            error_console.print(f"- {error.node}: {error.message}")
        raise typer.Exit(1)

    _print_run_summary(state, wall_clock_ms)
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(
            json.dumps(_pipeline_state_to_dict(state, wall_clock_ms), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        console.print(f"[green]Wrote pipeline JSON:[/green] {output_json}")


if __name__ == "__main__":
    app()
