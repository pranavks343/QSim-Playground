from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pytest import MonkeyPatch
from typer.testing import CliRunner

import cli.main as cli_main
from core.agents.base import QUBOOutput
from core.agents.critic import CriticVerdict
from core.agents.refiner import RefinedQUBO
from core.circuit_gen import CircuitData
from core.evaluator import ComparisonTable, Scorecard
from core.orchestrator import PipelineEvent, PipelineState
from core.runner import ClassicalResult, SimulationResult
from core.templates import get_template

RUNNER = CliRunner()
FIXTURE_DIR = Path(__file__).parent / "fixtures"
PIPELINE_OUTPUT_DIR = FIXTURE_DIR / "pipeline_outputs"


def _scorecard(agent_name: str, score: float) -> Scorecard:
    return Scorecard(
        agent_name=agent_name,
        qubit_count=6,
        sparsity=0.25,
        condition_number=2.0,
        penalty_sensitivity=0.0,
        classical_baseline_objective=-1.0,
        classical_baseline_runtime_ms=1.0,
        composite_score=score,
        notes="well conditioned",
    )


def _qubo(agent_name: str) -> QUBOOutput:
    return QUBOOutput(
        agent_name=agent_name,
        strategy=f"{agent_name} test strategy",
        q_matrix=[[1.0, 0.0], [0.0, 2.0]],
        variable_order=["x_0", "x_1"],
        parameters_used={},
        justification=(
            f"{agent_name} produces a valid deterministic QUBO for CLI rendering tests."
        ),
    )


def _fake_pipeline_state() -> PipelineState:
    scorecards = {
        "penalty": _scorecard("penalty", 8.0),
        "slack": _scorecard("slack", 7.0),
        "graph": _scorecard("graph", 6.0),
    }
    qubos = {agent_name: _qubo(agent_name) for agent_name in scorecards}
    refined = RefinedQUBO(
        **qubos["penalty"].model_dump(),
        original_agent="penalty",
        improvements_made=["none - original was already near-optimal"],
        expected_improvement=(
            "No targeted improvement was applied because the scorecard already ranked this "
            "formulation above the available alternatives."
        ),
    )
    return {
        "ir": get_template("portfolio"),
        "template_metadata": None,
        "run_id": "test-run",
        "qubos": qubos,
        "scorecards": scorecards,
        "comparison_table": ComparisonTable(
            scorecards=list(scorecards.values()),
            top_agent="penalty",
            runner_up="slack",
        ),
        "critic_verdict": CriticVerdict(
            winner_agent="penalty",
            runner_up_agent="slack",
            rejected_agents=["graph"],
            rationale=(
                "penalty wins because composite_score=8.0 and condition_number=2.0 are "
                "stronger than slack, while graph is rejected on composite_score=6.0."
            ),
            confidence="high",
        ),
        "refined_qubo": refined,
        "circuit_data": CircuitData(
            qubit_count=2,
            depth=4,
            gate_count=8,
            reps=2,
            qiskit_qasm="OPENQASM 3.0;",
        ),
        "sim_result": SimulationResult(
            best_bitstring="10",
            best_objective=-1.0,
            quality_vs_classical=100.0,
            top_5_bitstrings=[("10", 512, -1.0)],
            total_shots=1024,
            runtime_ms=10.0,
        ),
        "classical_result": ClassicalResult(
            best_bitstring="10",
            best_objective=-1.0,
            runtime_ms=1.0,
            method="deterministic_test",
        ),
        "events": [
            PipelineEvent(
                event_type="pipeline_done",
                payload={"winner": "penalty"},
                timestamp=datetime.now(tz=UTC),
                run_id="test-run",
            )
        ],
        "errors": [],
        "pipeline_failed": False,
        "critic_retry_count": 0,
    }


def test_run_template_prints_expected_sections(monkeypatch: MonkeyPatch) -> None:
    async def fake_run_pipeline(*_args: object, **_kwargs: object) -> PipelineState:
        return _fake_pipeline_state()

    monkeypatch.setattr(cli_main, "_run_pipeline", fake_run_pipeline)

    result = RUNNER.invoke(cli_main.app, ["run", "--template", "portfolio"])

    assert result.exit_code == 0
    assert "QSim Pipeline" in result.stdout
    assert "Agent Formulations" in result.stdout
    assert "Comparison" in result.stdout
    assert "Critic Verdict" in result.stdout
    assert "Refiner Improvements" in result.stdout
    assert "Simulation Results" in result.stdout
    assert "Execution Comparison" in result.stdout
    assert "Total wall-clock" in result.stdout


def test_run_output_json_writes_pipeline_state(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    async def fake_run_pipeline(*_args: object, **_kwargs: object) -> PipelineState:
        return _fake_pipeline_state()

    monkeypatch.setattr(cli_main, "_run_pipeline", fake_run_pipeline)
    output_path = tmp_path / "pipeline.json"

    result = RUNNER.invoke(
        cli_main.app,
        ["run", "--template", "portfolio", "--output-json", str(output_path)],
    )

    assert result.exit_code == 0
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["run_id"] == "test-run"
    assert data["comparison_table"]["top_agent"] == "penalty"
    assert data["critic_verdict"]["winner_agent"] == "penalty"
    assert data["sim_result"]["best_bitstring"] == "10"


def test_run_output_shape_matches_regression_fixture(monkeypatch: MonkeyPatch) -> None:
    async def fake_run_pipeline(*_args: object, **_kwargs: object) -> PipelineState:
        return _fake_pipeline_state()

    monkeypatch.setattr(cli_main, "_run_pipeline", fake_run_pipeline)
    fixture_data = json.loads((PIPELINE_OUTPUT_DIR / "portfolio.json").read_text(encoding="utf-8"))

    with RUNNER.isolated_filesystem():
        result = RUNNER.invoke(
            cli_main.app,
            ["run", "--template", "portfolio", "--output-json", "pipeline.json"],
        )
        output_data = json.loads(Path("pipeline.json").read_text(encoding="utf-8"))

    assert result.exit_code == 0
    assert set(output_data) == set(fixture_data)
    assert set(output_data["comparison_table"]) == set(fixture_data["comparison_table"])
    assert set(output_data["sim_result"]) == set(fixture_data["sim_result"])
