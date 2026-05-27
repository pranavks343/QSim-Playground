"""Two-user concurrency and isolation verification against real Supabase.

Skipped automatically when Supabase credentials are not configured. The QUBO
pipeline is monkey-patched to a deterministic static stub so the test exercises
the API, BackgroundTasks, and RLS without burning Gemini quota.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from typing import Any, Literal
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from pydantic import ValidationError
from qiskit import QuantumCircuit

from api.main import create_app
from core.agents.base import AgentContext, QUBOAgent, QUBOOutput
from core.agents.critic import CriticVerdict
from core.agents.refiner import RefinedQUBO, no_improvement_refinement
from core.circuit_gen import CircuitData
from core.evaluator import ComparisonTable, Scorecard
from core.orchestrator import AGENT_NAMES
from core.runner import ClassicalResult, SimulationResult
from infra.settings import Settings
from infra.supabase import get_anon_client, get_service_client

TestUser = dict[str, str]

PIPELINE_POLL_TIMEOUT = 90.0
PIPELINE_POLL_INTERVAL = 0.5


def _real_supabase_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        pytest.skip(f"Supabase credentials are not configured: {exc}")


class _StaticAgent(QUBOAgent):
    name = "static-concurrent"
    strategy_description = "static concurrent test strategy"
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
            strategy=f"{self._agent_name} concurrent stub",
            q_matrix=matrix,
            variable_order=[variable.name for variable in context.ir.variables],
            parameters_used={"offset": offset},
            justification=(
                f"The {self._agent_name} static stub returns a deterministic diagonal QUBO "
                "for the concurrent-user isolation smoke test without external API calls."
            ),
        )


class _StaticCritic:
    async def judge(self, comparison_table: ComparisonTable) -> CriticVerdict:
        top = comparison_table.scorecards[0]
        runner_up = comparison_table.scorecards[1]
        rejected = [scorecard.agent_name for scorecard in comparison_table.scorecards[2:]]
        confidence: Literal["high", "medium", "low"] = "high"
        return CriticVerdict(
            winner_agent=top.agent_name,
            runner_up_agent=runner_up.agent_name,
            rejected_agents=rejected,
            rationale=(
                f"{top.agent_name} wins the static concurrent stub with composite_score="
                f"{top.composite_score} and qubit_count={top.qubit_count}; "
                f"{runner_up.agent_name} follows."
            ),
            confidence=confidence,
        )


class _StaticRefiner:
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
        method="concurrent-stub",
    )


@pytest.fixture()
def concurrent_users() -> Iterator[dict[str, TestUser]]:
    _real_supabase_settings()
    service = get_service_client()
    anon = get_anon_client()
    marker = uuid4().hex
    user_secret = f"QsimConcurrent-{uuid4().hex}-99"
    emails = {
        "a": f"qsim-concur-a-{marker}@example.com",
        "b": f"qsim-concur-b-{marker}@example.com",
    }
    created_user_ids: list[str] = []
    try:
        users: dict[str, TestUser] = {}
        for label, email in emails.items():
            response = service.auth.admin.create_user(
                {
                    "email": email,
                    "password": user_secret,
                    "email_confirm": True,
                    "user_metadata": {"display_name": f"Concurrent User {label.upper()}"},
                }
            )
            user_id = str(response.user.id)
            created_user_ids.append(user_id)
            session_response = anon.auth.sign_in_with_password(
                {"email": email, "password": user_secret}
            )
            if session_response.session is None:
                raise RuntimeError("Supabase did not return a session for test user")
            users[label] = {
                "id": user_id,
                "email": email,
                "access_token": session_response.session.access_token,
            }
        yield users
    finally:
        for user_id in created_user_ids:
            with _suppress_admin_error():
                service.auth.admin.delete_user(user_id)


@pytest.fixture(autouse=True)
def _patch_pipeline_for_concurrency(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the real Gemini-backed agents with deterministic stubs."""

    monkeypatch.setattr(
        "core.orchestrator._default_agent_factories",
        lambda: {name: (lambda n=name: _StaticAgent(n)) for name in AGENT_NAMES},
    )
    monkeypatch.setattr(
        "core.orchestrator._default_critic_factory",
        lambda: lambda: _StaticCritic(),
    )
    monkeypatch.setattr(
        "core.orchestrator._default_refiner_factory",
        lambda: lambda: _StaticRefiner(),
    )
    monkeypatch.setattr("core.orchestrator.build_qaoa_circuit", _fake_build_qaoa_circuit)
    monkeypatch.setattr("core.orchestrator.simulate_circuit", _fake_simulate_circuit)
    monkeypatch.setattr("core.orchestrator.run_classical_baseline", _fake_classical_baseline)


