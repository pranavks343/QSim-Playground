from __future__ import annotations

import ast
import json
from typing import Any
from uuid import uuid4

import nbformat
import pytest

from api.export import build_notebook, build_script, export_filename


def _completed_run_row(**overrides: Any) -> dict[str, Any]:
    matrix = [
        [1.0, -0.5, 0.0],
        [-0.5, 2.0, 0.25],
        [0.0, 0.25, 3.0],
    ]
    base: dict[str, Any] = {
        "id": str(uuid4()),
        "status": "done",
        "template": "portfolio",
        "input_source": "template",
        "problem_ir": {
            "name": "portfolio",
            "description": "test portfolio problem",
            "variables": [
                {"name": "x_0", "type": "binary"},
                {"name": "x_1", "type": "binary"},
                {"name": "x_2", "type": "binary"},
            ],
            "constraints": [
                {
                    "name": "pick_two",
                    "type": "=",
                    "linear_terms": {"x_0": 1.0, "x_1": 1.0, "x_2": 1.0},
                    "rhs": 2.0,
                }
            ],
            "objective": {
                "sense": "minimize",
                "linear_terms": {"x_0": -0.5, "x_1": -1.0, "x_2": -0.75},
            },
        },
        "winner_agent": "decomp",
        "qubos": {
            "decomp": {
                "agent_name": "decomp",
                "strategy": "decomposition strategy",
                "q_matrix": matrix,
                "variable_order": ["x_0", "x_1", "x_2"],
                "parameters_used": {"lambda": 4.0},
                "justification": "Decomp produced a balanced matrix for this 3-var test problem.",
                "estimated_qubits": 3,
            }
        },
        "refined_qubo": {
            "agent_name": "decomp",
            "strategy": "refined decomposition",
            "q_matrix": matrix,
            "variable_order": ["x_0", "x_1", "x_2"],
            "parameters_used": {"lambda": 4.0},
            "justification": "Refined version of the decomposition formulation.",
            "estimated_qubits": 3,
            "original_agent": "decomp",
            "improvements_made": ["normalized diagonal", "scaled penalty"],
            "expected_improvement": (
                "Reduce condition number and stabilize the penalty term for the test fixture."
            ),
        },
        "critic_verdict": {
            "winner_agent": "decomp",
            "runner_up_agent": "graph",
            "rejected_agents": ["penalty", "slack", "domain"],
            "rationale": "Decomp wins by a clear margin on composite and qubit count.",
            "confidence": "high",
        },
        "circuit_data": {
            "qubit_count": 3,
            "depth": 8,
            "gate_count": 24,
            "reps": 2,
            "qiskit_qasm": (
                "OPENQASM 3.0;\n"
                'include "stdgates.inc";\n'
                "qubit[3] q;\n"
                "bit[3] meas;\n"
                "h q[0];\nh q[1];\nh q[2];\n"
                "barrier q[0], q[1], q[2];\n"
                "measure q -> meas;\n"
            ),
        },
        "sim_result": {
            "best_bitstring": "101",
            "best_objective": -0.5,
            "quality_vs_classical": 92.5,
            "top_5_bitstrings": [["101", 512, -0.5], ["011", 256, -0.4]],
            "total_shots": 1024,
            "runtime_ms": 12.3,
        },
        "classical_result": {
            "best_bitstring": "101",
            "best_objective": -0.54,
            "runtime_ms": 2.1,
            "method": "simulated-annealing",
        },
    }
    base.update(overrides)
    return base


def test_build_notebook_produces_valid_nbformat() -> None:
    run = _completed_run_row()
    notebook = build_notebook(run)
    # build_notebook already calls nbformat.validate; round-trip through JSON
    # to catch any non-serialisable additions.
    serialised = json.dumps(notebook, sort_keys=True)
    nbformat.validate(json.loads(serialised))
    cell_types = [cell["cell_type"] for cell in notebook["cells"]]
    assert "markdown" in cell_types
    assert "code" in cell_types
    # The intro should mention provenance
    intro = notebook["cells"][0]["source"]
    assert "decomp" in intro
    assert "portfolio" in intro
    # Metadata carries provenance
    assert notebook["metadata"]["qsim_provenance"]["winner_agent"] == "decomp"


def test_build_notebook_contains_qasm_and_simulation_cells() -> None:
    run = _completed_run_row()
    notebook = build_notebook(run)
    bodies = [cell["source"] for cell in notebook["cells"]]
    assert any("QASM_SOURCE" in body for body in bodies)
    assert any("AerSimulator" in body for body in bodies)


def test_build_script_is_syntactically_valid_python() -> None:
    run = _completed_run_row()
    script = build_script(run)
    # ast.parse raises on any syntax error.
    ast.parse(script)
    # Header carries provenance
    assert "Winner agent" in script
    assert "decomp" in script
    # No QSim dependency leaks in
    assert "qsim_playground" not in script
    assert "core." not in script
    # Has a top-level guard
    assert "if __name__" in script


def test_build_script_compiles_under_compile_builtin() -> None:
    run = _completed_run_row()
    script = build_script(run)
    compile(script, "<exported-script>", "exec")


def test_export_filename_is_safe() -> None:
    run = _completed_run_row()
    notebook_name = export_filename(run, "ipynb")
    script_name = export_filename(run, "py")
    assert notebook_name.endswith(".ipynb")
    assert script_name.endswith(".py")
    # No path separators or shell-funky chars
    for name in [notebook_name, script_name]:
        for forbidden in ("/", "..", " ", "*", "?"):
            assert forbidden not in name


def test_build_notebook_raises_when_no_winning_qubo() -> None:
    run = _completed_run_row()
    run["refined_qubo"] = None
    run["winner_agent"] = None
    run["qubos"] = None
    with pytest.raises(ValueError):
        build_notebook(run)
