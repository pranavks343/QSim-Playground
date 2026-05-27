"""Slack-variable QUBO formulation agent."""

from __future__ import annotations

from math import ceil, log2
from typing import ClassVar

from core.agents import register_agent
from core.agents.base import AgentContext, QUBOAgent
from core.ir import ConstraintType


@register_agent
class SlackAgent(QUBOAgent):
    """Agent that introduces binary ancilla variables for exact inequalities."""

    name: ClassVar[str] = "slack"
    strategy_description: ClassVar[str] = (
        "Introduce binary slack variables for inequality constraints, then encode the resulting "
        "equalities as quadratic penalties."
    )
    prompt_file: ClassVar[str] = "slack.md"
    temperature: ClassVar[float] = 0.2

    def _build_user_message(self, context: AgentContext) -> str:
        ancilla_counts: dict[str, int] = {}
        for index, constraint in enumerate(context.ir.constraints):
            if constraint.type is ConstraintType.EQ:
                continue
            max_lhs = sum(abs(value) for value in constraint.linear_terms.values())
            bits = max(1, ceil(log2(max(1.0, abs(constraint.rhs) + max_lhs) + 1.0)))
            ancilla_counts[constraint.name or f"constraint_{index}"] = bits

        original_qubits = len(context.ir.variables)
        ancilla_qubits = sum(ancilla_counts.values())
        total_qubits = original_qubits + ancilla_qubits
        ratio = total_qubits / original_qubits
        return (
            f"Use the slack-variable strategy on problem '{context.ir.name}'. Original qubits: "
            f"{original_qubits}; estimated ancilla qubits: {ancilla_qubits}; total/original "
            f"ratio: {ratio:.3f}. For each Ax <= b constraint, introduce binary slack bits "
            "weighted by powers of two so Ax + slack = b, then penalize that equality. Include "
            f"this ancilla breakdown in parameters_used: {ancilla_counts}. Explain why exact "
            "encoding matters and why the added qubits are acceptable."
        )
