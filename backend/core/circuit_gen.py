"""QAOA circuit generation from refined QUBO matrices."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from qiskit import QuantumCircuit, qasm3, transpile
from qiskit.circuit.library import QAOAAnsatz
from qiskit.quantum_info import SparsePauliOp

from core.agents.base import QUBOOutput
from core.limits import enforce_qubit_cap


class CircuitData(BaseModel):
    """Serializable metadata for a generated QAOA circuit."""

    model_config = ConfigDict(extra="forbid")

    qubit_count: int = Field(ge=1)
    depth: int = Field(ge=0)
    gate_count: int = Field(ge=0)
    reps: int = Field(ge=1)
    qiskit_qasm: str
    circuit_image_svg: str | None = None


def build_qaoa_circuit(
    qubo: QUBOOutput,
    reps: int = 2,
    max_qubits: int | None = None,
) -> tuple[CircuitData, QuantumCircuit]:
    """Build a QAOA ansatz circuit from a QUBO matrix."""

    enforce_qubit_cap(len(qubo.variable_order), max_qubits, source="circuit_gen")
    cost_operator = qubo_to_sparse_pauli_op(qubo)
    ansatz = QAOAAnsatz(cost_operator=cost_operator, reps=reps)
    circuit = transpile(
        ansatz,
        basis_gates=["h", "rx", "rz", "cx", "x", "sx"],
        optimization_level=1,
    )
    circuit_data = CircuitData(
        qubit_count=circuit.num_qubits,
        depth=circuit.depth(),
        gate_count=sum(circuit.count_ops().values()),
        reps=reps,
        qiskit_qasm=qasm3.dumps(circuit),
    )
    return circuit_data, circuit


def qubo_to_sparse_pauli_op(qubo: QUBOOutput) -> SparsePauliOp:
    """Convert `x.T Q x` over binary variables into a Pauli-Z cost operator."""

    matrix = qubo.q_matrix
    size = len(matrix)
    terms: dict[str, float] = {}

    def add_term(label: str, coefficient: float) -> None:
        if abs(coefficient) <= 1e-12:
            return
        terms[label] = terms.get(label, 0.0) + coefficient

    for row in range(size):
        linear_coefficient = matrix[row][row]
        z_label = _z_label(size, row)
        add_term(z_label, -linear_coefficient / 2.0)

    for row in range(size):
        for column in range(row + 1, size):
            coefficient = matrix[row][column] + matrix[column][row]
            zi_label = _z_label(size, row)
            zj_label = _z_label(size, column)
            zij_label = _zz_label(size, row, column)
            add_term(zi_label, -coefficient / 4.0)
            add_term(zj_label, -coefficient / 4.0)
            add_term(zij_label, coefficient / 4.0)

    labels = list(terms) or [_z_label(size, 0)]
    coefficients = [terms[label] for label in labels] or [0.0]
    return SparsePauliOp(labels, coefficients)


def _z_label(size: int, index: int) -> str:
    chars = ["I"] * size
    chars[size - index - 1] = "Z"
    return "".join(chars)


def _zz_label(size: int, left: int, right: int) -> str:
    chars = ["I"] * size
    chars[size - left - 1] = "Z"
    chars[size - right - 1] = "Z"
    return "".join(chars)
