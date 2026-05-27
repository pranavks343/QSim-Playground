"""Deterministic local pipeline factories for CLI runs without LLM credentials."""

from __future__ import annotations

from collections.abc import Callable
from math import ceil, log2
from typing import Literal

from core.agents.base import AgentContext, QUBOAgent, QUBOOutput
from core.agents.critic import CriticAgent, CriticVerdict
from core.agents.refiner import RefinedQUBO, RefinerAgent, no_improvement_refinement
from core.evaluator import ComparisonTable, Scorecard
from core.ir import ConstraintType, ObjectiveSense, ProblemIR
from core.orchestrator import AgentFactory, CriticFactory, RefinerFactory

QUBOGenerator = Callable[[ProblemIR], QUBOOutput]


class LocalQUBOAgent(QUBOAgent):
    """QUBO agent backed by deterministic local formulations."""

    name = "local"
    strategy_description = "deterministic local formulation"
    prompt_file = "base_qubo.md"

    def __init__(self, agent_name: str, generator: QUBOGenerator) -> None:
        self._agent_name = agent_name
        self._generator = generator

    async def formulate(self, context: AgentContext) -> QUBOOutput:
        return self._generator(context.ir)


class LocalCriticAgent(CriticAgent):
    """Deterministic critic that explains the sorted scorecard table."""

    def __init__(self) -> None:
        pass

    async def judge(self, comparison_table: ComparisonTable) -> CriticVerdict:
        top = comparison_table.scorecards[0]
        runner_up = comparison_table.scorecards[1]
        gap = top.composite_score - runner_up.composite_score
        confidence: Literal["high", "medium", "low"] = (
            "high" if gap >= 1.0 else "low" if gap < 0.25 else "medium"
        )
        rejected = [scorecard.agent_name for scorecard in comparison_table.scorecards[2:]]
        return CriticVerdict(
            winner_agent=top.agent_name,
            runner_up_agent=runner_up.agent_name,
            rejected_agents=rejected,
            rationale=(
                f"{top.agent_name} wins with composite_score={top.composite_score:g}, "
                f"qubit_count={top.qubit_count}, sparsity={top.sparsity:g}, "
                f"condition_number={top.condition_number:g}, and "
                f"penalty_sensitivity={top.penalty_sensitivity:g}. "
                f"{runner_up.agent_name} is runner-up with composite_score="
                f"{runner_up.composite_score:g}; rejected agents are "
                f"{', '.join(rejected) if rejected else 'none'}."
            ),
            confidence=confidence,
        )


class LocalRefinerAgent(RefinerAgent):
    """Deterministic refiner that keeps the winning QUBO when no safe change is proven."""

    def __init__(self) -> None:
        pass

    async def refine(
        self,
        winner_qubo: QUBOOutput,
        scorecard: Scorecard,
        *,
        with_hints: bool = False,
    ) -> RefinedQUBO:
        del scorecard, with_hints
        return no_improvement_refinement(winner_qubo)


def local_agent_factories() -> dict[str, AgentFactory]:
    """Return deterministic factories for the five formulation agents."""

    generators: dict[str, QUBOGenerator] = {
        "penalty": penalty_output,
        "slack": slack_output,
        "graph": graph_output,
        "decomp": decomp_output,
        "domain": domain_output,
    }
    factories: dict[str, AgentFactory] = {}
    for agent_name, generator in generators.items():

        def build_agent(
            name: str = agent_name,
            selected_generator: QUBOGenerator = generator,
        ) -> QUBOAgent:
            return LocalQUBOAgent(name, selected_generator)

        factories[agent_name] = build_agent
    return factories


def local_critic_factory() -> CriticFactory:
    """Return a deterministic critic factory."""

    return lambda: LocalCriticAgent()


def local_refiner_factory() -> RefinerFactory:
    """Return a deterministic refiner factory."""

    return lambda: LocalRefinerAgent()


