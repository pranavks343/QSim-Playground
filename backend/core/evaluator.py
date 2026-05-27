"""Deterministic QUBO evaluation metrics."""

from __future__ import annotations

import math
import time
from itertools import product
from typing import cast

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.agents.base import QUBOOutput
from core.ir import ProblemIR
from core.limits import enforce_qubit_cap
from core.templates import TemplateMetadata

ZERO_TOLERANCE = 1e-12
MAX_SA_ITERATIONS = 5000
FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int_]


class Scorecard(BaseModel):
    """Deterministic scorecard for one QUBO candidate."""

    model_config = ConfigDict(extra="forbid")

    agent_name: str
    qubit_count: int = Field(ge=1)
    sparsity: float = Field(ge=0.0, le=1.0)
    condition_number: float = Field(ge=0.0)
    penalty_sensitivity: float = Field(ge=0.0, le=1.0)
    classical_baseline_objective: float
    classical_baseline_runtime_ms: float = Field(ge=0.0)
    composite_score: float = Field(ge=0.0, le=10.0)
    notes: str


class ComparisonTable(BaseModel):
    """Sorted deterministic comparison table."""

    model_config = ConfigDict(extra="forbid")

    scorecards: list[Scorecard]
    top_agent: str
    runner_up: str

    @model_validator(mode="after")
    def validate_table(self) -> ComparisonTable:
        """Require a table large enough to compare a winner and runner-up."""

        if len(self.scorecards) < 2:
            raise ValueError("comparison table requires at least two scorecards")
        return self


def qubo_to_array(qubo: QUBOOutput) -> FloatArray:
    """Convert a QUBO output matrix to a NumPy array."""

    return np.asarray(qubo.q_matrix, dtype=np.float64)


def compute_sparsity(q: FloatArray) -> float:
    """Return the fraction of zero entries in the upper triangle, including diagonal."""

    _validate_square_matrix(q)
    upper = q[np.triu_indices(q.shape[0])]
    return float(np.count_nonzero(np.abs(upper) <= ZERO_TOLERANCE) / upper.size)


def compute_condition_number(q: FloatArray) -> float:
    """Return the matrix condition number, or infinity for singular/invalid matrices."""

    _validate_square_matrix(q)
    if np.linalg.matrix_rank(q) < q.shape[0]:
        return float("inf")
    try:
        condition = float(np.linalg.cond(q))
    except np.linalg.LinAlgError:
        return float("inf")
    return condition if math.isfinite(condition) else float("inf")


def compute_penalty_sensitivity(qubo: QUBOOutput, ir: ProblemIR) -> float:
    """Estimate normalized solution shift under +/-10% penalty-weight perturbation.

    If the QUBO reports a `lambda` parameter, the perturbation is approximated as a diagonal
    regularization shift because the source penalty matrix is not retained in `QUBOOutput`.
    The returned value is the average Hamming distance between the original best bitstring and
    the two perturbed best bitstrings, normalized by qubit count. Missing `lambda` means no
    penalty knob exists, so sensitivity is exactly 0.
    """

    del ir
    raw_lambda = qubo.parameters_used.get("lambda")
    if not isinstance(raw_lambda, int | float):
        return 0.0

    penalty_weight = float(raw_lambda)
    if abs(penalty_weight) <= ZERO_TOLERANCE:
        return 0.0

    q = qubo_to_array(qubo)
    original_bits, _ = _best_binary_solution(q)
    shifts: list[float] = []
    for direction in (-1.0, 1.0):
        perturbed = q.copy()
        perturbed += np.eye(q.shape[0]) * (direction * 0.10 * penalty_weight)
        perturbed_bits, _ = _best_binary_solution(perturbed)
        shifts.append(_normalized_hamming_distance(original_bits, perturbed_bits))
    return float(min(1.0, max(0.0, sum(shifts) / len(shifts))))


def run_classical_baseline(q: FloatArray) -> tuple[float, float]:
    """Run a deterministic binary simulated annealing baseline.

    For up to 16 variables, the function enumerates every bitstring exactly. For larger QUBOs,
    it uses a deterministic single-flip simulated annealing loop capped at 5000 iterations.
    Returns `(best_objective, runtime_ms)`.
    """

    _validate_square_matrix(q)
    started = time.perf_counter()
    _, objective = _best_binary_solution(q)
    runtime_ms = (time.perf_counter() - started) * 1000.0
    return float(objective), float(runtime_ms)