@pytest_asyncio.fixture()
async def app_client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio
async def test_two_users_concurrent_runs_with_full_isolation(
    concurrent_users: dict[str, TestUser],
    app_client: httpx.AsyncClient,
) -> None:
    user_a = concurrent_users["a"]
    user_b = concurrent_users["b"]
    headers_a = {"Authorization": f"Bearer {user_a['access_token']}"}
    headers_b = {"Authorization": f"Bearer {user_b['access_token']}"}

    create_a = app_client.post(
        "/api/runs",
        json={"input_source": "template", "template_name": "portfolio"},
        headers=headers_a,
    )
    create_b = app_client.post(
        "/api/runs",
        json={"input_source": "template", "template_name": "portfolio"},
        headers=headers_b,
    )
    response_a, response_b = await asyncio.gather(create_a, create_b)

    assert response_a.status_code == 201, response_a.text
    assert response_b.status_code == 201, response_b.text
    run_a_id = response_a.json()["run_id"]
    run_b_id = response_b.json()["run_id"]
    assert run_a_id != run_b_id

    final_a, final_b = await asyncio.gather(
        _poll_until_terminal(app_client, run_a_id, headers_a),
        _poll_until_terminal(app_client, run_b_id, headers_b),
    )
    assert final_a["status"] == "done", final_a
    assert final_b["status"] == "done", final_b
    assert final_a["winner_agent"] in AGENT_NAMES
    assert final_b["winner_agent"] in AGENT_NAMES

    cross_a = await app_client.get(f"/api/runs/{run_b_id}", headers=headers_a)
    cross_b = await app_client.get(f"/api/runs/{run_a_id}", headers=headers_b)
    assert cross_a.status_code == 404, cross_a.text
    assert cross_b.status_code == 404, cross_b.text

    list_a = await app_client.get("/api/runs", headers=headers_a)
    list_b = await app_client.get("/api/runs", headers=headers_b)
    assert list_a.status_code == 200
    assert list_b.status_code == 200
    ids_a = [item["id"] for item in list_a.json()["items"]]
    ids_b = [item["id"] for item in list_b.json()["items"]]
    assert ids_a == [run_a_id]
    assert ids_b == [run_b_id]

    events_cross_a = await app_client.get(f"/api/runs/{run_b_id}/events", headers=headers_a)
    events_cross_b = await app_client.get(f"/api/runs/{run_a_id}/events", headers=headers_b)
    assert events_cross_a.status_code == 404
    assert events_cross_b.status_code == 404

    service = get_service_client()
    profile_a = (
        service.table("users_profile")
        .select("monthly_runs_used")
        .eq("id", user_a["id"])
        .single()
        .execute()
    )
    profile_b = (
        service.table("users_profile")
        .select("monthly_runs_used")
        .eq("id", user_b["id"])
        .single()
        .execute()
    )
    assert profile_a.data["monthly_runs_used"] == 1
    assert profile_b.data["monthly_runs_used"] == 1


async def _poll_until_terminal(
    client: httpx.AsyncClient,
    run_id: str,
    headers: dict[str, str],
) -> dict[str, Any]:
    terminal = {"done", "failed", "timeout", "cancelled"}
    deadline = asyncio.get_event_loop().time() + PIPELINE_POLL_TIMEOUT
    while asyncio.get_event_loop().time() < deadline:
        response = await client.get(f"/api/runs/{run_id}", headers=headers)
        if response.status_code == 200:
            payload: dict[str, Any] = response.json()
            if payload["status"] in terminal:
                return payload
        await asyncio.sleep(PIPELINE_POLL_INTERVAL)
    raise AssertionError(
        f"run {run_id} did not reach a terminal status within {PIPELINE_POLL_TIMEOUT}s"
    )


class _suppress_admin_error:
    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        del exc, tb
        return exc_type is not None
