from __future__ import annotations

import pytest

from core.agents.graph import GraphAgent

from .helpers import assert_agent_outputs_valid_qubos, graph_output


@pytest.mark.asyncio
async def test_graph_agent_outputs_valid_qubos_on_templates() -> None:
    outputs = await assert_agent_outputs_valid_qubos(
        GraphAgent,
        graph_output,
        strategy_token="graph",
        expected_temperature=0.3,
    )

    max_cut_output = outputs[1]
    assert max_cut_output.parameters_used["detected_graph_problem"] is True
    assert any(value < 0 for row in max_cut_output.q_matrix for value in row)
