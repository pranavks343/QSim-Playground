from __future__ import annotations

from itertools import product

import pytest

from core.ir import Constraint, ConstraintType, ObjectiveSense, ProblemIR
from core.templates import (
    TEMPLATES,
    TemplateMetadata,
    build_knapsack_template,
    build_max_cut_template,
    build_portfolio_template,
    get_template,
    list_templates,
)

EXPECTED_VALUES = {
    "portfolio": -0.5980000000000001,
    "max_cut": 20.3,
    "knapsack": 196.0,
}


def objective_value(problem: ProblemIR, assignment: dict[str, int]) -> float:
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


def constraint_is_satisfied(constraint: Constraint, assignment: dict[str, int]) -> bool:
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


def brute_force_reference_value(problem: ProblemIR) -> float:
    variable_names = [variable.name for variable in problem.variables]
    values: list[float] = []

    for bits in product((0, 1), repeat=len(variable_names)):
        assignment = dict(zip(variable_names, bits, strict=True))
        if all(
            constraint_is_satisfied(constraint, assignment) for constraint in problem.constraints
        ):
            values.append(objective_value(problem, assignment))

    if problem.objective.sense is ObjectiveSense.MINIMIZE:
        return min(values)
    return max(values)


@pytest.mark.parametrize("template_name", ["portfolio", "max_cut", "knapsack"])
def test_template_loads_without_validation_error(template_name: str) -> None:
    problem = get_template(template_name)

    assert ProblemIR.from_dict(problem.to_dict()).name == template_name


def test_list_templates_returns_exactly_three_entries() -> None:
    metadata = list_templates()

    assert [entry.name for entry in metadata] == ["portfolio", "max_cut", "knapsack"]
    assert len(metadata) == 3
    assert all(isinstance(entry, TemplateMetadata) for entry in metadata)


@pytest.mark.parametrize("metadata", list_templates())
def test_template_metadata_is_populated(metadata: TemplateMetadata) -> None:
    problem = get_template(metadata.name)

    assert metadata.display_name
    assert metadata.description
    assert metadata.difficulty in {"easy", "medium", "hard"}
    assert metadata.variable_count == len(problem.variables)
    assert metadata.constraint_count == len(problem.constraints)
    assert metadata.expected_optimal_value == pytest.approx(EXPECTED_VALUES[metadata.name])
    assert metadata.domain_tags


@pytest.mark.parametrize("template_name", ["portfolio", "max_cut", "knapsack"])
def test_brute_force_optimal_value_matches_known_reference(template_name: str) -> None:
    problem = get_template(template_name)

    assert brute_force_reference_value(problem) == pytest.approx(EXPECTED_VALUES[template_name])
    assert problem.metadata["expected_optimal_value"] == pytest.approx(
        EXPECTED_VALUES[template_name]
    )


def test_portfolio_metadata_contains_raw_inputs() -> None:
    problem = get_template("portfolio")

    assert len(problem.metadata["returns"]) == 6
    assert len(problem.metadata["covariance"]) == 6
    assert all(len(row) == 6 for row in problem.metadata["covariance"])
    assert problem.metadata["risk_weight"] == 1.0
    assert problem.metadata["return_weight"] == 2.0


def test_max_cut_metadata_contains_weighted_edges() -> None:
    problem = get_template("max_cut")

    assert len(problem.metadata["edges"]) == 12
    assert all(len(edge) == 3 for edge in problem.metadata["edges"])


def test_knapsack_metadata_contains_items_and_capacity() -> None:
    problem = get_template("knapsack")

    assert len(problem.metadata["items"]) == 10
    assert problem.metadata["capacity"] == 100.0


def test_template_builders_have_agent_context_docstrings() -> None:
    assert build_portfolio_template.__doc__ is not None
    assert "QUBO" in build_portfolio_template.__doc__
    assert build_max_cut_template.__doc__ is not None
    assert "QUBO" in build_max_cut_template.__doc__
    assert build_knapsack_template.__doc__ is not None
    assert "QUBO" in build_knapsack_template.__doc__


def test_get_template_nonexistent_raises_clear_key_error() -> None:
    with pytest.raises(KeyError, match="unknown template 'nonexistent'"):
        get_template("nonexistent")


def test_registry_keys_match_builders() -> None:
    assert set(TEMPLATES) == {"portfolio", "max_cut", "knapsack"}
