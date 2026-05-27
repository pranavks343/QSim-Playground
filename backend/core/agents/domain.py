"""Domain-specific QUBO formulation agent."""

from __future__ import annotations

from typing import ClassVar

from core.agents import register_agent
from core.agents.base import AgentContext, QUBOAgent


@register_agent
class DomainAgent(QUBOAgent):
    """Agent that uses known optimization formulations from the literature."""

    name: ClassVar[str] = "domain"
    strategy_description: ClassVar[str] = (
        "Select known quantum optimization formulations based on problem domain, citing "
        "Markowitz, Lucas (2014), or standard graph QUBO formulations when applicable."
    )
    prompt_file: ClassVar[str] = "domain.md"
    temperature: ClassVar[float] = 0.2

    def _build_user_message(self, context: AgentContext) -> str:
        tags = context.template_metadata.domain_tags if context.template_metadata else []
        if context.ir.name == "portfolio" or "finance" in tags:
            reference = "Markowitz QUBO formulation with cardinality constraint"
        elif "graph" in tags or context.ir.name == "max_cut":
            reference = "standard graph QUBO formulations"
        elif any(tag in {"routing", "scheduling"} for tag in tags):
            reference = 'Lucas (2014) "Ising formulations of many NP problems"'
        else:
            reference = "clean penalty formulation fallback"
        return (
            f"Use the domain-specific strategy on problem '{context.ir.name}'. Domain tags: "
            f"{tags}. Selected reference: {reference}. Cite the source by name in the "
            "justification. If the selected path is fallback, say no domain-specific reference "
            "matched and use a clean penalty formulation."
        )
