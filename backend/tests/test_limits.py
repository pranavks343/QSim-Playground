from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from qiskit import QuantumCircuit

from api.deps import AuthenticatedUser
from api.limits import (
    TIER_LIMITS,
    check_qubit_cap,
    check_quota,
    check_rate_limit,
)
from core.agents.base import AgentContext, QUBOAgent, QUBOOutput
from core.agents.critic import CriticVerdict
from core.agents.refiner import RefinedQUBO, no_improvement_refinement
from core.circuit_gen import CircuitData
from core.evaluator import ComparisonTable, Scorecard, evaluate_qubo
from core.ir import (
    Constraint,
    ConstraintType,
    Objective,
    ObjectiveSense,
    ProblemIR,
    Variable,
    VariableType,
)
from core.limits import QubitCapExceeded
from core.orchestrator import AGENT_NAMES, run_pipeline
from core.runner import ClassicalResult, SimulationResult
from infra.gemini import (
    GeminiCircuitOpen,
    GeminiClient,
    GeminiQuotaExhausted,
    GeminiResponse,
    is_gemini_circuit_open,
    reset_gemini_circuit_breaker,
)


@dataclass(frozen=True)
class FakeHTTPError(Exception):
    status_code: int

    def __str__(self) -> str:
        return f"HTTP {self.status_code}"


class FakeTransport:
    def __init__(self, responses: list[GeminiResponse | Exception]) -> None:
        self._responses = responses

    async def generate(
        self,
        *,
        api_key: str,
        model: str,
        prompt: str,
        temperature: float,
        response_mime_type: str | None,
        timeout: float,
    ) -> GeminiResponse:
        del api_key, model, prompt, temperature, response_mime_type, timeout
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


async def _no_sleep(delay: float) -> None:
    del delay


def _expect_detail(detail: object) -> dict[str, Any]:
    assert isinstance(detail, dict)
    return detail


