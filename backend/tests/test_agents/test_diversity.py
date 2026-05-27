from __future__ import annotations

from pathlib import Path

import pytest

from core.agents.decomp import DecompositionAgent
from core.agents.domain import DomainAgent
from core.agents.graph import GraphAgent
from core.agents.penalty import PenaltyAgent
from core.agents.slack import SlackAgent

from .helpers import (
    FakeGeminiClient,
    decomp_output,
    domain_output,
    frobenius_norm_difference,
    graph_output,
    penalty_output,
    slack_output,
    template_contexts,
)

PROMPTS_DIR = Path(__file__).parents[2] / "core" / "agents" / "prompts"


@pytest.mark.asyncio
async def test_agents_produce_differentiated_qubos_on_each_template() -> None:
    agent_specs = [
        (PenaltyAgent, penalty_output),
        (SlackAgent, slack_output),
        (GraphAgent, graph_output),
        (DecompositionAgent, decomp_output),
        (DomainAgent, domain_output),
    ]

    for context in template_contexts():
        outputs = [
            await agent_cls(FakeGeminiClient(generator)).formulate(context)  # type: ignore[arg-type]
            for agent_cls, generator in agent_specs
        ]

        for left_index, left_output in enumerate(outputs):
            for right_output in outputs[left_index + 1 :]:
                difference = frobenius_norm_difference(left_output, right_output)
                assert difference > 0.01, (
                    f"{context.ir.name}: {left_output.agent_name} and "
                    f"{right_output.agent_name} produced near-identical QUBOs"
                )


def test_specialist_prompts_include_required_editable_sections() -> None:
    for prompt_name in ["penalty.md", "slack.md", "graph.md", "decomp.md", "domain.md"]:
        prompt = (PROMPTS_DIR / prompt_name).read_text(encoding="utf-8")

        for section in ["# Role", "# Strategy", "# Output Format", "# Examples"]:
            assert section in prompt
        assert "$problem_ir" in prompt
        assert "$user_message" in prompt
