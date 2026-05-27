from __future__ import annotations

import pytest

from core.agents.penalty import PenaltyAgent

from .helpers import assert_agent_outputs_valid_qubos, penalty_output


@pytest.mark.asyncio
async def test_penalty_agent_outputs_valid_qubos_on_templates() -> None:
    await assert_agent_outputs_valid_qubos(
        PenaltyAgent,
        penalty_output,
        strategy_token="penalty",
        expected_temperature=0.2,
    )
