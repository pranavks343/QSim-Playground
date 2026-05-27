"""Base models and behavior for LLM-backed QUBO formulation agents."""

from __future__ import annotations

from abc import ABC
from functools import cache
from pathlib import Path
from string import Template
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.ir import ProblemIR
from core.templates import TemplateMetadata
from infra.gemini import GeminiClient

PROMPTS_DIR = Path(__file__).parent / "prompts"


class AgentContext(BaseModel):
    """Context available to QUBO formulation agents."""

    model_config = ConfigDict(extra="forbid")

    ir: ProblemIR
    template_metadata: TemplateMetadata | None = None
    run_id: str | None = None


class QUBOOutput(BaseModel):
    """Validated QUBO formulation emitted by an agent."""

    model_config = ConfigDict(extra="forbid")

    agent_name: str
    strategy: str
    q_matrix: list[list[float]]
    variable_order: list[str]
    parameters_used: dict[str, Any] = Field(default_factory=dict)
    justification: str = Field(min_length=50, max_length=1000)
    estimated_qubits: int | None = None

    @model_validator(mode="after")
    def validate_matrix(self) -> QUBOOutput:
        """Validate matrix dimensions, symmetry, and derived qubit count."""

        dimension = len(self.q_matrix)
        if dimension == 0:
            raise ValueError("q_matrix must be non-empty")
        if len(self.variable_order) != dimension:
            raise ValueError("variable_order length must match q_matrix dimension")

        for row in self.q_matrix:
            if len(row) != dimension:
                raise ValueError("q_matrix must be square")

        for row_index in range(dimension):
            for column_index in range(row_index + 1, dimension):
                left = self.q_matrix[row_index][column_index]
                right = self.q_matrix[column_index][row_index]
                if abs(left - right) > 1e-9:
                    raise ValueError("q_matrix must be symmetric within tolerance 1e-9")

        if self.estimated_qubits is None:
            self.estimated_qubits = dimension
        elif self.estimated_qubits != dimension:
            raise ValueError("estimated_qubits must match q_matrix dimension")

        return self


class QUBOAgent(ABC):
    """Base class for LLM-backed QUBO formulation agents."""

    name: ClassVar[str]
    strategy_description: ClassVar[str]
    prompt_file: ClassVar[str]
    temperature: ClassVar[float] = 0.2

    def __init__(self, gemini_client: GeminiClient) -> None:
        self._gemini_client = gemini_client

    async def formulate(self, context: AgentContext) -> QUBOOutput:
        """Build the prompt, call Gemini JSON mode, and validate a QUBO output."""

        prompt_template = Template(self._load_prompt())
        prompt = prompt_template.safe_substitute(
            agent_name=self.name,
            strategy_description=self.strategy_description,
            user_message=self._build_user_message(context),
            problem_ir=context.ir.to_json(),
            template_metadata=(
                context.template_metadata.model_dump_json()
                if context.template_metadata is not None
                else "null"
            ),
            run_id=context.run_id or "",
        )
        return await self._gemini_client.generate_json(
            prompt,
            QUBOOutput,
            temperature=self.temperature,
        )

    def _build_user_message(self, context: AgentContext) -> str:
        """Return additional agent-specific instructions for a formulation request."""

        return (
            f"Formulate the ProblemIR named '{context.ir.name}' as a symmetric QUBO matrix. "
            "Return JSON only."
        )

    @classmethod
    def _load_prompt(cls) -> str:
        """Load the markdown prompt template for this agent class."""

        return _load_prompt(cls.prompt_file)


@cache
def _load_prompt(prompt_file: str) -> str:
    path = PROMPTS_DIR / prompt_file
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"agent prompt file not found: {path}") from exc