def penalty_output(ir: ProblemIR) -> QUBOOutput:
    variable_order, matrix = _base_q_matrix(ir)
    penalty_weight = _penalty_weight(ir)
    for constraint in ir.constraints:
        _add_squared_penalty(
            matrix, variable_order, constraint.linear_terms, constraint.rhs, penalty_weight
        )
    return QUBOOutput(
        agent_name="penalty",
        strategy=f"penalty-based with lambda={penalty_weight:g}",
        q_matrix=matrix,
        variable_order=variable_order,
        parameters_used={"lambda": penalty_weight},
        justification=(
            f"The penalty strategy uses lambda={penalty_weight:g}, twice the largest objective "
            "coefficient, to price feasibility above one-term objective gains."
        ),
    )


def slack_output(ir: ProblemIR) -> QUBOOutput:
    variable_order = _variable_order(ir)
    ancilla_by_constraint: dict[str, list[str]] = {}
    for constraint_index, constraint in enumerate(ir.constraints):
        if constraint.type is ConstraintType.EQ:
            continue
        max_lhs = sum(abs(value) for value in constraint.linear_terms.values())
        slack_bits = max(1, ceil(log2(max(1.0, abs(constraint.rhs) + max_lhs) + 1.0)))
        names = [f"s_{constraint_index}_{bit}" for bit in range(slack_bits)]
        ancilla_by_constraint[constraint.name or str(constraint_index)] = names
        variable_order.extend(names)

    matrix = _zero_matrix(len(variable_order))
    _add_objective(matrix, variable_order, ir, scale=1.05)
    penalty_weight = _penalty_weight(ir, multiplier=3.0)
    for constraint_index, constraint in enumerate(ir.constraints):
        terms = dict(constraint.linear_terms)
        key = constraint.name or str(constraint_index)
        for bit, slack_name in enumerate(ancilla_by_constraint.get(key, [])):
            terms[slack_name] = 2.0**bit
        _add_squared_penalty(matrix, variable_order, terms, constraint.rhs, penalty_weight)

    ancilla_count = len(variable_order) - len(ir.variables)
    return QUBOOutput(
        agent_name="slack",
        strategy=f"slack-variable exact encoding with {ancilla_count} ancilla qubits",
        q_matrix=matrix,
        variable_order=variable_order,
        parameters_used={"lambda": penalty_weight, "ancilla_qubits": ancilla_count},
        justification=(
            f"The slack strategy adds {ancilla_count} ancilla qubits for exact inequality "
            "encoding, trading search-space size for feasibility clarity."
        ),
    )


def graph_output(ir: ProblemIR) -> QUBOOutput:
    variable_order, matrix = _base_q_matrix(ir, scale=0.35)
    if ir.name == "max_cut" and "edges" in ir.metadata:
        matrix = _zero_matrix(len(variable_order))
        index_by_name = {name: index for index, name in enumerate(variable_order)}
        for left, right, weight in ir.metadata["edges"]:
            left_index = index_by_name[f"x_{left}"]
            right_index = index_by_name[f"x_{right}"]
            matrix[left_index][right_index] -= float(weight)
            matrix[right_index][left_index] -= float(weight)
    return QUBOOutput(
        agent_name="graph",
        strategy="graph canonical encoding",
        q_matrix=matrix,
        variable_order=variable_order,
        parameters_used={"detected_graph_problem": ir.name == "max_cut"},
        justification=(
            "The graph strategy uses canonical graph structure when present and otherwise "
            "keeps a sparse graph-inspired QUBO without forcing a false graph model."
        ),
    )


