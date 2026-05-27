from __future__ import annotations

import math

from qiskit import qasm3
from test_agents.helpers import graph_output, penalty_output

from core.circuit_gen import build_qaoa_circuit
from core.runner import run_classical_baseline, simulate_circuit
from core.templates import get_template


def test_portfolio_template_produces_circuit_with_at_most_12_qubits() -> None:
    circuit_data, circuit = build_qaoa_circuit(penalty_output(get_template("portfolio")), reps=1)

    assert circuit_data.qubit_count <= 12
    assert circuit.num_qubits == circuit_data.qubit_count
    assert circuit_data.depth > 0
    assert circuit_data.gate_count > 0


def test_max_cut_template_produces_circuit_with_at_most_12_qubits() -> None:
    circuit_data, circuit = build_qaoa_circuit(graph_output(get_template("max_cut")), reps=1)

    assert circuit_data.qubit_count <= 12
    assert circuit.num_qubits == circuit_data.qubit_count


def test_knapsack_template_produces_circuit_with_at_most_16_qubits() -> None:
    circuit_data, circuit = build_qaoa_circuit(penalty_output(get_template("knapsack")), reps=1)

    assert circuit_data.qubit_count <= 16
    assert circuit.num_qubits == circuit_data.qubit_count


def test_qasm_string_is_valid_and_reparseable() -> None:
    circuit_data, _ = build_qaoa_circuit(penalty_output(get_template("portfolio")), reps=1)

    reparsed = qasm3.loads(circuit_data.qiskit_qasm)

    assert reparsed.num_qubits == circuit_data.qubit_count


def test_simulation_returns_valid_bitstring_and_quality() -> None:
    ir = get_template("portfolio")
    qubo = penalty_output(ir)
    _, circuit = build_qaoa_circuit(qubo, reps=1)

    result = simulate_circuit(circuit, qubo, ir, shots=64)

    assert len(result.best_bitstring) == len(qubo.variable_order)
    assert set(result.best_bitstring) <= {"0", "1"}
    assert result.total_shots == 64
    assert result.top_5_bitstrings
    assert all(
        len(bitstring) == len(qubo.variable_order) for bitstring, _, _ in result.top_5_bitstrings
    )
    assert result.quality_vs_classical >= 0.0
    assert math.isfinite(result.best_objective)


def test_classical_baseline_returns_valid_result() -> None:
    ir = get_template("max_cut")
    qubo = graph_output(ir)

    result = run_classical_baseline(qubo, ir)

    assert len(result.best_bitstring) == len(qubo.variable_order)
    assert set(result.best_bitstring) <= {"0", "1"}
    assert math.isfinite(result.best_objective)
    assert result.runtime_ms >= 0.0
    assert result.method
