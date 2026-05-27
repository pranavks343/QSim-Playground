from __future__ import annotations

import pytest

from core.agents.decomp import DecompositionAgent

from .helpers import assert_agent_outputs_valid_qubos, decomp_output


@pytest.mark.asyncio
async def test_decomposition_agent_outputs_valid_qubos_on_templates() -> None:
    outputs = await assert_agent_outputs_valid_qubos(
        DecompositionAgent,
        decomp_output,
        strategy_token="decomposition",
        expected_temperature=0.3,
    )

    for output in outputs:
        assert output.parameters_used["decomposed"] is False
        assert output.parameters_used["subproblems"] == []
