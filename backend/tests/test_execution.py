from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

import pytest
from qiskit import QuantumCircuit

import api.execution as execution
from api.execution import execute_pipeline_background
from core.agents.base import AgentContext, QUBOAgent, QUBOOutput
from core.agents.critic import CriticVerdict
from core.agents.refiner import RefinedQUBO, no_improvement_refinement
from core.circuit_gen import CircuitData
from core.evaluator import ComparisonTable, Scorecard
from core.ir import ProblemIR
from core.orchestrator import AGENT_NAMES
from core.runner import ClassicalResult, SimulationResult
from core.templates import get_template


class StaticAgent(QUBOAgent):
    name = "static"
    strategy_description = "static test strategy"
    prompt_file = "base_qubo.md"

    def __init__(self, agent_name: str, fail: bool = False, delay_seconds: float = 0.0) -> None:
        self._agent_name = agent_name
        self._fail = fail
        self._delay_seconds = delay_seconds

    async def formulate(self, context: AgentContext) -> QUBOOutput:
        if self._delay_seconds:
            await asyncio.sleep(self._delay_seconds)
        if self._fail:
            raise RuntimeError(f"{self._agent_name} forced failure")
        size = len(context.ir.variables)
        offset = AGENT_NAMES.index(self._agent_name) + 1
        q_matrix = [[0.0 for _ in range(size)] for _ in range(size)]
        for index in range(size):
            q_matrix[index][index] = float(offset + index + 1)
        return QUBOOutput(
            agent_name=self._agent_name,
            strategy=f"{self._agent_name} static test strategy",
            q_matrix=q_matrix,
            variable_order=[variable.name for variable in context.ir.variables],
            parameters_used={"offset": offset},
            justification=(
                f"The {self._agent_name} static test strategy produces a deterministic "
                "symmetric QUBO for execution testing without external Gemini calls."
            ),
        )


class StaticCriticAgent:
    async def judge(self, comparison_table: ComparisonTable) -> CriticVerdict:
        top = comparison_table.scorecards[0]
        runner_up = comparison_table.scorecards[1]
        rejected = [scorecard.agent_name for scorecard in comparison_table.scorecards[2:]]
        confidence: Literal["high", "medium", "low"] = (
            "high"
            if top.composite_score - runner_up.composite_score >= 1.0
            else "low"
            if top.composite_score - runner_up.composite_score < 0.25
            else "medium"
        )
        return CriticVerdict(
            winner_agent=top.agent_name,
            runner_up_agent=runner_up.agent_name,
            rejected_agents=rejected,
            rationale=(
                f"{top.agent_name} wins with composite_score={top.composite_score} and "
                f"qubit_count={top.qubit_count}; {runner_up.agent_name} follows with "
                f"composite_score={runner_up.composite_score}."
            ),
            confidence=confidence,
        )


class StaticRefinerAgent:
    async def refine(
        self,
        winner_qubo: QUBOOutput,
        scorecard: Scorecard,
        *,
        with_hints: bool = False,
    ) -> RefinedQUBO:
        del scorecard, with_hints
        return no_improvement_refinement(winner_qubo)


def _fake_build_qaoa_circuit(
    qubo: QUBOOutput,
    reps: int = 2,
    max_qubits: int | None = None,
) -> tuple[CircuitData, QuantumCircuit]:
    del reps, max_qubits
    circuit = QuantumCircuit(len(qubo.variable_order))
    circuit.h(range(len(qubo.variable_order)))
    return (
        CircuitData(
            qubit_count=len(qubo.variable_order),
            depth=circuit.depth(),
            gate_count=sum(circuit.count_ops().values()),
            reps=2,
            qiskit_qasm="OPENQASM 3.0;",
        ),
        circuit,
    )


def _fake_simulate_circuit(
    circuit: QuantumCircuit,
    qubo: QUBOOutput,
    ir: object,
    shots: int = 1024,
) -> SimulationResult:
    del circuit, ir
    bitstring = "0" * len(qubo.variable_order)
    return SimulationResult(
        best_bitstring=bitstring,
        best_objective=0.0,
        quality_vs_classical=100.0,
        top_5_bitstrings=[(bitstring, shots, 0.0)],
        total_shots=shots,
        runtime_ms=1.0,
    )


def _fake_classical_baseline(qubo: QUBOOutput, ir: object) -> ClassicalResult:
    del ir
    return ClassicalResult(
        best_bitstring="0" * len(qubo.variable_order),
        best_objective=0.0,
        runtime_ms=1.0,
        method="test",
    )