def evaluate_qubo(
    qubo: QUBOOutput,
    ir: ProblemIR,
    template_metadata: TemplateMetadata | None,
    max_qubits: int | None = None,
) -> Scorecard:
    """Evaluate a QUBO with six deterministic metrics.

    Composite score:

    `score = 10 * (0.20 * normalize_qubits(qubit_count) + 0.20 * sparsity
    + 0.15 * normalize_condition(condition_number) + 0.20 * (1 - penalty_sensitivity)
    + 0.25 * normalize_baseline_quality(classical_obj, template_optimal))`

    Each normalized term maps to `[0, 1]`. Smaller qubit count is better; sparse and
    well-conditioned matrices are better; lower penalty sensitivity is better; and classical
    objective values closer to the known template optimum are better when one is available.
    """

    q = qubo_to_array(qubo)
    qubit_count = len(qubo.variable_order)
    enforce_qubit_cap(qubit_count, max_qubits, source=f"evaluator:{qubo.agent_name}")
    sparsity = compute_sparsity(q)
    condition_number = compute_condition_number(q)
    penalty_sensitivity = compute_penalty_sensitivity(qubo, ir)
    classical_objective, runtime_ms = run_classical_baseline(q)
    template_optimal = (
        template_metadata.expected_optimal_value if template_metadata is not None else None
    )
    composite_score = 10.0 * (
        0.20 * _normalize_qubits(qubit_count, len(ir.variables))
        + 0.20 * sparsity
        + 0.15 * _normalize_condition(condition_number)
        + 0.20 * (1.0 - penalty_sensitivity)
        + 0.25 * _normalize_baseline_quality(classical_objective, template_optimal)
    )
    notes = _build_notes(q, condition_number, penalty_sensitivity)
    return Scorecard(
        agent_name=qubo.agent_name,
        qubit_count=qubit_count,
        sparsity=round(sparsity, 6),
        condition_number=condition_number,
        penalty_sensitivity=round(penalty_sensitivity, 6),
        classical_baseline_objective=round(classical_objective, 6),
        classical_baseline_runtime_ms=round(runtime_ms, 6),
        composite_score=round(_clamp(composite_score, 0.0, 10.0), 6),
        notes=notes,
    )


def build_comparison_table(scorecards: dict[str, Scorecard]) -> ComparisonTable:
    """Sort scorecards by composite score and identify the top two agents."""

    if len(scorecards) < 2:
        raise ValueError("comparison table requires at least two scorecards")
    ordered = sorted(
        scorecards.values(),
        key=lambda scorecard: (scorecard.composite_score, scorecard.agent_name),
        reverse=True,
    )
    return ComparisonTable(
        scorecards=ordered,
        top_agent=ordered[0].agent_name,
        runner_up=ordered[1].agent_name,
    )


def _validate_square_matrix(q: FloatArray) -> None:
    if q.ndim != 2 or q.shape[0] != q.shape[1]:
        raise ValueError("QUBO matrix must be square")
    if q.shape[0] == 0:
        raise ValueError("QUBO matrix must be non-empty")


def _energy(q: FloatArray, bits: IntArray) -> float:
    return float(bits @ q @ bits)


def _best_binary_solution(q: FloatArray) -> tuple[IntArray, float]:
    size = q.shape[0]
    if size <= 16:
        best_bits = cast(IntArray, np.zeros(size, dtype=np.int_))
        best_energy = _energy(q, best_bits)
        for values in product((0, 1), repeat=size):
            bits = cast(IntArray, np.asarray(values, dtype=np.int_))
            energy = _energy(q, bits)
            if energy < best_energy:
                best_bits = bits
                best_energy = energy
        return best_bits, best_energy

    rng = np.random.default_rng(0)
    bits = cast(IntArray, rng.integers(0, 2, size=size, dtype=np.int_))
    current_energy = _energy(q, bits)
    best_bits = cast(IntArray, bits.copy())
    best_energy = current_energy
    for iteration in range(MAX_SA_ITERATIONS):
        index = iteration % size
        candidate = bits.copy()
        candidate[index] = 1 - candidate[index]
        candidate_energy = _energy(q, candidate)
        temperature = max(0.01, 1.0 - iteration / MAX_SA_ITERATIONS)
        accept_probability = math.exp(min(0.0, (current_energy - candidate_energy) / temperature))
        if candidate_energy <= current_energy or rng.random() < accept_probability:
            bits = cast(IntArray, candidate)
            current_energy = candidate_energy
        if current_energy < best_energy:
            best_bits = cast(IntArray, bits.copy())
            best_energy = current_energy
    return best_bits, best_energy


def _normalized_hamming_distance(left: IntArray, right: IntArray) -> float:
    if left.size == 0:
        return 0.0
    return float(np.count_nonzero(left != right) / left.size)


def _normalize_qubits(qubit_count: int, original_variable_count: int) -> float:
    if qubit_count <= 0:
        return 0.0
    ratio = qubit_count / max(1, original_variable_count)
    return _clamp(1.0 / ratio, 0.0, 1.0)


def _normalize_condition(condition_number: float) -> float:
    if not math.isfinite(condition_number):
        return 0.0
    return _clamp(1.0 / (1.0 + math.log10(max(1.0, condition_number))), 0.0, 1.0)


def _normalize_baseline_quality(classical_obj: float, template_optimal: float | None) -> float:
    if template_optimal is None:
        return 0.5
    scale = max(1.0, abs(template_optimal))
    relative_error = abs(classical_obj - template_optimal) / scale
    return _clamp(1.0 / (1.0 + relative_error), 0.0, 1.0)


def _build_notes(q: FloatArray, condition_number: float, penalty_sensitivity: float) -> str:
    observations: list[str] = []
    if not math.isfinite(condition_number):
        observations.append("matrix is singular")
    elif condition_number > 1e6:
        observations.append("matrix is nearly singular")
    if compute_sparsity(q) > 0.75:
        observations.append("matrix is highly sparse")
    if penalty_sensitivity > 0.5:
        observations.append("solution is sensitive to penalty perturbation")
    return "; ".join(observations) if observations else "metrics are within expected ranges"


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))
