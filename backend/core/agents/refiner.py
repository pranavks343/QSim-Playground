"""LLM refiner agent for targeted QUBO improvements."""

from __future__ import annotations

from functools import cache
from pathlib import Path
from string import Template
from typing import Any

from pydantic import Field

from core.agents.base import QUBOOutput
from core.evaluator import Scorecard
from infra.gemini import GeminiClient

PROMPTS_DIR = Path(__file__).parent / "prompts"


class RefinedQUBO(QUBOOutput):
    """QUBO output augmented with refinement provenance."""

    original_agent: str
    improvements_made: list[str] = Field(min_length=1)
    expected_improvement: str = Field(min_length=50, max_length=1200)


class RefinerAgent:
    """Thin Gemini-backed refiner for one targeted QUBO improvement."""

    prompt_file = "refiner.md"
    temperature = 0.4

    def __init__(self, gemini_client: GeminiClient) -> None:
        self._gemini_client = gemini_client

    async def refine(
        self,
        winner_qubo: QUBOOutput,
        scorecard: Scorecard,
        *,
        with_hints: bool = False,
    ) -> RefinedQUBO:
        """Return a refined QUBO or a no-improvement copy of the original."""

        prompt_template = Template(_load_prompt(self.prompt_file))
        prompt = prompt_template.safe_substitute(
            winner_qubo=winner_qubo.model_dump_json(),
            scorecard=scorecard.model_dump_json(),
            with_hints=str(with_hints).lower(),
            hint_text=_hint_text(scorecard) if with_hints else "none",
        )
        return await self._gemini_client.generate_json(
            prompt,
            RefinedQUBO,
            temperature=self.temperature,
        )


def no_improvement_refinement(winner_qubo: QUBOOutput) -> RefinedQUBO:
    """Create a valid no-improvement refined QUBO from the original output."""

    payload: dict[str, Any] = winner_qubo.model_dump()
    payload.update(
        {
            "original_agent": winner_qubo.agent_name,
            "improvements_made": ["none — original was already near-optimal"],
            "expected_improvement": (
                "No targeted improvement was applied because the winning QUBO was already "
                "near-optimal under the deterministic scorecard metrics."
            ),
        }
    )
    return RefinedQUBO.model_validate(payload)


def _hint_text(scorecard: Scorecard) -> str:
    return (
        f"Focus on the weakest metrics: sparsity={scorecard.sparsity}, "
        f"condition_number={scorecard.condition_number}, "
        f"penalty_sensitivity={scorecard.penalty_sensitivity}, "
        f"classical_baseline_objective={scorecard.classical_baseline_objective}."
    )


@cache
def _load_prompt(prompt_file: str) -> str:
    return (PROMPTS_DIR / prompt_file).read_text(encoding="utf-8")
