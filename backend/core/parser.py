"""AST-only parser for small NumPy optimization snippets."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any, Literal, TypeVar

from core.ir import (
    Constraint,
    ConstraintType,
    Objective,
    ObjectiveSense,
    ProblemIR,
    Variable,
    VariableType,
)

SUPPORTED_PATTERNS = [
    "x = np.array([...]) for one binary decision vector",
    "constant vectors or matrices via np.array([...])",
    "objective = c @ x",
    "objective = x.T @ Q @ x + c @ x",
    "constraint_name = A @ x <= b",
    "constraint_name = np.sum(x) == scalar",
    "minimize(objective) or maximize(objective)",
    "comments containing # minimize or # maximize",
]


@dataclass
class ParserError(Exception):
    """Structured parse error with AST location context."""

    message: str
    ast_node: str
    line: int | None
    column: int | None
    supported_patterns: list[str] = field(default_factory=lambda: SUPPORTED_PATTERNS.copy())

    def __str__(self) -> str:
        location = "unknown location"
        if self.line is not None and self.column is not None:
            location = f"line {self.line}, column {self.column}"
        return f"{self.message} at {location}. Node: {self.ast_node}"


@dataclass(frozen=True)
class ParseSuccess:
    """Successful parser result."""

    status: Literal["success"]
    ir: ProblemIR


@dataclass(frozen=True)
class ParseFailure:
    """Failed parser result."""

    status: Literal["failure"]
    errors: list[ParserError]


ParseResult = ParseSuccess | ParseFailure
TermKey = TypeVar("TermKey")


@dataclass(frozen=True)
class ArraySymbol:
    """Literal array known from the AST."""

    values: list[float] | list[list[float]]

    @property
    def shape(self) -> tuple[int, ...]:
        if not self.values:
            return (0,)
        first = self.values[0]
        if isinstance(first, list):
            return (len(self.values), len(first))
        return (len(self.values),)

    @property
    def is_binary_vector(self) -> bool:
        return len(self.shape) == 1 and all(value in {0.0, 1.0} for value in self.vector())

    def vector(self) -> list[float]:
        if len(self.shape) != 1:
            raise ValueError("array symbol is not a vector")
        return [float(value) for value in self.values if not isinstance(value, list)]

    def matrix(self) -> list[list[float]]:
        if len(self.shape) != 2:
            raise ValueError("array symbol is not a matrix")
        return [[float(value) for value in row] for row in self.values if isinstance(row, list)]


@dataclass(frozen=True)
class VariableVector:
    """Decision vector symbol."""

    source_name: str
    variable_names: list[str]


@dataclass(frozen=True)
class Polynomial:
    """Scalar linear/quadratic polynomial over binary variables."""

    linear_terms: dict[str, float] = field(default_factory=dict)
    quadratic_terms: dict[tuple[str, str], float] = field(default_factory=dict)
    constant: float = 0.0

    def add(self, other: Polynomial) -> Polynomial:
        linear_terms = self.linear_terms.copy()
        quadratic_terms = self.quadratic_terms.copy()
        for name, coefficient in other.linear_terms.items():
            linear_terms[name] = linear_terms.get(name, 0.0) + coefficient
        for key, coefficient in other.quadratic_terms.items():
            left, right = sorted(key)
            canonical_key = (left, right)
            quadratic_terms[canonical_key] = quadratic_terms.get(canonical_key, 0.0) + coefficient
        return Polynomial(
            linear_terms=_drop_zero_terms(linear_terms),
            quadratic_terms=_drop_zero_terms(quadratic_terms),
            constant=self.constant + other.constant,
        )

    def scale(self, coefficient: float) -> Polynomial:
        return Polynomial(
            linear_terms=_drop_zero_terms(
                {name: value * coefficient for name, value in self.linear_terms.items()}
            ),
            quadratic_terms=_drop_zero_terms(
                {key: value * coefficient for key, value in self.quadratic_terms.items()}
            ),
            constant=self.constant * coefficient,
        )


def _drop_zero_terms(terms: dict[TermKey, float]) -> dict[TermKey, float]:
    return {key: value for key, value in terms.items() if value != 0.0}


class NumPyOptimizationParser(ast.NodeVisitor):
    """Parse a safe subset of NumPy optimization code by walking the AST only."""

    def __init__(self, source: str) -> None:
        self.source = source
        self.arrays: dict[str, ArraySymbol] = {}
        self.scalars: dict[str, float] = {}
        self.literals: dict[str, Any] = {}
        self.variable_vector: VariableVector | None = None
        self.objective: Polynomial | None = None
        self.constraints: list[Constraint] = []
        self.sense: ObjectiveSense | None = self._sense_from_comments(source)
        self.errors: list[ParserError] = []

    def parse_tree(self, tree: ast.Module) -> ParseResult:
        """Visit a parsed AST module and return a parse result."""

        for statement in tree.body:
            try:
                self.visit(statement)
            except ParserError as error:
                self.errors.append(error)

        if self.errors:
            return ParseFailure(status="failure", errors=self.errors)

        if self.objective is None:
            return ParseFailure(status="failure", errors=[self._error(tree, "no objective found")])

        if self.variable_vector is None:
            return ParseFailure(
                status="failure",
                errors=[self._error(tree, "no binary decision variable vector found")],
            )

        sense = self.sense or ObjectiveSense.MINIMIZE
        try:
            ir = ProblemIR(
                name=str(self.literals.get("name", "parsed_problem")),
                description=str(self.literals.get("description", "")),
                variables=[
                    Variable(name=name, type=VariableType.BINARY)
                    for name in self.variable_vector.variable_names
                ],
                objective=Objective(
                    sense=sense,
                    linear_terms=self.objective.linear_terms,
                    quadratic_terms=self.objective.quadratic_terms,
                    constant=self.objective.constant,
                ),
                constraints=self.constraints,
                metadata=dict(self.literals.get("metadata", {})),
            )
        except ValueError as exc:
            return ParseFailure(status="failure", errors=[self._error(tree, str(exc))])

        return ParseSuccess(status="success", ir=ir)

    def visit_Import(self, node: ast.Import) -> None:
        """Allow NumPy imports as declarations and reject other imports."""

        for alias in node.names:
            if alias.name != "numpy":
                raise self._error(
                    node,
                    "Unsupported pattern: imports other than numpy are not allowed",
                )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Reject from-imports from user code."""

        raise self._error(node, "Unsupported pattern: from-import statements are not allowed")

    def visit_For(self, node: ast.For) -> None:
        """Reject control flow that implies unsupported transformations."""

        raise self._error(
            node,
            "Unsupported pattern: for loop with conditionals. "
            "Try simplifying or use template mode.",
        )

    def visit_If(self, node: ast.If) -> None:
        """Reject conditionals in optimization snippets."""

        raise self._error(
            node,
            "Unsupported pattern: conditionals. Try simplifying or use template mode.",
        )

    def visit_Expr(self, node: ast.Expr) -> None:
        """Handle objective sense calls and reject unsupported expression statements."""

        if isinstance(node.value, ast.Call):
            self.visit_Call(node.value)
            return
        raise self._error(node, "Unsupported pattern: expression statement")

    def visit_Assign(self, node: ast.Assign) -> None:
        """Handle variable bindings, objective bindings, and constraint bindings."""

        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            raise self._error(node, "Unsupported pattern: assignment target")

        target = node.targets[0].id
        value = node.value

        if isinstance(value, ast.Compare):
            self.constraints.append(self._constraint_from_compare(value, target))
            return

        if isinstance(value, ast.Call) and self._is_np_array_call(value):
            array_symbol = self._array_from_call(value)
            self.arrays[target] = array_symbol
            if target == "x" and array_symbol.is_binary_vector:
                self.variable_vector = VariableVector(
                    source_name=target,
                    variable_names=[f"x_{index}" for index in range(array_symbol.shape[0])],
                )
            return

        literal = self._literal_from_node(value)
        if literal is not None:
            self.literals[target] = literal
            if isinstance(literal, int | float):
                self.scalars[target] = float(literal)
            return

        polynomial = self._eval_polynomial(value)
        if target == "objective":
            self.objective = polynomial
            return

        raise self._error(value, f"Unsupported pattern: assignment to {target}")

    def visit_Compare(self, node: ast.Compare) -> None:
        """Handle standalone constraints."""

        self.constraints.append(self._constraint_from_compare(node, None))

    def visit_BinOp(self, node: ast.BinOp) -> None:
        """Validate supported binary arithmetic."""

        self._eval_polynomial(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Handle np.array, np.sum, minimize, and maximize calls."""

        call_name = self._call_name(node)
        if call_name in {"minimize", "maximize"}:
            self._set_objective_from_sense_call(node, call_name)
            return
        if call_name in {"np.array", "numpy.array", "np.sum", "numpy.sum", "sum"}:
            return
        raise self._error(node, f"Unsupported pattern: function call {call_name}")

    def visit_Subscript(self, node: ast.Subscript) -> None:
        """Validate supported indexed access."""

        self._eval_polynomial(node)

    def _sense_from_comments(self, source: str) -> ObjectiveSense | None:
        for line in source.splitlines():
            comment_index = line.find("#")
            if comment_index == -1:
                continue
            comment = line[comment_index:].lower()
            if "minimize" in comment:
                return ObjectiveSense.MINIMIZE
            if "maximize" in comment:
                return ObjectiveSense.MAXIMIZE
        return None

    def _set_objective_from_sense_call(self, node: ast.Call, call_name: str) -> None:
        if len(node.args) != 1:
            raise self._error(node, f"Unsupported pattern: {call_name} expects one argument")

        self.sense = ObjectiveSense.MINIMIZE if call_name == "minimize" else ObjectiveSense.MAXIMIZE
        argument = node.args[0]
        if isinstance(argument, ast.Name) and argument.id == "objective":
            if self.objective is None:
                raise self._error(
                    node,
                    "Unsupported pattern: objective referenced before assignment",
                )
            return
        self.objective = self._eval_polynomial(argument)

    def _constraint_from_compare(self, node: ast.Compare, name: str | None) -> Constraint:
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise self._error(node, "Unsupported pattern: chained comparisons")

        constraint_type = self._constraint_type(node.ops[0])
        lhs = self._eval_polynomial(node.left)
        rhs = self._eval_polynomial(node.comparators[0])
        polynomial = lhs.add(rhs.scale(-1.0))

        if polynomial.quadratic_terms:
            raise self._error(node, "Unsupported pattern: quadratic constraints")

        return Constraint(
            name=name,
            linear_terms=polynomial.linear_terms,
            type=constraint_type,
            rhs=-polynomial.constant,
        )

    def _constraint_type(self, operator: ast.cmpop) -> ConstraintType:
        if isinstance(operator, ast.LtE):
            return ConstraintType.LEQ
        if isinstance(operator, ast.GtE):
            return ConstraintType.GEQ
        if isinstance(operator, ast.Eq):
            return ConstraintType.EQ
        raise self._error(operator, "Unsupported pattern: comparison operator")

    def _eval_polynomial(self, node: ast.AST) -> Polynomial:
        if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
            return Polynomial(constant=float(node.value))

        if isinstance(node, ast.Name):
            if node.id == "objective" and self.objective is not None:
                return self.objective
            if node.id in self.scalars:
                return Polynomial(constant=self.scalars[node.id])
            raise self._error(node, f"Unsupported pattern: scalar name {node.id}")

        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return self._eval_polynomial(node.operand).scale(-1.0)

        if isinstance(node, ast.BinOp):
            if isinstance(node.op, ast.MatMult):
                return self._eval_matmul(node)
            if isinstance(node.op, ast.Add):
                return self._eval_polynomial(node.left).add(self._eval_polynomial(node.right))
            if isinstance(node.op, ast.Sub):
                return self._eval_polynomial(node.left).add(
                    self._eval_polynomial(node.right).scale(-1.0)
                )
            if isinstance(node.op, ast.Mult):
                return self._eval_multiplication(node)

        if isinstance(node, ast.Call):
            call_name = self._call_name(node)
            if call_name in {"np.sum", "numpy.sum", "sum"}:
                return self._eval_sum(node)

        if isinstance(node, ast.Subscript):
            return self._eval_subscript(node)

        raise self._error(
            node,
            "Unsupported pattern: expression. Try simplifying or use template mode.",
        )

    def _eval_multiplication(self, node: ast.BinOp) -> Polynomial:
        left_scalar = self._scalar_value(node.left)
        if left_scalar is not None:
            return self._eval_polynomial(node.right).scale(left_scalar)

        right_scalar = self._scalar_value(node.right)
        if right_scalar is not None:
            return self._eval_polynomial(node.left).scale(right_scalar)

        raise self._error(
            node,
            "Unsupported pattern: multiplication between non-scalar expressions",
        )

    def _eval_matmul(self, node: ast.BinOp) -> Polynomial:
        quadratic = self._quadratic_from_matmul(node)
        if quadratic is not None:
            return quadratic

        vector = self._array_vector(node.left)
        variable_vector = self._variable_vector_from_node(node.right)
        if vector is None or variable_vector is None:
            raise self._error(
                node,
                "Unsupported pattern: matrix multiplication with non-constant matrix. "
                "Try simplifying or use template mode.",
            )

        if len(vector) != len(variable_vector.variable_names):
            raise self._error(node, "Unsupported pattern: vector length does not match variables")

        return Polynomial(
            linear_terms=dict(zip(variable_vector.variable_names, vector, strict=True))
        )

    def _quadratic_from_matmul(self, node: ast.BinOp) -> Polynomial | None:
        if not isinstance(node.left, ast.BinOp) or not isinstance(node.left.op, ast.MatMult):
            return None

        left = node.left.left
        matrix_node = node.left.right
        right = node.right
        transposed_variable = self._transposed_variable_from_node(left)
        variable_vector = self._variable_vector_from_node(right)
        matrix = self._array_matrix(matrix_node)

        if transposed_variable is None or variable_vector is None or matrix is None:
            return None
        if transposed_variable.source_name != variable_vector.source_name:
            raise self._error(node, "Unsupported pattern: quadratic form uses different variables")

        names = variable_vector.variable_names
        if len(matrix) != len(names) or any(len(row) != len(names) for row in matrix):
            raise self._error(node, "Unsupported pattern: quadratic matrix shape mismatch")

        linear_terms: dict[str, float] = {}
        quadratic_terms: dict[tuple[str, str], float] = {}
        for row_index, row in enumerate(matrix):
            for column_index, coefficient in enumerate(row):
                if coefficient == 0.0:
                    continue
                if row_index == column_index:
                    variable_name = names[row_index]
                    linear_terms[variable_name] = linear_terms.get(variable_name, 0.0) + coefficient
                elif row_index < column_index:
                    symmetric_coefficient = coefficient + matrix[column_index][row_index]
                    if symmetric_coefficient != 0.0:
                        quadratic_terms[(names[row_index], names[column_index])] = (
                            symmetric_coefficient
                        )

        return Polynomial(
            linear_terms=_drop_zero_terms(linear_terms),
            quadratic_terms=_drop_zero_terms(quadratic_terms),
        )

    def _eval_sum(self, node: ast.Call) -> Polynomial:
        if len(node.args) != 1:
            raise self._error(node, "Unsupported pattern: sum expects one argument")

        argument = node.args[0]
        variable_vector = self._variable_vector_from_node(argument)
        if variable_vector is not None:
            return Polynomial(linear_terms={name: 1.0 for name in variable_vector.variable_names})

        if isinstance(argument, ast.GeneratorExp):
            return self._eval_sum_generator(argument)

        raise self._error(node, "Unsupported pattern: sum over non-variable expression")

    def _eval_sum_generator(self, node: ast.GeneratorExp) -> Polynomial:
        if len(node.generators) != 1:
            raise self._error(node, "Unsupported pattern: generator sum with multiple clauses")
        generator = node.generators[0]
        if generator.ifs:
            raise self._error(node, "Unsupported pattern: generator sum with conditionals")
        if not isinstance(generator.target, ast.Name):
            raise self._error(node, "Unsupported pattern: generator target")
        if not isinstance(generator.iter, ast.Call) or self._call_name(generator.iter) != "range":
            raise self._error(node, "Unsupported pattern: generator sum without range")

        range_values = self._range_values(generator.iter)
        terms: dict[str, float] = {}
        for index in range_values:
            terms = (
                self._eval_generator_element(node.elt, generator.target.id, index)
                .add(Polynomial(linear_terms=terms))
                .linear_terms
            )
        return Polynomial(linear_terms=terms)

    def _eval_generator_element(
        self,
        node: ast.AST,
        loop_variable: str,
        loop_value: int,
    ) -> Polynomial:
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.slice, ast.Name)
            and node.slice.id == loop_variable
        ):
            return self._subscript_polynomial(node.value, loop_value, node)
        raise self._error(node, "Unsupported pattern: generator element")

    def _eval_subscript(self, node: ast.Subscript) -> Polynomial:
        index = self._integer_index(node.slice)
        return self._subscript_polynomial(node.value, index, node)

    def _subscript_polynomial(self, value_node: ast.AST, index: int, node: ast.AST) -> Polynomial:
        variable_vector = self._variable_vector_from_node(value_node)
        if variable_vector is not None:
            try:
                variable_name = variable_vector.variable_names[index]
            except IndexError as exc:
                raise self._error(node, "Unsupported pattern: variable index out of range") from exc
            return Polynomial(linear_terms={variable_name: 1.0})

        vector = self._array_vector(value_node)
        if vector is not None:
            try:
                return Polynomial(constant=vector[index])
            except IndexError as exc:
                raise self._error(node, "Unsupported pattern: array index out of range") from exc

        raise self._error(node, "Unsupported pattern: indexed access")

    def _range_values(self, node: ast.Call) -> range:
        if len(node.args) == 1:
            stop = self._integer_index(node.args[0])
            return range(stop)
        if len(node.args) == 2:
            start = self._integer_index(node.args[0])
            stop = self._integer_index(node.args[1])
            return range(start, stop)
        raise self._error(node, "Unsupported pattern: range arity")

    def _integer_index(self, node: ast.AST) -> int:
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            return node.value
        if isinstance(node, ast.Name) and node.id in self.scalars:
            value = self.scalars[node.id]
            if value.is_integer():
                return int(value)
        raise self._error(node, "Unsupported pattern: non-constant index")

    def _scalar_value(self, node: ast.AST) -> float | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
            return float(node.value)
        if isinstance(node, ast.Name) and node.id in self.scalars:
            return self.scalars[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            operand = self._scalar_value(node.operand)
            if operand is not None:
                return -operand
        return None

    def _array_vector(self, node: ast.AST) -> list[float] | None:
        if isinstance(node, ast.Name) and node.id in self.arrays:
            symbol = self.arrays[node.id]
            if len(symbol.shape) == 1:
                return symbol.vector()
        return None

    def _array_matrix(self, node: ast.AST) -> list[list[float]] | None:
        if isinstance(node, ast.Name) and node.id in self.arrays:
            symbol = self.arrays[node.id]
            if len(symbol.shape) == 2:
                return symbol.matrix()
        return None

    def _variable_vector_from_node(self, node: ast.AST) -> VariableVector | None:
        if (
            isinstance(node, ast.Name)
            and self.variable_vector is not None
            and node.id == self.variable_vector.source_name
        ):
            return self.variable_vector
        return None

    def _transposed_variable_from_node(self, node: ast.AST) -> VariableVector | None:
        if isinstance(node, ast.Attribute) and node.attr == "T":
            return self._variable_vector_from_node(node.value)
        return None

    def _array_from_call(self, node: ast.Call) -> ArraySymbol:
        if len(node.args) != 1:
            raise self._error(node, "Unsupported pattern: np.array expects one literal argument")

        literal = self._literal_from_node(node.args[0])
        if not isinstance(literal, list):
            raise self._error(node, "Unsupported pattern: np.array argument must be a list")

        normalized = self._normalize_array_literal(literal, node)
        return ArraySymbol(values=normalized)

    def _normalize_array_literal(
        self,
        literal: list[Any],
        node: ast.AST,
    ) -> list[float] | list[list[float]]:
        if all(isinstance(value, int | float) for value in literal):
            return [float(value) for value in literal]

        if all(isinstance(row, list) for row in literal):
            rows = []
            row_length: int | None = None
            for row in literal:
                if not all(isinstance(value, int | float) for value in row):
                    raise self._error(node, "Unsupported pattern: non-numeric np.array")
                if row_length is None:
                    row_length = len(row)
                elif len(row) != row_length:
                    raise self._error(node, "Unsupported pattern: ragged np.array")
                rows.append([float(value) for value in row])
            return rows

        raise self._error(node, "Unsupported pattern: non-numeric np.array")

    def _literal_from_node(self, node: ast.AST) -> Any | None:
        try:
            return ast.literal_eval(node)
        except (ValueError, SyntaxError):
            return None

    def _is_np_array_call(self, node: ast.AST) -> bool:
        return isinstance(node, ast.Call) and self._call_name(node) in {"np.array", "numpy.array"}

    def _call_name(self, node: ast.Call) -> str:
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            return f"{node.func.value.id}.{node.func.attr}"
        return ast.dump(node.func)

    def _error(self, node: ast.AST, message: str) -> ParserError:
        return ParserError(
            message=message,
            ast_node=ast.dump(node),
            line=getattr(node, "lineno", None),
            column=getattr(node, "col_offset", None),
        )


def parse(source: str) -> ParseResult:
    """Parse NumPy optimization source without executing user code."""

    if not source.strip():
        return ParseFailure(
            status="failure",
            errors=[
                ParserError(
                    message="no objective found",
                    ast_node="",
                    line=None,
                    column=None,
                )
            ],
        )

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return ParseFailure(
            status="failure",
            errors=[
                ParserError(
                    message=f"syntax error: {exc.msg}",
                    ast_node="",
                    line=exc.lineno,
                    column=exc.offset,
                )
            ],
        )

    return NumPyOptimizationParser(source).parse_tree(tree)
