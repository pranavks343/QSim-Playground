"""LLM critic agent for turning deterministic scorecards into a verdict."""

from __future__ import annotations

from functools import cache
from pathlib import Path
from string import Template
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.evaluator import ComparisonTable
from infra.gemini import GeminiClient

PROMPTS_DIR = Path(__file__).parent / "prompts"


class CriticVerdict(BaseModel):
    """Structured verdict over deterministic QUBO scorecards."""

    model_config = ConfigDict(extra="forbid")

    winner_agent: str
    runner_up_agent: str
    rejected_agents: list[str] = Field(default_factory=list)
    rationale: str = Field(min_length=50, max_length=1200)
    confidence: Literal["high", "medium", "low"]

    @model_validator(mode="after")
    def validate_agent_sets(self) -> CriticVerdict:
        """Ensure winner, runner-up, and rejected agents are distinct."""

        if self.winner_agent == self.runner_up_agent:
            raise ValueError("winner_agent and runner_up_agent must differ")
        if self.winner_agent in self.rejected_agents:
            raise ValueError("winner_agent cannot also be rejected")
        if self.runner_up_agent in self.rejected_agents:
            raise ValueError("runner_up_agent cannot also be rejected")
        return self


class CriticAgent:
    """Thin Gemini-backed critic for explaining deterministic scorecard rankings."""

    prompt_file = "critic.md"
    temperature = 0.3

    def __init__(self, gemini_client: GeminiClient) -> None:
        self._gemini_client = gemini_client

    async def judge(self, comparison_table: ComparisonTable) -> CriticVerdict:
        """Return a metrics-grounded verdict for a comparison table."""

        prompt_template = Template(_load_prompt(self.prompt_file))
        prompt = prompt_template.safe_substitute(
            comparison_table=comparison_table.model_dump_json(),
            top_agent=comparison_table.top_agent,
            runner_up=comparison_table.runner_up,
        )
        return await self._gemini_client.generate_json(
            prompt,
            CriticVerdict,
            temperature=self.temperature,
        )


@cache
def _load_prompt(prompt_file: str) -> str:
    return (PROMPTS_DIR / prompt_file).read_text(encoding="utf-8")