class FakeQuery:
    def __init__(self, db: FakeSupabaseClient, table_name: str) -> None:
        self._db = db
        self._table_name = table_name
        self._operation = "select"
        self._columns = "*"
        self._payload: dict[str, Any] = {}
        self._filters: list[tuple[str, str, Any]] = []
        self._single = False

    def select(self, columns: str) -> FakeQuery:
        self._operation = "select"
        self._columns = columns
        return self

    def insert(self, payload: dict[str, Any]) -> FakeQuery:
        self._operation = "insert"
        self._payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        self._operation = "update"
        self._payload = payload
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self._filters.append(("eq", column, value))
        return self

    def single(self) -> FakeQuery:
        self._single = True
        return self

    def execute(self) -> Any:
        if self._operation == "insert":
            return _Result([self._db.insert(self._table_name, self._payload)])
        if self._operation == "update":
            return _Result(self._db.update(self._table_name, self._payload, self._filters))
        rows = self._db.select(self._table_name, self._filters)
        if self._single:
            return _Result(rows[0] if rows else {})
        return _Result(rows)


class _Result:
    def __init__(self, data: Any) -> None:
        self.data = data


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {"runs": [], "run_events": []}
        self._event_id = 1
        self._lock = asyncio.Lock()

    def table(self, table_name: str) -> FakeQuery:
        return FakeQuery(self, table_name)

    def insert(self, table_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        row = payload.copy()
        if table_name == "run_events":
            row.setdefault("id", self._event_id)
            self._event_id += 1
            row.setdefault("created_at", datetime.now(tz=UTC).isoformat())
        self.tables.setdefault(table_name, []).append(row)
        return row

    def select(self, table_name: str, filters: list[tuple[str, str, Any]]) -> list[dict[str, Any]]:
        rows = [row.copy() for row in self.tables.get(table_name, [])]
        for op, column, value in filters:
            if op == "eq":
                rows = [row for row in rows if str(row.get(column)) == str(value)]
        return rows

    def update(
        self,
        table_name: str,
        payload: dict[str, Any],
        filters: list[tuple[str, str, Any]],
    ) -> list[dict[str, Any]]:
        rows = self.select(table_name, filters)
        ids = {row.get("id") for row in rows}
        for row in self.tables.get(table_name, []):
            if row.get("id") in ids:
                row.update(payload)
        return [row | payload for row in rows]


@pytest.fixture()
def fake_db() -> FakeSupabaseClient:
    return FakeSupabaseClient()


@pytest.fixture()
def seeded_run(fake_db: FakeSupabaseClient) -> dict[str, Any]:
    run = {
        "id": str(uuid4()),
        "user_id": str(uuid4()),
        "status": "queued",
        "cancel_requested": False,
        "created_at": datetime.now(tz=UTC).isoformat(),
    }
    fake_db.tables["runs"].append(run)
    return run


def _agent_factories(
    failing_agents: set[str] | None = None,
    delays: dict[str, float] | None = None,
) -> dict[str, Callable[[], QUBOAgent]]:
    failures = failing_agents or set()
    delay_by_name = delays or {}
    factories: dict[str, Callable[[], QUBOAgent]] = {}
    for agent_name in AGENT_NAMES:

        def build(name: str = agent_name) -> QUBOAgent:
            return StaticAgent(
                name,
                fail=name in failures,
                delay_seconds=delay_by_name.get(name, 0.0),
            )

        factories[agent_name] = build
    return factories


def _patch_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    fake_db: FakeSupabaseClient,
    failing_agents: set[str] | None = None,
    delays: dict[str, float] | None = None,
) -> None:
    monkeypatch.setattr(execution, "get_service_client", lambda: fake_db)
    monkeypatch.setattr(
        "core.orchestrator._default_agent_factories",
        lambda: _agent_factories(failing_agents=failing_agents, delays=delays),
    )
    monkeypatch.setattr(
        "core.orchestrator._default_critic_factory",
        lambda: lambda: StaticCriticAgent(),
    )
    monkeypatch.setattr(
        "core.orchestrator._default_refiner_factory",
        lambda: lambda: StaticRefinerAgent(),
    )
    monkeypatch.setattr("core.orchestrator.build_qaoa_circuit", _fake_build_qaoa_circuit)
    monkeypatch.setattr("core.orchestrator.simulate_circuit", _fake_simulate_circuit)
    monkeypatch.setattr("core.orchestrator.run_classical_baseline", _fake_classical_baseline)


def _template_ir() -> ProblemIR:
    return get_template("portfolio")


def _run_row(fake_db: FakeSupabaseClient, run_id: str) -> dict[str, Any]:
    rows = [row for row in fake_db.tables["runs"] if row["id"] == run_id]
    assert rows, "run row missing"
    return rows[0]


def _events(fake_db: FakeSupabaseClient, run_id: str) -> list[dict[str, Any]]:
    return [event for event in fake_db.tables["run_events"] if event["run_id"] == run_id]