class StaticAgent(QUBOAgent):
    name = "static"
    strategy_description = "static test strategy"
    prompt_file = "base_qubo.md"

    def __init__(self, agent_name: str) -> None:
        self._agent_name = agent_name

    async def formulate(self, context: AgentContext) -> QUBOOutput:
        size = len(context.ir.variables)
        offset = AGENT_NAMES.index(self._agent_name) + 1
        matrix = [[0.0 for _ in range(size)] for _ in range(size)]
        for index in range(size):
            matrix[index][index] = float(offset + index + 1)
        return QUBOOutput(
            agent_name=self._agent_name,
            strategy=f"{self._agent_name} static test strategy",
            q_matrix=matrix,
            variable_order=[variable.name for variable in context.ir.variables],
            parameters_used={"offset": offset},
            justification=(
                f"The {self._agent_name} static test strategy produces a deterministic "
                "symmetric QUBO for limits testing without external Gemini calls."
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


def _user(tier: str = "free", monthly_runs_used: int = 0) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=uuid4(),
        email="user@example.com",
        tier=tier,
        monthly_runs_used=monthly_runs_used,
        quota_remaining=max(0, TIER_LIMITS[tier]["monthly_runs"] or 0) - monthly_runs_used
        if TIER_LIMITS[tier]["monthly_runs"] is not None
        else 0,
    )


class _RateLimitDB:
    """Minimal fake supabase client for rate_limit_log."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def table(self, table_name: str) -> _RateLimitDB._Query:
        assert table_name == "rate_limit_log"
        return _RateLimitDB._Query(self)

    class _Query:
        def __init__(self, db: _RateLimitDB) -> None:
            self._db = db
            self._op = "select"
            self._payload: dict[str, Any] = {}
            self._filters: list[tuple[str, Any]] = []

        def insert(self, payload: dict[str, Any]) -> _RateLimitDB._Query:
            self._op = "insert"
            self._payload = payload
            return self

        def select(self, _columns: str) -> _RateLimitDB._Query:
            self._op = "select"
            return self

        def eq(self, column: str, value: Any) -> _RateLimitDB._Query:
            self._filters.append((column, value))
            return self

        def execute(self) -> Any:
            if self._op == "insert":
                self._db.rows.append(self._payload)
                return _Result([self._payload])
            rows = list(self._db.rows)
            for col, val in self._filters:
                rows = [row for row in rows if str(row.get(col)) == str(val)]
            return _Result(rows)


class _Result:
    def __init__(self, data: Any) -> None:
        self.data = data


@pytest.fixture(autouse=True)
def _reset_breaker() -> None:
    reset_gemini_circuit_breaker()


@pytest.mark.asyncio
async def test_check_quota_below_limit_allows() -> None:
    user = _user(tier="free", monthly_runs_used=49)
    await check_quota(user)


@pytest.mark.asyncio
async def test_check_quota_at_limit_raises_429_with_retry_after() -> None:
    user = _user(tier="free", monthly_runs_used=50)
    with pytest.raises(HTTPException) as excinfo:
        await check_quota(user)
    assert excinfo.value.status_code == 429
    detail = _expect_detail(excinfo.value.detail)
    assert detail["error"] == "quota_exceeded"
    assert detail["limit"] == 50
    headers = excinfo.value.headers
    assert headers is not None
    assert int(headers["Retry-After"]) >= 1


@pytest.mark.asyncio
async def test_check_quota_enterprise_is_unlimited() -> None:
    user = _user(tier="enterprise", monthly_runs_used=10_000)
    await check_quota(user)


@pytest.mark.asyncio
async def test_check_rate_limit_first_five_succeed_sixth_429() -> None:
    user = _user(tier="free")
    db = _RateLimitDB()
    now = datetime.now(tz=UTC)

    for _ in range(5):
        await check_rate_limit(user, client=db, now=now)

    with pytest.raises(HTTPException) as excinfo:
        await check_rate_limit(user, client=db, now=now)
    assert excinfo.value.status_code == 429
    headers = excinfo.value.headers
    assert headers is not None
    assert headers["Retry-After"] == "60"
    detail = _expect_detail(excinfo.value.detail)
    assert detail["error"] == "rate_limit_exceeded"
    assert detail["limit"] == 5


@pytest.mark.asyncio
async def test_check_rate_limit_succeeds_after_window_elapses() -> None:
    user = _user(tier="free")
    db = _RateLimitDB()
    old = datetime.now(tz=UTC) - timedelta(seconds=120)

    for _ in range(5):
        await check_rate_limit(user, client=db, now=old)

    fresh = datetime.now(tz=UTC)
    await check_rate_limit(user, client=db, now=fresh)


def test_check_qubit_cap_within_limit() -> None:
    check_qubit_cap(20, _user(tier="free"))


def test_check_qubit_cap_over_limit_raises() -> None:
    with pytest.raises(QubitCapExceeded) as excinfo:
        check_qubit_cap(21, _user(tier="free"))
    assert excinfo.value.qubit_count == 21
    assert excinfo.value.limit == 20


def test_evaluator_qubit_cap_trips_on_oversized_qubo() -> None:
    qubo = _make_qubo(size=25)
    ir = _make_ir(size=25)
    with pytest.raises(QubitCapExceeded):
        evaluate_qubo(qubo, ir, None, max_qubits=20)


@pytest.mark.asyncio
async def test_pipeline_marks_failed_when_qubit_cap_exceeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_pipeline(monkeypatch, size=25)
    ir = _make_ir(size=25)

    state = await run_pipeline(ir, run_id="run-cap", max_qubits=20)

    assert state.get("pipeline_failed") is True
    events = state["events"]
    assert events[-1].event_type == "pipeline_failed"
    assert events[-1].payload["reason"] == "qubit_cap_exceeded"
    assert events[-1].payload["limit"] == 20
    assert events[-1].payload["qubit_count"] == 25
    assert state["errors"][-1].error_type == "QubitCapExceeded"


@pytest.mark.asyncio
async def test_gemini_circuit_breaker_opens_after_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del monkeypatch
    responses: list[GeminiResponse | Exception] = [
        FakeHTTPError(status_code=429) for _ in range(11)
    ]
    transport = FakeTransport(responses)
    keys = [f"key-{index}" for index in range(11)]
    client = GeminiClient(
        api_keys=keys,
        transport=transport,
        sleep=_no_sleep,
    )

    with pytest.raises((GeminiCircuitOpen, GeminiQuotaExhausted)):
        await client.generate_text("trigger 429s")

    open_, remaining = is_gemini_circuit_open()
    assert open_ is True
    assert remaining > 0

    with pytest.raises(GeminiCircuitOpen):
        await client.generate_text("should fast-fail")


def _make_qubo(size: int, agent_name: str = "penalty") -> QUBOOutput:
    matrix = [[0.0 for _ in range(size)] for _ in range(size)]
    for index in range(size):
        matrix[index][index] = 1.0
    return QUBOOutput(
        agent_name=agent_name,
        strategy="test strategy generated for qubit-cap exercises",
        q_matrix=matrix,
        variable_order=[f"x_{index}" for index in range(size)],
        parameters_used={},
        justification=(
            "Diagonal identity QUBO of configurable size used to verify the qubit cap path. "
            "Each diagonal entry is a unit linear penalty, which is sufficient to exercise "
            "the evaluator and the orchestrator failure routing."
        ),
    )


def _make_ir(size: int) -> ProblemIR:
    variables = [Variable(name=f"x_{i}", type=VariableType.BINARY) for i in range(size)]
    linear_terms = {variable.name: 1.0 for variable in variables}
    constraint = Constraint(
        name="pick_half",
        type=ConstraintType.LEQ,
        linear_terms=linear_terms,
        rhs=float(size // 2),
    )
    return ProblemIR(
        name=f"cap_test_{size}",
        description="synthetic large-variable IR for qubit cap testing",
        variables=variables,
        objective=Objective(sense=ObjectiveSense.MINIMIZE, linear_terms=linear_terms),
        constraints=[constraint],
    )


def _patch_pipeline(monkeypatch: pytest.MonkeyPatch, size: int) -> None:
    def factory_for(name: str) -> Callable[[], QUBOAgent]:
        def build() -> QUBOAgent:
            return _FixedSizeStaticAgent(name, size)

        return build

    monkeypatch.setattr(
        "core.orchestrator._default_agent_factories",
        lambda: {name: factory_for(name) for name in AGENT_NAMES},
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


class _FixedSizeStaticAgent(StaticAgent):
    """Static agent that always produces a QUBO of a configured size."""

    def __init__(self, agent_name: str, size: int) -> None:
        super().__init__(agent_name)
        self._size = size

    async def formulate(self, context: AgentContext) -> QUBOOutput:
        del context
        return _make_qubo(self._size, self._agent_name)