def decomp_output(ir: ProblemIR) -> QUBOOutput:
    variable_order, matrix = _base_q_matrix(ir, scale=0.9)
    for index in range(len(variable_order)):
        matrix[index][index] += 0.01 * (index + 1)
    return QUBOOutput(
        agent_name="decomp",
        strategy="monolithic decomposition-aware QUBO",
        q_matrix=matrix,
        variable_order=variable_order,
        parameters_used={"decomposed": len(ir.variables) > 20, "subproblems": []},
        justification=(
            f"The decomposition strategy sees {len(ir.variables)} variables, so it keeps a "
            "monolithic QUBO and avoids unnecessary boundary-variable reconciliation."
        ),
    )


def domain_output(ir: ProblemIR) -> QUBOOutput:
    variable_order, matrix = _base_q_matrix(ir, scale=1.2)
    penalty_weight = _penalty_weight(ir, multiplier=2.5)
    for constraint in ir.constraints:
        _add_squared_penalty(
            matrix, variable_order, constraint.linear_terms, constraint.rhs, penalty_weight
        )
    reference = "Markowitz QUBO formulation" if ir.name == "portfolio" else "Lucas (2014)"
    if ir.name == "max_cut":
        reference = "standard graph QUBO formulations"
    return QUBOOutput(
        agent_name="domain",
        strategy=f"domain-specific formulation citing {reference}",
        q_matrix=matrix,
        variable_order=variable_order,
        parameters_used={"reference": reference, "lambda": penalty_weight},
        justification=(
            f"The domain-specific strategy cites {reference} and adapts the QUBO to the "
            f"{ir.name} template before falling back to generic penalties."
        ),
    )


def _variable_order(ir: ProblemIR) -> list[str]:
    return [variable.name for variable in ir.variables]


def _zero_matrix(size: int) -> list[list[float]]:
    return [[0.0 for _ in range(size)] for _ in range(size)]


def _objective_coefficients(ir: ProblemIR) -> list[float]:
    return [*ir.objective.linear_terms.values(), *ir.objective.quadratic_terms.values()]


def _penalty_weight(ir: ProblemIR, multiplier: float = 2.0) -> float:
    return multiplier * max((abs(value) for value in _objective_coefficients(ir)), default=1.0)


def _base_q_matrix(ir: ProblemIR, scale: float = 1.0) -> tuple[list[str], list[list[float]]]:
    variable_order = _variable_order(ir)
    matrix = _zero_matrix(len(variable_order))
    _add_objective(matrix, variable_order, ir, scale=scale)
    return variable_order, matrix


def _add_objective(
    matrix: list[list[float]],
    variable_order: list[str],
    ir: ProblemIR,
    scale: float = 1.0,
) -> None:
    sign = -1.0 if ir.objective.sense is ObjectiveSense.MAXIMIZE else 1.0
    index_by_name = {name: index for index, name in enumerate(variable_order)}
    for name, coefficient in ir.objective.linear_terms.items():
        matrix[index_by_name[name]][index_by_name[name]] += sign * scale * coefficient
    for (left, right), coefficient in ir.objective.quadratic_terms.items():
        left_index = index_by_name[left]
        right_index = index_by_name[right]
        value = sign * scale * coefficient
        matrix[left_index][right_index] += value
        if left_index != right_index:
            matrix[right_index][left_index] += value


def _add_squared_penalty(
    matrix: list[list[float]],
    variable_order: list[str],
    linear_terms: dict[str, float],
    rhs: float,
    penalty_weight: float,
) -> None:
    index_by_name = {name: index for index, name in enumerate(variable_order)}
    terms = list(linear_terms.items())
    for name, coefficient in terms:
        index = index_by_name[name]
        matrix[index][index] += penalty_weight * (
            coefficient * coefficient - 2.0 * rhs * coefficient
        )
    for left_position, (left_name, left_coefficient) in enumerate(terms):
        for right_name, right_coefficient in terms[left_position + 1 :]:
            left_index = index_by_name[left_name]
            right_index = index_by_name[right_name]
            value = penalty_weight * left_coefficient * right_coefficient
            matrix[left_index][right_index] += value
            matrix[right_index][left_index] += value
