from __future__ import annotations

import json
from typing import Any, cast

import pytest

from core.agents.base import QUBOOutput
from core.agents.critic import CriticAgent, CriticVerdict
from core.agents.refiner import RefinedQUBO, RefinerAgent, no_improvement_refinement
from core.evaluator import ComparisonTable, Scorecard
from infra.gemini import GeminiClient


def _scorecard(agent_name: str, score: float, qubits: int = 6) -> Scorecard:
    return Scorecard(
        agent_name=agent_name,
        qubit_count=qubits,
        sparsity=0.5,
        condition_number=2.5,
        penalty_sensitivity=0.1,
        classical_baseline_objective=-1.25,
        classical_baseline_runtime_ms=2.0,
        composite_score=score,
        notes="metrics are within expected ranges",
    )


def _comparison_table(scores: list[Scorecard]) -> ComparisonTable:
    ordered = sorted(scores, key=lambda scorecard: scorecard.composite_score, reverse=True)
    return ComparisonTable(
        scorecards=ordered,
        top_agent=ordered[0].agent_name,
        runner_up=ordered[1].agent_name,
    )


def _winner_qubo() -> QUBOOutput:
    return QUBOOutput(
        agent_name="domain",
        strategy="domain-specific formulation",
        q_matrix=[[1.0, 0.2], [0.2, 2.0]],
        variable_order=["x_0", "x_1"],
        parameters_used={"lambda": 4.5},
        justification=(
            "The domain formulation preserves the known structure while using a calibrated "
            "constraint penalty for a compact and symmetric QUBO."
        ),
    )


def _extract_backticked_json(prompt: str, label: str) -> dict[str, object]:
    start = prompt.index(label) + len(label)
    fragment = prompt[start:]
    first_tick = fragment.index("`") + 1
    second_tick = fragment.index("`", first_tick)
    raw = fragment[first_tick:second_tick]
    data = json.loads(raw)
    assert isinstance(data, dict)
    return data


class FakeCriticGeminiClient:
    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.temperatures: list[float] = []

    async def generate_json(
        self,
        prompt: str,
        schema: type[CriticVerdict],
        temperature: float = 0.2,
    ) -> CriticVerdict:
        self.prompts.append(prompt)
        self.temperatures.append(temperature)
        table = _extract_backticked_json(prompt, "Comparison table JSON:")
        scorecards = table["scorecards"]
        assert isinstance(scorecards, list)
        top = scorecards[0]
        runner_up = scorecards[1]
        assert isinstance(top, dict)
        assert isinstance(runner_up, dict)
        gap = float(top["composite_score"]) - float(runner_up["composite_score"])
        confidence = "high" if gap >= 1.0 else "low" if gap < 0.25 else "medium"
        rejected = [
            str(scorecard["agent_name"])
            for scorecard in scorecards[2:]
            if isinstance(scorecard, dict)
        ]
        return schema.model_validate(
            {
                "winner_agent": top["agent_name"],
                "runner_up_agent": runner_up["agent_name"],
                "rejected_agents": rejected,
                "rationale": (
                    f"{top['agent_name']} wins with composite_score={top['composite_score']} "
                    f"and qubit_count={top['qubit_count']}; {runner_up['agent_name']} is "
                    f"runner-up with composite_score={runner_up['composite_score']}."
                ),
                "confidence": confidence,
            }
        )


class FakeRefinerGeminiClient:
    def __init__(self, no_improvement: bool = False) -> None:
        self.no_improvement = no_improvement
        self.prompts: list[str] = []
        self.temperatures: list[float] = []

    async def generate_json(
        self,
        prompt: str,
        schema: type[RefinedQUBO],
        temperature: float = 0.2,
    ) -> RefinedQUBO:
        self.prompts.append(prompt)
        self.temperatures.append(temperature)
        qubo_data = _extract_backticked_json(prompt, "Winner QUBO JSON:")
        if self.no_improvement:
            qubo = QUBOOutput.model_validate(qubo_data)
            return schema.model_validate(no_improvement_refinement(qubo).model_dump())

        parameters = cast(dict[str, Any], qubo_data["parameters_used"])
        qubo_data["parameters_used"] = {**parameters, "lambda": 3.8}
        qubo_data.update(
            {
                "original_agent": qubo_data["agent_name"],
                "improvements_made": [
                    "Reduced lambda from 4.5 to 3.8 based on sensitivity analysis"
                ],
                "expected_improvement": (
                    "The lower penalty weight should reduce sensitivity while preserving the "
                    "same symmetric matrix shape and variable order."
                ),
            }
        )
        return schema.model_validate(qubo_data)


@pytest.mark.asyncio
async def test_critic_clear_winner_picks_correctly_and_references_metrics() -> None:
    table = _comparison_table(
        [
            _scorecard("domain", 8.7),
            _scorecard("graph", 7.1),
            _scorecard("slack", 5.5),
        ]
    )
    fake_client = FakeCriticGeminiClient()
    critic = CriticAgent(cast(GeminiClient, fake_client))

    verdict = await critic.judge(table)

    assert verdict.winner_agent == "domain"
    assert verdict.runner_up_agent == "graph"
    assert verdict.confidence == "high"
    assert "8.7" in verdict.rationale
    assert "qubit_count" in verdict.rationale
    assert fake_client.temperatures == [0.3]


@pytest.mark.asyncio
async def test_critic_near_identical_scorecards_returns_low_confidence() -> None:
    table = _comparison_table(
        [
            _scorecard("domain", 8.02),
            _scorecard("graph", 7.91),
            _scorecard("slack", 7.84),
        ]
    )
    critic = CriticAgent(cast(GeminiClient, FakeCriticGeminiClient()))

    verdict = await critic.judge(table)

    assert verdict.winner_agent == "domain"
    assert verdict.confidence == "low"


@pytest.mark.asyncio
async def test_refiner_produces_valid_refined_qubo() -> None:
    fake_client = FakeRefinerGeminiClient()
    refiner = RefinerAgent(cast(GeminiClient, fake_client))

    refined = await refiner.refine(_winner_qubo(), _scorecard("domain", 8.7))

    assert refined.original_agent == "domain"
    assert refined.improvements_made
    assert refined.parameters_used["lambda"] == 3.8
    assert refined.estimated_qubits == 2
    assert refined.q_matrix[0][1] == refined.q_matrix[1][0]
    assert fake_client.temperatures == [0.4]


@pytest.mark.asyncio
async def test_refiner_no_improvement_path_keeps_pipeline_safe() -> None:
    refiner = RefinerAgent(cast(GeminiClient, FakeRefinerGeminiClient(no_improvement=True)))

    refined = await refiner.refine(_winner_qubo(), _scorecard("domain", 8.7))

    assert refined.improvements_made == ["none — original was already near-optimal"]
    assert refined.original_agent == "domain"
    assert refined.q_matrix == _winner_qubo().q_matrix
    assert refined.estimated_qubits == 2


def test_no_improvement_refinement_preserves_symmetric_matrix() -> None:
    refined = no_improvement_refinement(_winner_qubo())

    assert refined.q_matrix[0][1] == refined.q_matrix[1][0]
    assert refined.variable_order == ["x_0", "x_1"]
