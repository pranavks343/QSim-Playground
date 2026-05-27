from __future__ import annotations

from collections.abc import Callable
from math import ceil, log2, sqrt
from typing import cast

from core.agents.base import AgentContext, QUBOAgent, QUBOOutput
from core.ir import ConstraintType, ObjectiveSense, ProblemIR
from core.templates import TemplateMetadata, get_template, list_templates
from infra.gemini import GeminiClient


def _variable_order(ir: ProblemIR) -> list[str]:
    return [variable.name for variable in ir.variables]


def _zero_matrix(size: int) -> list[list[float]]:
    return [[0.0 for _ in range(size)] for _ in range(size)]


def _objective_coefficients(ir: ProblemIR) -> list[float]:
    return [*ir.objective.linear_terms.values(), *ir.objective.quadratic_terms.values()]


def _penalty_weight(ir: ProblemIR, multiplier: float = 2.0) -> float:
    return multiplier * max((abs(value) for value in _objective_coefficients(ir)), default=1.0)


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


def _base_q_matrix(ir: ProblemIR, scale: float = 1.0) -> tuple[list[str], list[list[float]]]:
    variable_order = _variable_order(ir)
    matrix = _zero_matrix(len(variable_order))
    _add_objective(matrix, variable_order, ir, scale=scale)
    return variable_order, matrix


def penalty_output(ir: ProblemIR) -> QUBOOutput:
    variable_order, matrix = _base_q_matrix(ir)
    penalty_weight = _penalty_weight(ir)
    for constraint in ir.constraints:
        _add_squared_penalty(
            matrix,
            variable_order,
            constraint.linear_terms,
            constraint.rhs,
            penalty_weight,
        )
    return QUBOOutput(
        agent_name="penalty",
        strategy=f"penalty-based with lambda={penalty_weight:g}",
        q_matrix=matrix,
        variable_order=variable_order,
        parameters_used={"lambda": penalty_weight, "constraint_mode": "quadratic_penalty"},
        justification=(
            f"The penalty strategy uses lambda={penalty_weight:g}, twice the largest objective "
            "coefficient, so constraint violations are priced above single-term objective gains. "
            "This trades some objective scaling fidelity for stronger constraint satisfaction."
        ),
    )


def _extract_ir(prompt: str) -> ProblemIR:
    start = prompt.index("Problem IR:") + len("Problem IR:")
    end = prompt.index("User message:")
    return ProblemIR.from_json(prompt[start:end].strip().strip("`").strip())


class FakeGeminiClient:
    def __init__(self, generator: Callable[[ProblemIR], QUBOOutput]) -> None:
        self._generator = generator
        self.prompts: list[str] = []
        self.temperatures: list[float] = []

    async def generate_json(
        self,
        prompt: str,
        schema: type[QUBOOutput],
        temperature: float = 0.2,
    ) -> QUBOOutput:
        self.prompts.append(prompt)
        self.temperatures.append(temperature)
        return schema.model_validate(self._generator(_extract_ir(prompt)).model_dump())


def template_contexts() -> list[AgentContext]:
    metadata_by_name: dict[str, TemplateMetadata] = {
        metadata.name: metadata for metadata in list_templates()
    }
    return [
        AgentContext(ir=get_template(name), template_metadata=metadata_by_name[name])
        for name in ["portfolio", "max_cut", "knapsack"]
    ]


async def assert_agent_outputs_valid_qubos(
    agent_cls: type[QUBOAgent],
    generator: Callable[[ProblemIR], QUBOOutput],
    strategy_token: str,
    expected_temperature: float,
) -> list[QUBOOutput]:
    fake_client = FakeGeminiClient(generator)
    agent = agent_cls(cast(GeminiClient, fake_client))
    contexts = template_contexts()
    outputs = [await agent.formulate(context) for context in contexts]

    for context, output in zip(contexts, outputs, strict=True):
        assert output.agent_name == agent_cls.name
        assert len(output.q_matrix) == len(output.variable_order)
        assert output.estimated_qubits == len(output.variable_order)
        assert output.estimated_qubits >= len(context.ir.variables)
        assert strategy_token.lower() in output.justification.lower()
    assert fake_client.temperatures == [expected_temperature] * 3
    return outputs


def frobenius_norm_difference(left: QUBOOutput, right: QUBOOutput) -> float:
    size = max(len(left.q_matrix), len(right.q_matrix))

    def value(output: QUBOOutput, row: int, column: int) -> float:
        if row >= len(output.q_matrix) or column >= len(output.q_matrix):
            return 0.0
        return output.q_matrix[row][column]

    total = 0.0
    for row in range(size):
        for column in range(size):
            total += (value(left, row, column) - value(right, row, column)) ** 2
    return sqrt(total)


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
        parameters_used={
            "lambda": penalty_weight,
            "ancilla_qubits": ancilla_count,
            "ancilla_by_constraint": ancilla_by_constraint,
        },
        justification=(
            f"The slack strategy adds {ancilla_count} ancilla qubits to encode inequalities "
            "as equalities exactly. This matters when feasibility must be preserved, trading "
            "a larger qubit count for a cleaner constraint representation."
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
            "The graph strategy checks for canonical graph structure before encoding. It uses "
            "a natural max-cut graph form when detected, otherwise it rejects graph structure "
            "and emits a sparse graph-inspired QUBO."
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
            f"The decomposition strategy sees {len(ir.variables)} variables, so decomposition "
            "is unnecessary here. It keeps a monolithic QUBO while reserving boundary-variable "
            "metadata for larger overlapping subproblems."
        ),
    )


def domain_output(ir: ProblemIR) -> QUBOOutput:
    variable_order, matrix = _base_q_matrix(ir, scale=1.2)
    penalty_weight = _penalty_weight(ir, multiplier=2.5)
    for constraint in ir.constraints:
        _add_squared_penalty(
            matrix,
            variable_order,
            constraint.linear_terms,
            constraint.rhs,
            penalty_weight,
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
            f"The domain-specific strategy cites {reference} and adapts the formulation to "
            f"the {ir.name} template. It prefers known literature structure before falling "
            "back to a clean penalty formulation when no domain match exists."
        ),
    )
