from __future__ import annotations

from typing import cast

import pytest

from core.agents import get_agent, list_agents, register_agent
from core.agents.base import AgentContext, QUBOAgent, QUBOOutput
from core.templates import get_template
from infra.gemini import GeminiClient


def _valid_qubo_payload() -> dict[str, object]:
    return {
        "agent_name": "test-agent",
        "strategy": "direct symmetric matrix",
        "q_matrix": [[1.0, 0.5], [0.5, 2.0]],
        "variable_order": ["x_0", "x_1"],
        "parameters_used": {"lambda": 4.5},
        "justification": (
            "This formulation preserves the objective coefficients directly while keeping "
            "the matrix symmetric for stable downstream circuit generation."
        ),
    }


def test_qubo_output_rejects_non_symmetric_matrices() -> None:
    payload = _valid_qubo_payload()
    payload["q_matrix"] = [[1.0, 0.25], [0.5, 2.0]]

    with pytest.raises(ValueError, match="symmetric"):
        QUBOOutput.model_validate(payload)


def test_qubo_output_rejects_mismatched_variable_order_length() -> None:
    payload = _valid_qubo_payload()
    payload["variable_order"] = ["x_0"]

    with pytest.raises(ValueError, match="variable_order"):
        QUBOOutput.model_validate(payload)


def test_qubo_output_auto_computes_estimated_qubits() -> None:
    output = QUBOOutput.model_validate(_valid_qubo_payload())

    assert output.estimated_qubits == 2


class FakeGeminiClient:
    def __init__(self) -> None:
        self.prompt: str | None = None

    async def generate_json(
        self,
        prompt: str,
        schema: type[QUBOOutput],
        temperature: float = 0.2,
    ) -> QUBOOutput:
        del schema, temperature
        self.prompt = prompt
        return QUBOOutput.model_validate(_valid_qubo_payload())


class DummyAgent(QUBOAgent):
    name = "dummy"
    strategy_description = "Use the direct validated test strategy."
    prompt_file = "base_qubo.md"


@pytest.mark.asyncio
async def test_qubo_agent_formulate_loads_prompt_and_validates_output() -> None:
    fake_client = FakeGeminiClient()
    agent = DummyAgent(cast(GeminiClient, fake_client))
    context = AgentContext(ir=get_template("max_cut"), run_id="run-123")

    output = await agent.formulate(context)

    assert output.agent_name == "test-agent"
    assert fake_client.prompt is not None
    assert "run-123" in fake_client.prompt
    assert '"name":"max_cut"' in fake_client.prompt


def test_agent_registry_registers_and_lists_agents() -> None:
    class UniqueAgent(DummyAgent):
        name = "unique-test-agent"

    register_agent(UniqueAgent)

    assert get_agent("unique-test-agent") is UniqueAgent
    assert UniqueAgent in list_agents()

    with pytest.raises(ValueError, match="already registered"):
        register_agent(UniqueAgent)
