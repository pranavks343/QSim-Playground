from __future__ import annotations

import pytest

from core.agents.domain import DomainAgent

from .helpers import assert_agent_outputs_valid_qubos, domain_output


@pytest.mark.asyncio
async def test_domain_agent_outputs_valid_qubos_on_templates() -> None:
    outputs = await assert_agent_outputs_valid_qubos(
        DomainAgent,
        domain_output,
        strategy_token="domain",
        expected_temperature=0.2,
    )

    assert "Markowitz" in outputs[0].justification
    assert "standard graph QUBO" in outputs[1].justification
    assert "Lucas (2014)" in outputs[2].justification
