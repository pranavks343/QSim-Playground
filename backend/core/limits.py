"""Core-side resource cap primitives used by evaluator and circuit_gen."""

from __future__ import annotations


class QubitCapExceeded(Exception):
    """Raised when a candidate QUBO or circuit exceeds the tier qubit cap."""

    def __init__(self, qubit_count: int, limit: int, source: str = "qubo") -> None:
        self.qubit_count = qubit_count
        self.limit = limit
        self.source = source
        super().__init__(f"{source}: {qubit_count} qubits exceeds tier cap of {limit}")


def enforce_qubit_cap(qubit_count: int, limit: int | None, source: str = "qubo") -> None:
    """Raise :class:`QubitCapExceeded` when ``qubit_count`` is over ``limit``.

    ``limit=None`` disables the check (used for enterprise tier and tests).
    """

    if limit is not None and qubit_count > limit:
        raise QubitCapExceeded(qubit_count=qubit_count, limit=limit, source=source)
