"""Penalty-based QUBO formulation agent."""

from __future__ import annotations

from typing import ClassVar

from core.agents import register_agent
from core.agents.base import AgentContext, QUBOAgent


@register_agent
class PenaltyAgent(QUBOAgent):
    """Agent that converts constraints into quadratic penalty terms."""

    name: ClassVar[str] = "penalty"
    strategy_description: ClassVar[str] = (
        "Convert every constraint into quadratic penalties added to the objective, using "
        "lambda = 2 * max(abs(objective coefficient))."
    )
    prompt_file: ClassVar[str] = "penalty.md"
    temperature: ClassVar[float] = 0.2

    def _build_user_message(self, context: AgentContext) -> str:
        objective_coefficients = [
            *context.ir.objective.linear_terms.values(),
            *context.ir.objective.quadratic_terms.values(),
        ]
        max_coefficient = max((abs(value) for value in objective_coefficients), default=1.0)
        penalty_weight = 2.0 * max_coefficient
        constraint_names = [
            constraint.name or f"constraint_{index}"
            for index, constraint in enumerate(context.ir.constraints)
        ]
        return (
            f"Use the penalty strategy on problem '{context.ir.name}'. Compute lambda as "
            f"2 * max(abs(objective coefficient)) = {penalty_weight:g}. Convert equality "
            "constraints with lambda * (A x - b)^2 and inequality constraints with the "
            "specified slack-free quadratic approximation. Mention these constraints: "
            f"{constraint_names or ['none']}. Justification must include the lambda value, "
            "why it is appropriate, and the tradeoff between objective quality and "
            "constraint satisfaction."
        )
