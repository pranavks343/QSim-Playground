"""Decomposition-aware QUBO formulation agent."""

from __future__ import annotations

from typing import ClassVar

from core.agents import register_agent
from core.agents.base import AgentContext, QUBOAgent


@register_agent
class DecompositionAgent(QUBOAgent):
    """Agent that decomposes large problems into overlapping subproblems."""

    name: ClassVar[str] = "decomp"
    strategy_description: ClassVar[str] = (
        "Decompose problems with more than 20 variables into overlapping subproblems; keep "
        "small problems monolithic and explain why decomposition is unnecessary."
    )
    prompt_file: ClassVar[str] = "decomp.md"
    temperature: ClassVar[float] = 0.3

    def _build_user_message(self, context: AgentContext) -> str:
        variable_count = len(context.ir.variables)
        if variable_count > 20:
            decision = (
                "Decompose into overlapping subproblems and include subproblems as serialized "
                "QUBOOutput objects inside parameters_used['subproblems']."
            )
        else:
            decision = (
                "Do not decompose. Produce a monolithic QUBO and state that decomposition is "
                "unnecessary at this size."
            )
        return (
            f"Use the decomposition strategy on problem '{context.ir.name}'. Variable count: "
            f"{variable_count}. {decision} Justification must include the variable count, the "
            "decomposition decision, and the boundary-variable strategy."
        )
