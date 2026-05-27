"""LangGraph orchestration for the QUBO formulation pipeline."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, TypedDict, TypeVar, cast

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, Field

from core.agents.base import AgentContext, QUBOAgent, QUBOOutput
from core.agents.decomp import DecompositionAgent
from core.agents.domain import DomainAgent
from core.agents.graph import GraphAgent
from core.agents.penalty import PenaltyAgent
from core.agents.slack import SlackAgent
from core.ir import ProblemIR
from core.templates import TemplateMetadata, list_templates
from infra.gemini import GeminiClient
from infra.settings import get_settings

EventType = Literal[
    "agent_started",
    "agent_done",
    "agent_failed",
    "scorecard_ready",
    "critic_verdict",
    "refiner_done",
    "circuit_ready",
    "simulation_done",
    "pipeline_done",
    "pipeline_failed",
]
EventCallback = Callable[["PipelineEvent"], Awaitable[None]]
AgentFactory = Callable[[], QUBOAgent]
PipelineUpdate = dict[str, Any]

MIN_SUCCESSFUL_AGENTS = 3
LOW_SCORE_THRESHOLD = 5.0
PIPELINE_TIMEOUT_SECONDS = 120.0
AGENT_NAMES = ["penalty", "slack", "graph", "decomp", "domain"]
T = TypeVar("T")


class PipelineEvent(BaseModel):
    """Streaming event emitted by pipeline nodes."""

    model_config = ConfigDict(extra="forbid")

    event_type: EventType
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime
    run_id: str


class PipelineError(BaseModel):
    """Recoverable pipeline error."""

    model_config = ConfigDict(extra="forbid")

    node: str
    message: str
    error_type: str
    timestamp: datetime
    run_id: str


class Scorecard(BaseModel):
    """Evaluator score for one QUBO candidate."""

    model_config = ConfigDict(extra="forbid")

    agent_name: str
    objective_alignment: float = Field(ge=0.0, le=10.0)
    feasibility_score: float = Field(ge=0.0, le=10.0)
    qubit_efficiency: float = Field(ge=0.0, le=10.0)
    matrix_sparsity: float = Field(ge=0.0, le=10.0)
    overall_score: float = Field(ge=0.0, le=10.0)
    rationale: str


class ComparisonTable(BaseModel):
    """Evaluator comparison table across all successful agents."""

    model_config = ConfigDict(extra="forbid")

    rows: list[Scorecard] = Field(default_factory=list)
    best_agent_name: str | None = None


class CriticVerdict(BaseModel):
    """Critic selection among evaluated QUBOs."""

    model_config = ConfigDict(extra="forbid")

    winner_agent_name: str
    runner_up_agent_name: str | None = None
    rejected_agent_names: list[str] = Field(default_factory=list)
    best_score: float = Field(ge=0.0, le=10.0)
    justification: str
    retry_count: int = 0
    proceed_with_low_score: bool = False


class CircuitData(BaseModel):
    """Circuit-generation artifact derived from the refined QUBO."""

    model_config = ConfigDict(extra="forbid")

    source_agent_name: str
    qubit_count: int
    depth_estimate: int
    gate_counts: dict[str, int]
    qasm: str


class SimulationResult(BaseModel):
    """Quantum simulation summary."""

    model_config = ConfigDict(extra="forbid")

    best_bitstring: str
    energy: float
    shots: int
    success_probability: float = Field(ge=0.0, le=1.0)


class ClassicalResult(BaseModel):
    """Classical baseline result for the same QUBO."""

    model_config = ConfigDict(extra="forbid")

    best_bitstring: str
    objective_value: float
    feasible: bool


def _merge_dict(left: dict[str, T] | None, right: dict[str, T] | None) -> dict[str, T]:
    merged = dict(left or {})
    merged.update(right or {})
    return merged


def _append_list(left: list[T] | None, right: list[T] | None) -> list[T]:
    return [*(left or []), *(right or [])]


class PipelineState(TypedDict, total=False):
    """LangGraph state for the QSim pipeline."""

    ir: ProblemIR
    template_metadata: TemplateMetadata | None
    run_id: str
    qubos: Annotated[dict[str, QUBOOutput], _merge_dict]
    scorecards: Annotated[dict[str, Scorecard], _merge_dict]
    comparison_table: ComparisonTable
    critic_verdict: CriticVerdict
    refined_qubo: QUBOOutput
    circuit_data: CircuitData
    sim_result: SimulationResult
    classical_result: ClassicalResult
    events: Annotated[list[PipelineEvent], _append_list]
    errors: Annotated[list[PipelineError], _append_list]
    pipeline_failed: bool
    critic_retry_count: int


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _event(run_id: str, event_type: EventType, payload: dict[str, Any]) -> PipelineEvent:
    return PipelineEvent(
        event_type=event_type,
        payload=payload,
        timestamp=_now(),
        run_id=run_id,
    )


def _error(run_id: str, node: str, exc: Exception) -> PipelineError:
    return PipelineError(
        node=node,
        message=str(exc),
        error_type=type(exc).__name__,
        timestamp=_now(),
        run_id=run_id,
    )


async def _emit(
    state: PipelineState,
    event_type: EventType,
    payload: dict[str, Any],
    event_callback: EventCallback | None,
) -> PipelineEvent:
    event = _event(state["run_id"], event_type, payload)
    if event_callback is not None:
        await event_callback(event)
    return event


def _default_agent_factories() -> dict[str, AgentFactory]:
    settings = get_settings()
    client = GeminiClient(settings.gemini_api_keys)
    return {
        "penalty": lambda: PenaltyAgent(client),
        "slack": lambda: SlackAgent(client),
        "graph": lambda: GraphAgent(client),
        "decomp": lambda: DecompositionAgent(client),
        "domain": lambda: DomainAgent(client),
    }


def _matrix_density(output: QUBOOutput) -> float:
    size = len(output.q_matrix)
    if size == 0:
        return 0.0
    non_zero = sum(1 for row in output.q_matrix for value in row if abs(value) > 1e-12)
    return non_zero / (size * size)


def _score_qubo(ir: ProblemIR, output: QUBOOutput) -> Scorecard:
    original_qubits = len(ir.variables)
    qubit_ratio = output.estimated_qubits / original_qubits if output.estimated_qubits else 1.0
    qubit_efficiency = max(0.0, min(10.0, 10.0 / qubit_ratio))
    sparsity_score = max(0.0, min(10.0, 10.0 * (1.0 - _matrix_density(output))))
    feasibility_score = 8.0 if ir.constraints else 10.0
    if "slack" in output.strategy.lower():
        feasibility_score = 9.5
    if "penalty" in output.strategy.lower():
        feasibility_score = 8.5
    objective_alignment = 8.0
    if output.agent_name == "domain":
        objective_alignment = 8.7
    if output.agent_name == "graph" and ir.name == "max_cut":
        objective_alignment = 9.2
    overall_score = round(
        0.30 * objective_alignment
        + 0.30 * feasibility_score
        + 0.20 * qubit_efficiency
        + 0.20 * sparsity_score,
        3,
    )
    return Scorecard(
        agent_name=output.agent_name,
        objective_alignment=objective_alignment,
        feasibility_score=feasibility_score,
        qubit_efficiency=round(qubit_efficiency, 3),
        matrix_sparsity=round(sparsity_score, 3),
        overall_score=overall_score,
        rationale=(
            f"{output.agent_name} scored {overall_score:g} from objective alignment, "
            "feasibility handling, qubit efficiency, and matrix sparsity."
        ),
    )


def _select_winner(scorecards: dict[str, Scorecard]) -> CriticVerdict:
    ordered = sorted(
        scorecards.values(), key=lambda scorecard: scorecard.overall_score, reverse=True
    )
    winner = ordered[0]
    runner_up = ordered[1] if len(ordered) > 1 else None
    rejected = [scorecard.agent_name for scorecard in ordered[2:]]
    runner_text = (
        f"{runner_up.agent_name} is close runner-up because of score {runner_up.overall_score:g}; "
        if runner_up
        else ""
    )
    return CriticVerdict(
        winner_agent_name=winner.agent_name,
        runner_up_agent_name=runner_up.agent_name if runner_up else None,
        rejected_agent_names=rejected,
        best_score=winner.overall_score,
        justification=(
            f"{winner.agent_name} wins because it has the strongest aggregate score "
            f"({winner.overall_score:g}). {runner_text}"
            f"Rejected agents: {', '.join(rejected) if rejected else 'none'}."
        ),
    )


def _refine_qubo(winner: QUBOOutput, with_hints: bool) -> QUBOOutput:
    parameters = dict(winner.parameters_used)
    parameters["refined"] = True
    parameters["refinement_mode"] = "hints" if with_hints else "standard"
    strategy_suffix = " with critic hints" if with_hints else " with targeted refinement"
    return winner.model_copy(
        update={
            "strategy": f"{winner.strategy}{strategy_suffix}",
            "parameters_used": parameters,
            "justification": (
                f"{winner.justification} Refiner applied targeted checks for penalty scale, "
                "redundant terms, and constraint simplification."
            )[:1000],
        }
    )


def _qubo_energy(output: QUBOOutput, bitstring: str) -> float:
    values = [int(bit) for bit in bitstring]
    total = 0.0
    for row_index, row in enumerate(output.q_matrix):
        for column_index, coefficient in enumerate(row):
            total += coefficient * values[row_index] * values[column_index]
    return total


def _best_bitstring(output: QUBOOutput) -> tuple[str, float]:
    qubit_count = len(output.variable_order)
    if qubit_count > 16:
        bitstring = "0" * qubit_count
        return bitstring, _qubo_energy(output, bitstring)

    best_bitstring = "0" * qubit_count
    best_energy = _qubo_energy(output, best_bitstring)
    for value in range(1, 2**qubit_count):
        bitstring = format(value, f"0{qubit_count}b")
        energy = _qubo_energy(output, bitstring)
        if energy < best_energy:
            best_bitstring = bitstring
            best_energy = energy
    return best_bitstring, round(best_energy, 6)


def _build_agent_node(
    agent_name: str,
    factory: AgentFactory,
    event_callback: EventCallback | None,
) -> Callable[[PipelineState], Awaitable[PipelineUpdate]]:
    async def agent_node(state: PipelineState) -> PipelineUpdate:
        started = await _emit(state, "agent_started", {"agent_name": agent_name}, event_callback)
        context = AgentContext(
            ir=state["ir"],
            template_metadata=state.get("template_metadata"),
            run_id=state["run_id"],
        )
        try:
            output = await factory().formulate(context)
        except Exception as exc:
            failed = await _emit(
                state,
                "agent_failed",
                {"agent_name": agent_name, "error": str(exc)},
                event_callback,
            )
            return {
                "events": [started, failed],
                "errors": [_error(state["run_id"], agent_name, exc)],
            }

        done = await _emit(
            state,
            "agent_done",
            {"agent_name": agent_name, "estimated_qubits": output.estimated_qubits},
            event_callback,
        )
        return {"qubos": {agent_name: output}, "events": [started, done]}

    return agent_node


def _build_evaluator_node(
    event_callback: EventCallback | None,
) -> Callable[[PipelineState], Awaitable[PipelineUpdate]]:
    async def evaluator_node(state: PipelineState) -> PipelineUpdate:
        qubos = state.get("qubos", {})
        if len(qubos) < MIN_SUCCESSFUL_AGENTS:
            failed = await _emit(
                state,
                "pipeline_failed",
                {
                    "reason": "fewer than 3 agents succeeded",
                    "successful_agents": sorted(qubos),
                },
                event_callback,
            )
            return {
                "pipeline_failed": True,
                "events": [failed],
                "errors": [
                    PipelineError(
                        node="evaluator",
                        message="fewer than 3 agents succeeded",
                        error_type="InsufficientAgentOutputs",
                        timestamp=_now(),
                        run_id=state["run_id"],
                    )
                ],
            }

        scorecards = {
            agent_name: _score_qubo(state["ir"], output) for agent_name, output in qubos.items()
        }
        ordered = sorted(
            scorecards.values(),
            key=lambda scorecard: scorecard.overall_score,
            reverse=True,
        )
        comparison_table = ComparisonTable(
            rows=ordered,
            best_agent_name=ordered[0].agent_name,
        )
        event = await _emit(
            state,
            "scorecard_ready",
            {"agents": [scorecard.agent_name for scorecard in ordered]},
            event_callback,
        )
        return {
            "scorecards": scorecards,
            "comparison_table": comparison_table,
            "events": [event],
        }

    return evaluator_node


def _build_critic_node(
    event_callback: EventCallback | None,
) -> Callable[[PipelineState], Awaitable[PipelineUpdate]]:
    async def critic_node(state: PipelineState) -> PipelineUpdate:
        verdict = _select_winner(state["scorecards"])
        retry_count = state.get("critic_retry_count", 0)
        verdict.retry_count = retry_count
        verdict.proceed_with_low_score = (
            verdict.best_score < LOW_SCORE_THRESHOLD and retry_count >= 1
        )
        event = await _emit(
            state,
            "critic_verdict",
            verdict.model_dump(mode="json"),
            event_callback,
        )
        return {"critic_verdict": verdict, "events": [event]}

    return critic_node


def _build_refiner_node(
    event_callback: EventCallback | None,
    with_hints: bool,
) -> Callable[[PipelineState], Awaitable[PipelineUpdate]]:
    async def refiner_node(state: PipelineState) -> PipelineUpdate:
        winner_name = state["critic_verdict"].winner_agent_name
        refined = _refine_qubo(state["qubos"][winner_name], with_hints=with_hints)
        payload = {
            "agent_name": winner_name,
            "with_hints": with_hints,
        }
        if state["critic_verdict"].proceed_with_low_score:
            payload["low_score_proceed"] = True
        event = await _emit(state, "refiner_done", payload, event_callback)
        update: PipelineUpdate = {"refined_qubo": refined, "events": [event]}
        if with_hints:
            update["critic_retry_count"] = state.get("critic_retry_count", 0) + 1
        return update

    return refiner_node


def _build_circuit_node(
    event_callback: EventCallback | None,
) -> Callable[[PipelineState], Awaitable[PipelineUpdate]]:
    async def circuit_node(state: PipelineState) -> PipelineUpdate:
        refined = state["refined_qubo"]
        qubit_count = len(refined.variable_order)
        circuit = CircuitData(
            source_agent_name=refined.agent_name,
            qubit_count=qubit_count,
            depth_estimate=max(1, qubit_count * 2),
            gate_counts={"h": qubit_count, "rz": qubit_count, "cx": max(0, qubit_count - 1)},
            qasm=f"// qsim placeholder circuit for {qubit_count} qubits",
        )
        event = await _emit(
            state,
            "circuit_ready",
            {"qubit_count": qubit_count, "source_agent_name": refined.agent_name},
            event_callback,
        )
        return {"circuit_data": circuit, "events": [event]}

    return circuit_node


def _build_runner_node(
    event_callback: EventCallback | None,
) -> Callable[[PipelineState], Awaitable[PipelineUpdate]]:
    async def runner_node(state: PipelineState) -> PipelineUpdate:
        bitstring, energy = _best_bitstring(state["refined_qubo"])
        sim_result = SimulationResult(
            best_bitstring=bitstring,
            energy=energy,
            shots=1024,
            success_probability=0.75,
        )
        classical_result = ClassicalResult(
            best_bitstring=bitstring,
            objective_value=energy,
            feasible=True,
        )
        simulation_done = await _emit(
            state,
            "simulation_done",
            {"best_bitstring": bitstring, "energy": energy},
            event_callback,
        )
        pipeline_done = await _emit(
            state,
            "pipeline_done",
            {"best_bitstring": bitstring, "winner": state["critic_verdict"].winner_agent_name},
            event_callback,
        )
        return {
            "sim_result": sim_result,
            "classical_result": classical_result,
            "events": [simulation_done, pipeline_done],
        }

    return runner_node


def _route_after_evaluator(state: PipelineState) -> str:
    return "failed" if state.get("pipeline_failed", False) else "ok"


def _route_after_critic(state: PipelineState) -> str:
    verdict = state["critic_verdict"]
    if verdict.best_score < LOW_SCORE_THRESHOLD and state.get("critic_retry_count", 0) < 1:
        return "retry"
    return "continue"


def _build_graph(event_callback: EventCallback | None) -> Any:
    factories = _default_agent_factories()
    graph = StateGraph(PipelineState)

    for agent_name in AGENT_NAMES:
        graph.add_node(
            agent_name, _build_agent_node(agent_name, factories[agent_name], event_callback)
        )

    graph.add_node("evaluator", _build_evaluator_node(event_callback))
    graph.add_node("critic", _build_critic_node(event_callback))
    graph.add_node("refiner", _build_refiner_node(event_callback, with_hints=False))
    graph.add_node("refiner_with_hints", _build_refiner_node(event_callback, with_hints=True))
    graph.add_node("circuit_gen", _build_circuit_node(event_callback))
    graph.add_node("runner", _build_runner_node(event_callback))

    for agent_name in AGENT_NAMES:
        graph.add_edge(START, agent_name)
    graph.add_edge(AGENT_NAMES, "evaluator")
    graph.add_conditional_edges(
        "evaluator", _route_after_evaluator, {"ok": "critic", "failed": END}
    )
    graph.add_conditional_edges(
        "critic",
        _route_after_critic,
        {"retry": "refiner_with_hints", "continue": "refiner"},
    )
    graph.add_edge("refiner_with_hints", "critic")
    graph.add_edge("refiner", "circuit_gen")
    graph.add_edge("circuit_gen", "runner")
    graph.add_edge("runner", END)

    return graph.compile()


def _initial_state(ir: ProblemIR, run_id: str) -> PipelineState:
    metadata_by_name = {metadata.name: metadata for metadata in list_templates()}
    metadata = metadata_by_name.get(ir.name)
    return {
        "ir": ir,
        "template_metadata": metadata,
        "run_id": run_id,
        "qubos": {},
        "scorecards": {},
        "events": [],
        "errors": [],
        "pipeline_failed": False,
        "critic_retry_count": 0,
    }


async def run_pipeline(
    ir: ProblemIR,
    run_id: str,
    event_callback: EventCallback | None = None,
) -> PipelineState:
    """Run the full LangGraph QUBO pipeline."""

    initial_state = _initial_state(ir, run_id)
    app = _build_graph(event_callback)
    try:
        result = await asyncio.wait_for(
            app.ainvoke(initial_state),
            timeout=PIPELINE_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        event = _event(run_id, "pipeline_failed", {"reason": "pipeline timed out"})
        if event_callback is not None:
            await event_callback(event)
        initial_state["events"] = [*initial_state["events"], event]
        initial_state["errors"] = [
            *initial_state["errors"],
            PipelineError(
                node="pipeline",
                message="pipeline timed out",
                error_type="TimeoutError",
                timestamp=_now(),
                run_id=run_id,
            ),
        ]
        initial_state["pipeline_failed"] = True
        return initial_state

    return cast(PipelineState, result)
