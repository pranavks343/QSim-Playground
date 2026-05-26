from __future__ import annotations

import json

import pytest

from core.critic_refiner import (
    CriticAgent,
    LLMResponseError,
    QuboCandidate,
    RefinerAgent,
    Scorecard,
)


class FakeGeminiClient:
    def __init__(self, response: dict[str, object] | str) -> None:
        self.response = response
        self.prompts: list[str] = []

    def generate_json(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if isinstance(self.response, str):
            return self.response
        return json.dumps(self.response)


def scorecard(index: int) -> Scorecard:
    candidate_id = f"candidate_{index}"
    agent_name = f"agent_{index}"
    return Scorecard(
        candidate_id=candidate_id,
        agent_name=agent_name,
        objective_value=float(10 - index),
        feasibility_score=1.0 - (index * 0.05),
        approximation_ratio=0.9 - (index * 0.01),
        runtime_ms=100.0 + index,
        qubit_count=6 + index,
        circuit_depth=12 + index,
        notes=f"scorecard {index}",
        qubo=QuboCandidate(
            candidate_id=candidate_id,
            agent_name=agent_name,
            linear_terms={"x_0": 1.0 + index},
            quadratic_terms={"x_0,x_1": -2.0},
            penalty_weight=10.0 + index,
            notes=f"qubo {index}",
        ),
    )


def five_scorecards() -> list[Scorecard]:
    return [scorecard(index) for index in range(5)]


def test_critic_ranks_top_two_with_one_gemini_call() -> None:
    fake = FakeGeminiClient(
        {
            "top_two": [
                {
                    "rank": 1,
                    "candidate_id": "candidate_0",
                    "agent_name": "agent_0",
                    "reason": "best feasible objective",
                },
                {
                    "rank": 2,
                    "candidate_id": "candidate_1",
                    "agent_name": "agent_1",
                    "reason": "close objective with slightly more depth",
                },
            ],
            "justification": (
                "agent_0 wins because of feasibility and objective quality; agent_1 is close "
                "runner-up because its score is similar; agent_4 is rejected because it is slower."
            ),
        }
    )

    decision = CriticAgent(fake).rank(five_scorecards())

    assert len(fake.prompts) == 1
    assert "exactly five QUBO scorecards" in fake.prompts[0]
    assert [candidate.candidate_id for candidate in decision.top_two] == [
        "candidate_0",
        "candidate_1",
    ]


def test_critic_requires_exactly_five_scorecards() -> None:
    fake = FakeGeminiClient({})

    with pytest.raises(ValueError, match="exactly 5 scorecards"):
        CriticAgent(fake).rank(five_scorecards()[:4])

    assert fake.prompts == []


def test_critic_rejects_unknown_candidate_from_llm() -> None:
    fake = FakeGeminiClient(
        {
            "top_two": [
                {
                    "rank": 1,
                    "candidate_id": "candidate_0",
                    "agent_name": "agent_0",
                    "reason": "best",
                },
                {
                    "rank": 2,
                    "candidate_id": "missing",
                    "agent_name": "agent_x",
                    "reason": "invalid",
                },
            ],
            "justification": "candidate_0 wins because of A; missing is invalid because of B.",
        }
    )

    with pytest.raises(LLMResponseError, match="unknown candidate ids"):
        CriticAgent(fake).rank(five_scorecards())


def test_critic_rejects_invalid_json_response() -> None:
    fake = FakeGeminiClient("not json")

    with pytest.raises(LLMResponseError, match="not valid JSON"):
        CriticAgent(fake).rank(five_scorecards())


def test_refiner_returns_improved_qubo_with_one_gemini_call() -> None:
    winner = scorecard(0)
    fake = FakeGeminiClient(
        {
            "improved_qubo": {
                "candidate_id": "candidate_0",
                "agent_name": "agent_0",
                "linear_terms": {"x_0": 1.0},
                "quadratic_terms": {"x_0,x_1": -1.8},
                "constant": 0.0,
                "penalty_weight": 8.0,
                "notes": "retuned penalty weight",
            },
            "message": "retuned penalty weight to reduce constraint dominance",
        }
    )

    decision = RefinerAgent(fake).refine(winner)

    assert len(fake.prompts) == 1
    assert "re-tune penalty weights" in fake.prompts[0]
    assert decision.improved_qubo is not None
    assert decision.improved_qubo.penalty_weight == 8.0


def test_refiner_can_return_no_improvement_found() -> None:
    fake = FakeGeminiClient({"improved_qubo": None, "message": "no improvement found"})

    decision = RefinerAgent(fake).refine(scorecard(0))

    assert decision.improved_qubo is None
    assert decision.message == "no improvement found"


def test_refiner_rejects_changed_candidate_id() -> None:
    fake = FakeGeminiClient(
        {
            "improved_qubo": {
                "candidate_id": "different",
                "agent_name": "agent_0",
                "linear_terms": {"x_0": 1.0},
                "quadratic_terms": {},
                "constant": 0.0,
                "penalty_weight": 8.0,
                "notes": "invalid candidate id",
            },
            "message": "retuned penalty weight",
        }
    )

    with pytest.raises(LLMResponseError, match="changed the winning candidate_id"):
        RefinerAgent(fake).refine(scorecard(0))


def test_refiner_rejects_invalid_no_improvement_message() -> None:
    fake = FakeGeminiClient({"improved_qubo": None, "message": "try again later"})

    with pytest.raises(LLMResponseError, match="no improvement found"):
        RefinerAgent(fake).refine(scorecard(0))
