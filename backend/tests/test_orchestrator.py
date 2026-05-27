from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Literal, cast

import pytest

from core.agents.base import AgentContext, QUBOAgent, QUBOOutput
from core.agents.critic import CriticVerdict
from core.agents.refiner import RefinedQUBO, no_improvement_refinement
from core.evaluator import ComparisonTable, Scorecard
from core.orchestrator import (
    AGENT_NAMES,
    EventCallback,
    PipelineEvent,
    PipelineState,
    run_pipeline,
)
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
                "symmetric QUBO for orchestrator testing without external Gemini calls."
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


def _agent_factories(
    failing_agents: set[str] | None = None,
    delays: dict[str, float] | None = None,
) -> dict[str, Callable[[], QUBOAgent]]:
    failures = failing_agents or set()
    delay_by_name = delays or {}
    factories: dict[str, Callable[[], QUBOAgent]] = {}
    for agent_name in AGENT_NAMES:

        def build_agent(name: str = agent_name) -> QUBOAgent:
            return StaticAgent(
                name,
                fail=name in failures,
                delay_seconds=delay_by_name.get(name, 0.0),
            )

        factories[agent_name] = build_agent
    return factories


def _patch_agent_factories(
    monkeypatch: pytest.MonkeyPatch,
    failing_agents: set[str] | None = None,
    delays: dict[str, float] | None = None,
) -> None:
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


@pytest.mark.asyncio
@pytest.mark.parametrize("template_name", ["portfolio", "max_cut", "knapsack"])
async def test_full_pipeline_runs_on_templates(
    monkeypatch: pytest.MonkeyPatch,
    template_name: str,
) -> None:
    _patch_agent_factories(monkeypatch)

    state = await run_pipeline(get_template(template_name), run_id=f"run-{template_name}")

    assert state.get("pipeline_failed") is False
    assert len(state["qubos"]) == 5
    assert len(state["scorecards"]) == 5
    assert state["critic_verdict"].winner_agent in state["qubos"]
    assert state["comparison_table"].top_agent == state["critic_verdict"].winner_agent
    assert state["refined_qubo"].agent_name == state["critic_verdict"].winner_agent
    assert state["circuit_data"].qubit_count == state["refined_qubo"].estimated_qubits
    assert state["sim_result"].best_bitstring
    assert state["classical_result"].feasible is True
    assert state["events"][-1].event_type == "pipeline_done"


@pytest.mark.asyncio
async def test_pipeline_survives_two_agent_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_agent_factories(monkeypatch, failing_agents={"penalty", "slack"})

    state = await run_pipeline(get_template("portfolio"), run_id="run-partial")

    assert state.get("pipeline_failed") is False
    assert len(state["qubos"]) == 3
    assert len(state["errors"]) == 2
    assert [event.event_type for event in state["events"]].count("agent_failed") == 2
    assert state["events"][-1].event_type == "pipeline_done"


@pytest.mark.asyncio
async def test_pipeline_fails_gracefully_when_four_agents_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_agent_factories(monkeypatch, failing_agents={"penalty", "slack", "graph", "decomp"})

    state = await run_pipeline(get_template("portfolio"), run_id="run-failed")

    assert state.get("pipeline_failed") is True
    assert len(state["qubos"]) == 1
    assert len(state["errors"]) == 5
    assert state["errors"][-1].node == "evaluator"
    assert state["events"][-1].event_type == "pipeline_failed"
    assert "fewer than 3 agents succeeded" in state["events"][-1].payload["reason"]


@pytest.mark.asyncio
async def test_event_callback_receives_events_in_pipeline_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_agent_factories(monkeypatch)
    received: list[PipelineEvent] = []

    async def callback(event: PipelineEvent) -> None:
        received.append(event)

    state = await run_pipeline(
        get_template("portfolio"),
        run_id="run-events",
        event_callback=cast(EventCallback, callback),
    )

    event_types = [event.event_type for event in received]
    assert event_types.count("agent_started") == 5
    assert event_types.count("agent_done") == 5
    assert event_types.index("scorecard_ready") > max(
        index for index, event_type in enumerate(event_types) if event_type == "agent_done"
    )
    assert event_types.count("scorecard_ready") == 5
    assert event_types.index("comparison_ready") > max(
        index for index, event_type in enumerate(event_types) if event_type == "scorecard_ready"
    )
    assert event_types.index("critic_verdict") > event_types.index("comparison_ready")
    assert event_types.index("refiner_done") > event_types.index("critic_verdict")
    assert event_types.index("circuit_ready") > event_types.index("refiner_done")
    assert event_types.index("simulation_done") > event_types.index("circuit_ready")
    assert event_types[-1] == "pipeline_done"
    assert state["events"][-1].event_type == "pipeline_done"


@pytest.mark.asyncio
async def test_low_score_critic_path_retries_refiner_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_agent_factories(monkeypatch)
    monkeypatch.setattr("core.orchestrator.LOW_SCORE_THRESHOLD", 9.99)

    state = await run_pipeline(get_template("portfolio"), run_id="run-low-score")

    event_types = [event.event_type for event in state["events"]]
    refiner_events = [event for event in state["events"] if event.event_type == "refiner_done"]
    assert event_types.count("critic_verdict") == 2
    assert len(refiner_events) == 2
    assert refiner_events[0].payload["with_hints"] is True
    assert refiner_events[1].payload["with_hints"] is False
    assert refiner_events[1].payload["low_score_proceed"] is True
    assert state["events"][-1].event_type == "pipeline_done"


@pytest.mark.asyncio
async def test_timeout_enforcement_emits_pipeline_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_agent_factories(monkeypatch, delays={"penalty": 200.0})
    monkeypatch.setattr("core.orchestrator.PIPELINE_TIMEOUT_SECONDS", 0.01)
    received: list[PipelineEvent] = []

    async def callback(event: PipelineEvent) -> None:
        received.append(event)

    state: PipelineState = await run_pipeline(
        get_template("portfolio"),
        run_id="run-timeout",
        event_callback=cast(EventCallback, callback),
    )

    assert state.get("pipeline_failed") is True
    assert state["events"][-1].event_type == "pipeline_failed"
    assert state["errors"][-1].error_type == "TimeoutError"
    assert received[-1].event_type == "pipeline_failed"
