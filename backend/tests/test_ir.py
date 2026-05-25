from __future__ import annotations

import copy
import json
from typing import Any

import pytest
from pydantic import ValidationError

from core.ir import ConstraintType, ObjectiveSense, ProblemIR, VariableType


def portfolio_data() -> dict[str, Any]:
    return {
        "name": "portfolio",
        "description": "Minimal portfolio allocation problem.",
        "variables": [
            {"name": "asset_a", "type": "binary"},
            {"name": "asset_b", "type": "binary"},
        ],
        "objective": {
            "sense": "maximize",
            "linear_terms": {"asset_a": 1.2, "asset_b": 0.9},
            "quadratic_terms": {"asset_a,asset_b": -0.1},
            "constant": 0.0,
        },
        "constraints": [
            {
                "name": "budget",
                "linear_terms": {"asset_a": 1.0, "asset_b": 1.0},
                "quadratic_terms": {},
                "type": "<=",
                "rhs": 1.0,
            }
        ],
        "metadata": {"template": "portfolio"},
    }


def max_cut_data() -> dict[str, Any]:
    return {
        "name": "max_cut",
        "description": "Minimal two-node Max-Cut problem.",
        "variables": [
            {"name": "x0", "type": "binary"},
            {"name": "x1", "type": "binary"},
        ],
        "objective": {
            "sense": "maximize",
            "linear_terms": {"x0": 1.0, "x1": 1.0},
            "quadratic_terms": {"x0,x1": -2.0},
            "constant": 0.0,
        },
        "constraints": [],
        "metadata": {"template": "max_cut"},
    }


def knapsack_data() -> dict[str, Any]:
    return {
        "name": "knapsack",
        "description": "Minimal capacity-constrained knapsack problem.",
        "variables": [
            {"name": "item_0", "type": "binary", "lower_bound": 0.0, "upper_bound": 1.0},
            {"name": "item_1", "type": "binary", "lower_bound": 0.0, "upper_bound": 1.0},
        ],
        "objective": {
            "sense": "maximize",
            "linear_terms": {"item_0": 4.0, "item_1": 6.0},
            "quadratic_terms": {},
            "constant": 0.0,
        },
        "constraints": [
            {
                "name": "capacity",
                "linear_terms": {"item_0": 2.0, "item_1": 3.0},
                "quadratic_terms": {},
                "type": "<=",
                "rhs": 3.0,
            }
        ],
        "metadata": {"template": "knapsack"},
    }


def canonical_json(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


@pytest.mark.parametrize("problem_data", [portfolio_data(), max_cut_data(), knapsack_data()])
def test_valid_template_data_loads(problem_data: dict[str, Any]) -> None:
    problem = ProblemIR.from_dict(problem_data)

    assert problem.name == problem_data["name"]
    assert len(problem.variables) >= 1


def test_enums_use_stable_json_values() -> None:
    assert VariableType.BINARY.value == "binary"
    assert ConstraintType.LEQ.value == "<="
    assert ObjectiveSense.MAXIMIZE.value == "maximize"


def test_duplicate_variable_names_raise_validation_error() -> None:
    data = portfolio_data()
    data["variables"][1]["name"] = "asset_a"

    with pytest.raises(ValidationError, match="variable names must be unique"):
        ProblemIR.from_dict(data)


def test_objective_references_undefined_variable_raise_validation_error() -> None:
    data = portfolio_data()
    data["objective"]["linear_terms"]["missing_asset"] = 2.0

    with pytest.raises(ValidationError, match="objective references undefined variables"):
        ProblemIR.from_dict(data)


def test_constraint_references_undefined_variable_raise_validation_error() -> None:
    data = portfolio_data()
    data["constraints"][0]["linear_terms"]["missing_asset"] = 2.0

    with pytest.raises(ValidationError, match="constraint references undefined variables"):
        ProblemIR.from_dict(data)


def test_binary_variable_with_non_binary_bounds_raise_validation_error() -> None:
    data = portfolio_data()
    data["variables"][0]["lower_bound"] = 0.0
    data["variables"][0]["upper_bound"] = 2.0

    with pytest.raises(ValidationError, match="binary variables"):
        ProblemIR.from_dict(data)


def test_empty_objective_raise_validation_error() -> None:
    data = portfolio_data()
    data["objective"]["linear_terms"] = {}
    data["objective"]["quadratic_terms"] = {}

    with pytest.raises(ValidationError, match="objective must include"):
        ProblemIR.from_dict(data)


def test_dict_round_trip_matches_original() -> None:
    data = portfolio_data()

    assert ProblemIR.from_dict(data).to_dict() == data


def test_json_round_trip_matches_original() -> None:
    data = max_cut_data()
    json_input = canonical_json(data)

    assert ProblemIR.from_json(json_input).to_json() == json_input


def test_quadratic_term_key_canonicalization() -> None:
    data = copy.deepcopy(max_cut_data())
    data["objective"]["quadratic_terms"] = {"x1,x0": -2.0}

    problem = ProblemIR.from_dict(data)

    assert ("x0", "x1") in problem.objective.quadratic_terms
    assert ("x1", "x0") not in problem.objective.quadratic_terms
    assert problem.to_dict()["objective"]["quadratic_terms"] == {"x0,x1": -2.0}
