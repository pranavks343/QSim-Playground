"""QAOA simulation and classical comparison utilities."""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import cast

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator
from scipy.optimize import minimize

from core.agents.base import QUBOOutput
from core.evaluator import qubo_to_array
from core.evaluator import run_classical_baseline as evaluator_baseline
from core.ir import ProblemIR


class SimulationResult(BaseModel):
    """Result from sampling an optimized QAOA circuit."""

    model_config = ConfigDict(extra="forbid")

    best_bitstring: str
    best_objective: float
    quality_vs_classical: float
    top_5_bitstrings: list[tuple[str, int, float]]
    total_shots: int = Field(ge=1)
    runtime_ms: float = Field(ge=0.0)


class ClassicalResult(BaseModel):
    """Classical baseline result for the same QUBO."""

    model_config = ConfigDict(extra="forbid")

    best_bitstring: str
    best_objective: float
    runtime_ms: float = Field(ge=0.0)
    method: str


def simulate_circuit(
    circuit: QuantumCircuit,
    qubo: QUBOOutput,
    ir: ProblemIR,
    shots: int = 1024,
) -> SimulationResult:
    """Optimize QAOA parameters with COBYLA, sample on Aer, and decode bitstrings."""

    started = time.perf_counter()
    simulator = AerSimulator()
    parameters = list(circuit.parameters)
    optimization_shots = min(shots, 256)

    if parameters:

        def objective(values: NDArray[np.float64]) -> float:
            bound = circuit.assign_parameters(dict(zip(parameters, values, strict=True)))
            counts = _sample_counts(simulator, bound, optimization_shots)
            return _mean_objective(counts, qubo)

        initial = np.full(len(parameters), 0.1, dtype=np.float64)
        optimized = minimize(
            objective,
            initial,
            method="COBYLA",
            options={"maxiter": 50, "rhobeg": 0.5},
        )
        final_circuit = circuit.assign_parameters(dict(zip(parameters, optimized.x, strict=True)))
    else:
        final_circuit = circuit

    counts = _sample_counts(simulator, final_circuit, shots)
    ranked = _rank_counts(counts, qubo)
    classical = run_classical_baseline(qubo, ir)
    best_bitstring, _, best_objective = ranked[0]
    runtime_ms = (time.perf_counter() - started) * 1000.0
    return SimulationResult(
        best_bitstring=best_bitstring,
        best_objective=best_objective,
        quality_vs_classical=_quality_percentage(best_objective, classical.best_objective),
        top_5_bitstrings=ranked[:5],
        total_shots=shots,
        runtime_ms=runtime_ms,
    )


def run_classical_baseline(qubo: QUBOOutput, ir: ProblemIR) -> ClassicalResult:
    """Run the deterministic evaluator baseline and return a structured result."""

    del ir
    q = qubo_to_array(qubo)
    started = time.perf_counter()
    best_bitstring, best_objective = _best_binary_solution(q)
    _, evaluator_runtime_ms = evaluator_baseline(q)
    runtime_ms = (time.perf_counter() - started) * 1000.0 + evaluator_runtime_ms
    return ClassicalResult(
        best_bitstring=best_bitstring,
        best_objective=round(best_objective, 6),
        runtime_ms=round(runtime_ms, 6),
        method="deterministic_exhaustive_or_simulated_annealing",
    )


def qubo_objective(qubo: QUBOOutput, bitstring: str) -> float:
    """Evaluate a QUBO objective for a bitstring ordered like `variable_order`."""

    values = [int(bit) for bit in bitstring]
    total = 0.0
    for row_index, row in enumerate(qubo.q_matrix):
        for column_index, coefficient in enumerate(row):
            total += coefficient * values[row_index] * values[column_index]
    return round(total, 6)


def _sample_counts(
    simulator: AerSimulator,
    circuit: QuantumCircuit,
    shots: int,
) -> Mapping[str, int]:
    measured = circuit.copy()
    measured.measure_all()
    result = simulator.run(measured, shots=shots, seed_simulator=1234).result()
    counts = result.get_counts()
    return cast(Mapping[str, int], counts)


def _mean_objective(counts: Mapping[str, int], qubo: QUBOOutput) -> float:
    total = 0.0
    shots = 0
    for raw_bitstring, count in counts.items():
        bitstring = _qiskit_to_variable_order(raw_bitstring)
        total += qubo_objective(qubo, bitstring) * count
        shots += count
    return total / max(1, shots)


def _rank_counts(counts: Mapping[str, int], qubo: QUBOOutput) -> list[tuple[str, int, float]]:
    ranked = [
        (
            _qiskit_to_variable_order(raw_bitstring),
            count,
            qubo_objective(qubo, _qiskit_to_variable_order(raw_bitstring)),
        )
        for raw_bitstring, count in counts.items()
    ]
    return sorted(ranked, key=lambda item: (item[2], -item[1], item[0]))


def _qiskit_to_variable_order(raw_bitstring: str) -> str:
    return raw_bitstring.replace(" ", "")[::-1]


def _best_binary_solution(q: NDArray[np.float64]) -> tuple[str, float]:
    size = q.shape[0]
    if size > 16:
        bitstring = "0" * size
        return bitstring, _objective_from_array(q, bitstring)

    best_bitstring = "0" * size
    best_objective = _objective_from_array(q, best_bitstring)
    for value in range(1, 2**size):
        bitstring = format(value, f"0{size}b")
        objective = _objective_from_array(q, bitstring)
        if objective < best_objective:
            best_bitstring = bitstring
            best_objective = objective
    return best_bitstring, best_objective


def _objective_from_array(q: NDArray[np.float64], bitstring: str) -> float:
    bits = np.asarray([int(bit) for bit in bitstring], dtype=np.float64)
    return round(float(bits @ q @ bits), 6)


def _quality_percentage(best_objective: float, classical_objective: float) -> float:
    if abs(classical_objective) <= 1e-12:
        return 100.0 if abs(best_objective) <= 1e-12 else 0.0
    return round(max(0.0, (best_objective / classical_objective) * 100.0), 6)
