"""Hardcoded optimization problem templates."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from itertools import combinations, product
from typing import Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from core.ir import (
    Constraint,
    ConstraintType,
    Objective,
    ObjectiveSense,
    ProblemIR,
    Variable,
    VariableType,
)

TemplateDifficulty = Literal["easy", "medium", "hard"]

PORTFOLIO_RETURNS = [0.08, 0.11, 0.13, 0.09, 0.15, 0.12]
PORTFOLIO_COVARIANCE = [
    [0.021, 0.004, 0.006, 0.003, 0.008, 0.005],
    [0.004, 0.030, 0.009, 0.005, 0.011, 0.007],
    [0.006, 0.009, 0.045, 0.006, 0.014, 0.010],
    [0.003, 0.005, 0.006, 0.018, 0.007, 0.004],
    [0.008, 0.011, 0.014, 0.007, 0.050, 0.012],
    [0.005, 0.007, 0.010, 0.004, 0.012, 0.035],
]
PORTFOLIO_RISK_WEIGHT = 1.0
PORTFOLIO_RETURN_WEIGHT = 2.0

MAX_CUT_EDGES = [
    (0, 1, 2.0),
    (1, 2, 1.5),
    (2, 3, 2.5),
    (3, 4, 1.0),
    (4, 5, 2.2),
    (5, 6, 1.8),
    (6, 7, 2.4),
    (7, 0, 1.7),
    (0, 4, 2.1),
    (1, 5, 1.3),
    (2, 6, 2.6),
    (3, 7, 1.9),
]


class KnapsackItem(TypedDict):
    """Hardcoded item data for the Knapsack template."""

    name: str
    weight: float
    value: float


KNAPSACK_ITEMS: list[KnapsackItem] = [
    {"name": "calibrator", "weight": 12.0, "value": 24.0},
    {"name": "sensor", "weight": 18.0, "value": 32.0},
    {"name": "optimizer", "weight": 25.0, "value": 50.0},
    {"name": "compiler", "weight": 9.0, "value": 18.0},
    {"name": "sampler", "weight": 30.0, "value": 60.0},
    {"name": "validator", "weight": 14.0, "value": 27.0},
    {"name": "router", "weight": 21.0, "value": 38.0},
    {"name": "cache", "weight": 7.0, "value": 13.0},
    {"name": "monitor", "weight": 16.0, "value": 31.0},
    {"name": "exporter", "weight": 11.0, "value": 20.0},
]
KNAPSACK_CAPACITY = 100.0


class TemplateMetadata(BaseModel):
    """Catalog metadata for a hardcoded optimization template."""

    model_config = ConfigDict(extra="forbid")

    name: str
    display_name: str
    description: str
    difficulty: TemplateDifficulty
    variable_count: int = Field(ge=1)
    constraint_count: int = Field(ge=0)
    expected_optimal_value: float | None
    domain_tags: list[str] = Field(default_factory=list)


def _binary_variables(count: int) -> list[Variable]:
    return [Variable(name=f"x_{index}", type=VariableType.BINARY) for index in range(count)]


def _objective_value(problem: ProblemIR, assignment: dict[str, int]) -> float:
    value = problem.objective.constant
    value += sum(
        coefficient * assignment[name]
        for name, coefficient in problem.objective.linear_terms.items()
    )
    value += sum(
        coefficient * assignment[left] * assignment[right]
        for (left, right), coefficient in problem.objective.quadratic_terms.items()
    )
    return value


def _constraint_is_satisfied(constraint: Constraint, assignment: dict[str, int]) -> bool:
    lhs = sum(
        coefficient * assignment[name] for name, coefficient in constraint.linear_terms.items()
    )
    lhs += sum(
        coefficient * assignment[left] * assignment[right]
        for (left, right), coefficient in constraint.quadratic_terms.items()
    )

    if constraint.type is ConstraintType.LEQ:
        return lhs <= constraint.rhs
    if constraint.type is ConstraintType.GEQ:
        return lhs >= constraint.rhs
    return lhs == constraint.rhs


def _is_feasible(problem: ProblemIR, assignment: dict[str, int]) -> bool:
    return all(
        _constraint_is_satisfied(constraint, assignment) for constraint in problem.constraints
    )


def _assignments(variable_names: Iterable[str]) -> Iterable[dict[str, int]]:
    names = list(variable_names)
    for values in product((0, 1), repeat=len(names)):
        yield dict(zip(names, values, strict=True))


def _brute_force_optimal_value(problem: ProblemIR) -> float:
    variable_names = [variable.name for variable in problem.variables]
    best_value: float | None = None

    for assignment in _assignments(variable_names):
        if not _is_feasible(problem, assignment):
            continue

        value = _objective_value(problem, assignment)
        if best_value is None:
            best_value = value
        elif problem.objective.sense is ObjectiveSense.MINIMIZE:
            best_value = min(best_value, value)
        else:
            best_value = max(best_value, value)

    if best_value is None:
        raise ValueError(f"template {problem.name} has no feasible assignments")

    return best_value


def _portfolio_objective_terms() -> tuple[dict[str, float], dict[tuple[str, str], float]]:
    linear_terms: dict[str, float] = {}
    quadratic_terms: dict[tuple[str, str], float] = {}

    for index, expected_return in enumerate(PORTFOLIO_RETURNS):
        variable_name = f"x_{index}"
        linear_terms[variable_name] = (
            PORTFOLIO_RISK_WEIGHT * PORTFOLIO_COVARIANCE[index][index]
            - PORTFOLIO_RETURN_WEIGHT * expected_return
        )

    for left, right in combinations(range(len(PORTFOLIO_RETURNS)), 2):
        quadratic_terms[(f"x_{left}", f"x_{right}")] = (
            2.0 * PORTFOLIO_RISK_WEIGHT * PORTFOLIO_COVARIANCE[left][right]
        )

    return linear_terms, quadratic_terms


def _max_cut_objective_terms() -> tuple[dict[str, float], dict[tuple[str, str], float]]:
    linear_terms = {f"x_{index}": 0.0 for index in range(8)}
    quadratic_terms: dict[tuple[str, str], float] = {}

    for left, right, weight in MAX_CUT_EDGES:
        left_name = f"x_{left}"
        right_name = f"x_{right}"
        linear_terms[left_name] += weight
        linear_terms[right_name] += weight
        key = (left_name, right_name) if left_name <= right_name else (right_name, left_name)
        quadratic_terms[key] = quadratic_terms.get(key, 0.0) - 2.0 * weight

    return linear_terms, quadratic_terms


def _build_portfolio_problem() -> ProblemIR:
    linear_terms, quadratic_terms = _portfolio_objective_terms()
    return ProblemIR(
        name="portfolio",
        description="Select exactly three assets while trading off expected return against risk.",
        variables=_binary_variables(6),
        objective=Objective(
            sense=ObjectiveSense.MINIMIZE,
            linear_terms=linear_terms,
            quadratic_terms=quadratic_terms,
        ),
        constraints=[
            Constraint(
                name="select_exactly_three_assets",
                linear_terms={f"x_{index}": 1.0 for index in range(6)},
                type=ConstraintType.EQ,
                rhs=3.0,
            )
        ],
        metadata={
            "template": "portfolio",
            "returns": PORTFOLIO_RETURNS,
            "covariance": PORTFOLIO_COVARIANCE,
            "risk_weight": PORTFOLIO_RISK_WEIGHT,
            "return_weight": PORTFOLIO_RETURN_WEIGHT,
        },
    )


def _build_max_cut_problem() -> ProblemIR:
    linear_terms, quadratic_terms = _max_cut_objective_terms()
    return ProblemIR(
        name="max_cut",
        description="Partition a weighted graph to maximize the total cut edge weight.",
        variables=_binary_variables(8),
        objective=Objective(
            sense=ObjectiveSense.MAXIMIZE,
            linear_terms=linear_terms,
            quadratic_terms=quadratic_terms,
        ),
        constraints=[],
        metadata={"template": "max_cut", "edges": MAX_CUT_EDGES},
    )


def _build_knapsack_problem() -> ProblemIR:
    return ProblemIR(
        name="knapsack",
        description="Choose a high-value subset of items without exceeding capacity.",
        variables=_binary_variables(10),
        objective=Objective(
            sense=ObjectiveSense.MAXIMIZE,
            linear_terms={f"x_{index}": item["value"] for index, item in enumerate(KNAPSACK_ITEMS)},
        ),
        constraints=[
            Constraint(
                name="capacity",
                linear_terms={
                    f"x_{index}": item["weight"] for index, item in enumerate(KNAPSACK_ITEMS)
                },
                type=ConstraintType.LEQ,
                rhs=KNAPSACK_CAPACITY,
            )
        ],
        metadata={
            "template": "knapsack",
            "items": KNAPSACK_ITEMS,
            "capacity": KNAPSACK_CAPACITY,
        },
    )


PORTFOLIO_EXPECTED_OPTIMAL_VALUE = _brute_force_optimal_value(_build_portfolio_problem())
MAX_CUT_EXPECTED_OPTIMAL_VALUE = _brute_force_optimal_value(_build_max_cut_problem())
KNAPSACK_EXPECTED_OPTIMAL_VALUE = _brute_force_optimal_value(_build_knapsack_problem())


def build_portfolio_template() -> ProblemIR:
    """Build a portfolio selection problem.

    The template represents choosing exactly three assets from six candidates while balancing
    return against covariance-based risk. It is interesting for QUBO formulation because the
    equality constraint needs a penalty and the dense covariance matrix creates quadratic
    interactions between most asset pairs. Penalty-based strategies with calibrated constraint
    weights should perform well, especially if they preserve the original risk-return scale.
    """

    problem = _build_portfolio_problem()
    problem.metadata["expected_optimal_value"] = PORTFOLIO_EXPECTED_OPTIMAL_VALUE
    return problem


def build_max_cut_template() -> ProblemIR:
    """Build a weighted Max-Cut graph partitioning problem.

    The template represents splitting eight graph nodes into two partitions to maximize the
    weight of edges crossing the partition boundary. It is interesting for QUBO formulation
    because the objective is naturally quadratic and unconstrained, so agents can focus on
    preserving sign conventions and graph structure. Direct Ising or native QUBO strategies
    should perform well because no feasibility penalties are required.
    """

    problem = _build_max_cut_problem()
    problem.metadata["expected_optimal_value"] = MAX_CUT_EXPECTED_OPTIMAL_VALUE
    return problem


def build_knapsack_template() -> ProblemIR:
    """Build a binary knapsack selection problem.

    The template represents choosing a subset of ten items with maximum value under a fixed
    capacity budget. It is interesting for QUBO formulation because the inequality constraint
    must be encoded with slack variables or a penalty, and poor penalty scaling can overwhelm
    item values. Slack-variable or adaptive-penalty strategies should perform well for this
    small but realistic constrained selection problem.
    """

    problem = _build_knapsack_problem()
    problem.metadata["expected_optimal_value"] = KNAPSACK_EXPECTED_OPTIMAL_VALUE
    return problem


TEMPLATES: dict[str, Callable[[], ProblemIR]] = {
    "portfolio": build_portfolio_template,
    "max_cut": build_max_cut_template,
    "knapsack": build_knapsack_template,
}

_TEMPLATE_METADATA: dict[str, TemplateMetadata] = {
    "portfolio": TemplateMetadata(
        name="portfolio",
        display_name="Portfolio Optimization",
        description="Select exactly three assets while balancing expected return and risk.",
        difficulty="medium",
        variable_count=6,
        constraint_count=1,
        expected_optimal_value=PORTFOLIO_EXPECTED_OPTIMAL_VALUE,
        domain_tags=["finance", "selection", "quadratic"],
    ),
    "max_cut": TemplateMetadata(
        name="max_cut",
        display_name="Max-Cut",
        description="Partition a weighted graph to maximize cut edge weight.",
        difficulty="easy",
        variable_count=8,
        constraint_count=0,
        expected_optimal_value=MAX_CUT_EXPECTED_OPTIMAL_VALUE,
        domain_tags=["graph", "partitioning", "unconstrained"],
    ),
    "knapsack": TemplateMetadata(
        name="knapsack",
        display_name="Knapsack",
        description="Select the highest-value item subset within a capacity limit.",
        difficulty="medium",
        variable_count=10,
        constraint_count=1,
        expected_optimal_value=KNAPSACK_EXPECTED_OPTIMAL_VALUE,
        domain_tags=["selection", "capacity", "integer-programming"],
    ),
}


def get_template(name: str) -> ProblemIR:
    """Return a fresh ProblemIR for a registered template name."""

    try:
        return TEMPLATES[name]()
    except KeyError as exc:
        available = ", ".join(sorted(TEMPLATES))
        raise KeyError(f"unknown template '{name}'. Available templates: {available}") from exc


def list_templates() -> list[TemplateMetadata]:
    """Return metadata for all registered templates."""

    return [_TEMPLATE_METADATA[name] for name in TEMPLATES]
