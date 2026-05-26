from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

import pytest

from core.ir import ObjectiveSense
from core.parser import NumPyOptimizationParser, ParseFailure, ParseSuccess, parse
from core.templates import get_template

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def fixture_source(name: str) -> str:
    return (FIXTURE_DIR / f"{name}_numpy.py").read_text(encoding="utf-8")


@pytest.mark.parametrize("template_name", ["portfolio", "max_cut", "knapsack"])
def test_template_numpy_fixture_parses_to_template_ir(template_name: str) -> None:
    result = parse(fixture_source(template_name))

    assert isinstance(result, ParseSuccess)
    assert result.ir.to_dict() == get_template(template_name).to_dict()


def test_empty_code_returns_no_objective_failure() -> None:
    result = parse("")

    assert isinstance(result, ParseFailure)
    assert "no objective found" in result.errors[0].message


def test_syntax_error_returns_line_number() -> None:
    result = parse("x = np.array([0, 1]\nobjective = x")

    assert isinstance(result, ParseFailure)
    assert "syntax error" in result.errors[0].message
    assert result.errors[0].line == 1


def test_unsupported_control_flow_returns_helpful_failure() -> None:
    result = parse(
        """
import numpy as np
x = np.array([0, 0])
for i in range(2):
    if i:
        objective = x[i]
"""
    )

    assert isinstance(result, ParseFailure)
    assert "Unsupported pattern" in result.errors[0].message
    assert result.errors[0].line == 4
    assert "template mode" in result.errors[0].message
    assert result.errors[0].supported_patterns


def test_security_os_system_payload_does_not_execute(tmp_path: Path) -> None:
    sentinel = tmp_path / "sentinel.txt"
    sentinel.write_text("still here", encoding="utf-8")
    source = f"""
import os
os.remove({str(sentinel)!r})
"""

    result = parse(source)

    assert isinstance(result, ParseFailure)
    assert sentinel.exists()
    assert sentinel.read_text(encoding="utf-8") == "still here"


def test_security_dunder_import_payload_does_not_import_module() -> None:
    module_name = "qsim_parser_should_not_import_this"
    sys.modules.pop(module_name, None)

    result = parse(f"__import__({module_name!r})")

    assert isinstance(result, ParseFailure)
    assert module_name not in sys.modules


def test_parser_source_has_no_execution_primitives() -> None:
    source = inspect.getsource(NumPyOptimizationParser)
    tree = ast.parse(source)

    forbidden_calls = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"exec", "eval", "compile"}
        ):
            forbidden_calls.append(node.func.id)

    assert forbidden_calls == []


def test_quadratic_objective_extracts_correct_terms() -> None:
    result = parse(
        """
import numpy as np
x = np.array([0, 0])
Q = np.array([[1.0, 2.0], [2.0, 3.0]])
objective = x.T @ Q @ x
minimize(objective)
"""
    )

    assert isinstance(result, ParseSuccess)
    assert result.ir.objective.linear_terms == {"x_0": 1.0, "x_1": 3.0}
    assert result.ir.objective.quadratic_terms == {("x_0", "x_1"): 4.0}


def test_mixed_linear_and_quadratic_objective_extracts_both_parts() -> None:
    result = parse(
        """
import numpy as np
x = np.array([0, 0])
Q = np.array([[1.0, 0.5], [0.5, 2.0]])
c = np.array([4.0, 5.0])
objective = x.T @ Q @ x + c @ x
maximize(objective)
"""
    )

    assert isinstance(result, ParseSuccess)
    assert result.ir.objective.linear_terms == {"x_0": 5.0, "x_1": 7.0}
    assert result.ir.objective.quadratic_terms == {("x_0", "x_1"): 1.0}
    assert result.ir.objective.sense is ObjectiveSense.MAXIMIZE


def test_multiple_constraints_in_sequence_are_captured() -> None:
    result = parse(
        """
import numpy as np
x = np.array([0, 0, 0])
c = np.array([1.0, 2.0, 3.0])
objective = c @ x
limit = c @ x <= 4.0
select_one = np.sum(x) == 1
maximize(objective)
"""
    )

    assert isinstance(result, ParseSuccess)
    assert [constraint.name for constraint in result.ir.constraints] == ["limit", "select_one"]
    assert result.ir.constraints[0].linear_terms == {"x_0": 1.0, "x_1": 2.0, "x_2": 3.0}
    assert result.ir.constraints[0].rhs == 4.0
    assert result.ir.constraints[1].linear_terms == {"x_0": 1.0, "x_1": 1.0, "x_2": 1.0}
    assert result.ir.constraints[1].rhs == 1.0
