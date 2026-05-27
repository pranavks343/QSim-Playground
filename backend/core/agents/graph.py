"""Graph-encoding QUBO formulation agent."""

from __future__ import annotations

from typing import ClassVar

from core.agents import register_agent
from core.agents.base import AgentContext, QUBOAgent


@register_agent
class GraphAgent(QUBOAgent):
    """Agent that prefers canonical graph-problem encodings."""

    name: ClassVar[str] = "graph"
    strategy_description: ClassVar[str] = (
        "Detect canonical graph problems such as max-cut, vertex cover, independent set, and "
        "graph coloring; use graph-native QUBO encodings when available."
    )
    prompt_file: ClassVar[str] = "graph.md"
    temperature: ClassVar[float] = 0.3

    def _build_user_message(self, context: AgentContext) -> str:
        tags = context.template_metadata.domain_tags if context.template_metadata else []
        has_edges = "edges" in context.ir.metadata
        detected = context.ir.name == "max_cut" or "graph" in tags or has_edges
        if detected:
            graph_message = (
                "Graph structure detected. For max-cut-like problems, use the standard "
                "(1 - x_i * x_j) edge formulation and explain why this is natural."
            )
        else:
            graph_message = (
                "No canonical graph structure is detected. Produce a sparse QUBO and explicitly "
                "state that graph form does not apply."
            )
        return (
            f"Use the graph encoding strategy on problem '{context.ir.name}'. Domain tags: {tags}. "
            f"Metadata contains edges: {has_edges}. {graph_message} Justification must name the "
            "graph problem detected or explain why graph encoding was rejected."
        )
