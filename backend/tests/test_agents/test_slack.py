from __future__ import annotations

import pytest

from core.agents.slack import SlackAgent

from .helpers import assert_agent_outputs_valid_qubos, slack_output


@pytest.mark.asyncio
async def test_slack_agent_outputs_valid_qubos_on_templates() -> None:
    outputs = await assert_agent_outputs_valid_qubos(
        SlackAgent,
        slack_output,
        strategy_token="slack",
        expected_temperature=0.2,
    )

    knapsack_output = outputs[2]
    assert knapsack_output.estimated_qubits is not None
    assert knapsack_output.estimated_qubits > 10
    assert knapsack_output.parameters_used["ancilla_qubits"] > 0
