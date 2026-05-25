"""Intermediate representation for optimization problems."""

from __future__ import annotations

import json
from enum import StrEnum
from hashlib import sha256
from typing import Any, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

VARIABLE_NAME_PATTERN = r"^[a-zA-Z_][a-zA-Z0-9_]*$"


class VariableType(StrEnum):
    """Supported optimization variable domains."""

    BINARY = "binary"
    INTEGER = "integer"
    CONTINUOUS = "continuous"


class ConstraintType(StrEnum):
    """Supported constraint comparisons."""

    LEQ = "<="
    GEQ = ">="
    EQ = "="


class ObjectiveSense(StrEnum):
    """Objective direction."""

    MINIMIZE = "minimize"
    MAXIMIZE = "maximize"


class Variable(BaseModel):
    """Optimization decision variable."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=VARIABLE_NAME_PATTERN)
    type: VariableType
    lower_bound: float | None = None
    upper_bound: float | None = None

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        """Validate binary and ordered bounds."""

        if self.type is VariableType.BINARY:
            has_implicit_bounds = self.lower_bound is None and self.upper_bound is None
            has_explicit_binary_bounds = self.lower_bound == 0 and self.upper_bound == 1
            if not has_implicit_bounds and not has_explicit_binary_bounds:
                raise ValueError(
                    "binary variables must use implicit bounds or explicit [0, 1] bounds"
                )

        if (
            self.lower_bound is not None
            and self.upper_bound is not None
            and self.lower_bound > self.upper_bound
        ):
            raise ValueError("lower_bound must be less than or equal to upper_bound")

        return self


def _quadratic_key_from_string(key: str) -> tuple[str, str]:
    parts = [part.strip() for part in key.split(",")]
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError("quadratic term keys must be encoded as 'var_a,var_b'")
    left, right = parts
    return (left, right) if left <= right else (right, left)


def _quadratic_key_from_tuple(key: tuple[Any, ...]) -> tuple[str, str]:
    if len(key) != 2 or not all(isinstance(part, str) and part for part in key):
        raise ValueError("quadratic term tuple keys must contain exactly two variable names")
    left, right = key
    return (left, right) if left <= right else (right, left)


def _parse_quadratic_terms(value: Any) -> dict[tuple[str, str], float]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("quadratic_terms must be a mapping")

    parsed: dict[tuple[str, str], float] = {}
    for raw_key, coefficient in value.items():
        if isinstance(raw_key, str):
            key = _quadratic_key_from_string(raw_key)
        elif isinstance(raw_key, tuple):
            key = _quadratic_key_from_tuple(raw_key)
        else:
            raise ValueError("quadratic term keys must be tuples or 'var_a,var_b' strings")
        parsed[key] = float(coefficient)

    return parsed


def _serialize_quadratic_terms(value: dict[tuple[str, str], float]) -> dict[str, float]:
    return {f"{left},{right}": coefficient for (left, right), coefficient in value.items()}


def _referenced_variable_names(
    linear_terms: dict[str, float],
    quadratic_terms: dict[tuple[str, str], float],
) -> set[str]:
    names = set(linear_terms)
    for left, right in quadratic_terms:
        names.add(left)
        names.add(right)
    return names


class Constraint(BaseModel):
    """Linear or quadratic constraint over known variables."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    linear_terms: dict[str, float]
    quadratic_terms: dict[tuple[str, str], float] = Field(default_factory=dict)
    type: ConstraintType
    rhs: float

    @field_validator("quadratic_terms", mode="before")
    @classmethod
    def parse_quadratic_terms(cls, value: Any) -> dict[tuple[str, str], float]:
        """Parse JSON-safe quadratic term keys."""

        return _parse_quadratic_terms(value)

    @field_serializer("quadratic_terms")
    def serialize_quadratic_terms(self, value: dict[tuple[str, str], float]) -> dict[str, float]:
        """Serialize tuple keys as JSON object keys."""

        return _serialize_quadratic_terms(value)

    @model_validator(mode="after")
    def validate_constraint(self) -> Self:
        """Validate required terms and derive missing names."""

        if not self.linear_terms:
            raise ValueError("constraint linear_terms must be non-empty")

        if self.name is None:
            serialized = json.dumps(self.model_dump(mode="json", exclude={"name"}), sort_keys=True)
            digest = sha256(serialized.encode("utf-8")).hexdigest()[:10]
            self.name = f"constraint_{digest}"

        return self


class Objective(BaseModel):
    """Problem objective."""

    model_config = ConfigDict(extra="forbid")

    sense: ObjectiveSense
    linear_terms: dict[str, float] = Field(default_factory=dict)
    quadratic_terms: dict[tuple[str, str], float] = Field(default_factory=dict)
    constant: float = 0.0

    @field_validator("quadratic_terms", mode="before")
    @classmethod
    def parse_quadratic_terms(cls, value: Any) -> dict[tuple[str, str], float]:
        """Parse JSON-safe quadratic term keys."""

        return _parse_quadratic_terms(value)

    @field_serializer("quadratic_terms")
    def serialize_quadratic_terms(self, value: dict[tuple[str, str], float]) -> dict[str, float]:
        """Serialize tuple keys as JSON object keys."""

        return _serialize_quadratic_terms(value)

    @model_validator(mode="after")
    def validate_objective(self) -> Self:
        """Require at least one non-constant term."""

        if not self.linear_terms and not self.quadratic_terms:
            raise ValueError("objective must include at least one linear or quadratic term")
        return self


class ProblemIR(BaseModel):
    """Normalized optimization problem IR."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    variables: list[Variable] = Field(min_length=1)
    objective: Objective
    constraints: list[Constraint] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        """Ensure variables are unique and every term references a declared variable."""

        variable_names = [variable.name for variable in self.variables]
        declared_names = set(variable_names)
        if len(variable_names) != len(declared_names):
            raise ValueError("variable names must be unique")

        objective_names = _referenced_variable_names(
            self.objective.linear_terms,
            self.objective.quadratic_terms,
        )
        undefined_objective_names = objective_names - declared_names
        if undefined_objective_names:
            names = ", ".join(sorted(undefined_objective_names))
            raise ValueError(f"objective references undefined variables: {names}")

        for constraint in self.constraints:
            constraint_names = _referenced_variable_names(
                constraint.linear_terms,
                constraint.quadratic_terms,
            )
            undefined_constraint_names = constraint_names - declared_names
            if undefined_constraint_names:
                names = ", ".join(sorted(undefined_constraint_names))
                raise ValueError(f"constraint references undefined variables: {names}")

        return self

    @classmethod
    def from_json(cls, json_str: str) -> Self:
        """Create a problem IR from a JSON string."""

        raw = json.loads(json_str)
        if not isinstance(raw, dict):
            raise ValueError("ProblemIR JSON must decode to an object")
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Create a problem IR from a Python dictionary."""

        return cls.model_validate(data)

    def to_dict(self) -> dict[str, Any]:
        """Dump the problem IR as a JSON-safe dictionary."""

        return self.model_dump(mode="json", exclude_none=True)

    def to_json(self) -> str:
        """Dump the problem IR as canonical JSON."""

        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