@pytest.mark.asyncio
async def test_successful_run_marks_done_and_emits_events(
    monkeypatch: pytest.MonkeyPatch,
    fake_db: FakeSupabaseClient,
    seeded_run: dict[str, Any],
) -> None:
    _patch_pipeline(monkeypatch, fake_db)

    await asyncio.wait_for(
        execute_pipeline_background(
            UUID(seeded_run["id"]),
            UUID(seeded_run["user_id"]),
            _template_ir(),
        ),
        timeout=30.0,
    )

    row = _run_row(fake_db, seeded_run["id"])
    assert row["status"] == "done"
    assert row["winner_agent"] in AGENT_NAMES
    assert row["completed_at"] is not None
    assert isinstance(row["total_runtime_ms"], int)
    assert row["qubos"] and row["scorecards"]

    events = _events(fake_db, seeded_run["id"])
    assert any(event["event_type"] == "agent_started" for event in events)
    assert events[-1]["event_type"] == "pipeline_done"


@pytest.mark.asyncio
async def test_partial_agent_failure_still_completes(
    monkeypatch: pytest.MonkeyPatch,
    fake_db: FakeSupabaseClient,
    seeded_run: dict[str, Any],
) -> None:
    _patch_pipeline(monkeypatch, fake_db, failing_agents={"penalty", "slack"})

    await execute_pipeline_background(
        UUID(seeded_run["id"]),
        UUID(seeded_run["user_id"]),
        _template_ir(),
    )

    row = _run_row(fake_db, seeded_run["id"])
    assert row["status"] == "done"
    failed_events = [
        event
        for event in _events(fake_db, seeded_run["id"])
        if event["event_type"] == "agent_failed"
    ]
    assert len(failed_events) == 2


@pytest.mark.asyncio
async def test_all_agents_failing_marks_failed(
    monkeypatch: pytest.MonkeyPatch,
    fake_db: FakeSupabaseClient,
    seeded_run: dict[str, Any],
) -> None:
    _patch_pipeline(
        monkeypatch,
        fake_db,
        failing_agents={"penalty", "slack", "graph", "decomp", "domain"},
    )

    await execute_pipeline_background(
        UUID(seeded_run["id"]),
        UUID(seeded_run["user_id"]),
        _template_ir(),
    )

    row = _run_row(fake_db, seeded_run["id"])
    assert row["status"] == "failed"
    assert row["error"]
    events = _events(fake_db, seeded_run["id"])
    assert events[-1]["event_type"] == "pipeline_failed"


@pytest.mark.asyncio
async def test_cancellation_flag_stops_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    fake_db: FakeSupabaseClient,
    seeded_run: dict[str, Any],
) -> None:
    _patch_pipeline(monkeypatch, fake_db)
    fake_db.tables["runs"][0]["cancel_requested"] = True

    await execute_pipeline_background(
        UUID(seeded_run["id"]),
        UUID(seeded_run["user_id"]),
        _template_ir(),
    )

    row = _run_row(fake_db, seeded_run["id"])
    assert row["status"] == "cancelled"
    assert row["completed_at"] is not None


@pytest.mark.asyncio
async def test_timeout_marks_run_timeout(
    monkeypatch: pytest.MonkeyPatch,
    fake_db: FakeSupabaseClient,
    seeded_run: dict[str, Any],
) -> None:
    _patch_pipeline(monkeypatch, fake_db, delays={"penalty": 5.0})
    monkeypatch.setattr(execution, "PIPELINE_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr("core.orchestrator.PIPELINE_TIMEOUT_SECONDS", 0.05)

    await execute_pipeline_background(
        UUID(seeded_run["id"]),
        UUID(seeded_run["user_id"]),
        _template_ir(),
    )

    row = _run_row(fake_db, seeded_run["id"])
    assert row["status"] == "timeout"
    assert "cap" in (row.get("error") or "") or row.get("error")
    events = _events(fake_db, seeded_run["id"])
    assert events[-1]["event_type"] == "pipeline_failed"


@pytest.mark.asyncio
async def test_events_appear_in_run_events_within_30_seconds(
    monkeypatch: pytest.MonkeyPatch,
    fake_db: FakeSupabaseClient,
    seeded_run: dict[str, Any],
) -> None:
    _patch_pipeline(monkeypatch, fake_db)
    task = asyncio.create_task(
        execute_pipeline_background(
            UUID(seeded_run["id"]),
            UUID(seeded_run["user_id"]),
            _template_ir(),
        )
    )
    deadline = asyncio.get_event_loop().time() + 30.0
    while asyncio.get_event_loop().time() < deadline:
        if _events(fake_db, seeded_run["id"]):
            break
        await asyncio.sleep(0.05)
    await task
    assert _events(fake_db, seeded_run["id"])
