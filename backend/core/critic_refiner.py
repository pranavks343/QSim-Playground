"""Critic and refiner agents for ranking and improving QUBO candidates."""

from __future__ import annotations

import json
from typing import Protocol, Self, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

ModelT = TypeVar("ModelT", bound=BaseModel)


class LLMResponseError(ValueError):
    """Raised when an LLM response cannot be validated."""


class GeminiJsonClient(Protocol):
    """Minimal interface for a Gemini JSON-generation client."""

    def generate_json(self, prompt: str) -> str:
        """Return a JSON string for a prompt."""


class QuboCandidate(BaseModel):
    """JSON-safe QUBO candidate emitted by upstream formulation agents."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1)
    agent_name: str = Field(min_length=1)
    linear_terms: dict[str, float] = Field(default_factory=dict)
    quadratic_terms: dict[str, float] = Field(default_factory=dict)
    constant: float = 0.0
    penalty_weight: float | None = Field(default=None, gt=0.0)
    notes: str = ""

    @model_validator(mode="after")
    def require_terms(self) -> Self:
        """Require a meaningful objective surface."""

        if not self.linear_terms and not self.quadratic_terms:
            raise ValueError("QUBO candidate must contain linear or quadratic terms")
        return self


class Scorecard(BaseModel):
    """Evaluator scorecard for one formulation agent's QUBO candidate."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1)
    agent_name: str = Field(min_length=1)
    objective_value: float | None
    feasibility_score: float = Field(ge=0.0, le=1.0)
    approximation_ratio: float | None = Field(default=None, ge=0.0)
    runtime_ms: float = Field(ge=0.0)
    qubit_count: int = Field(ge=0)
    circuit_depth: int = Field(ge=0)
    notes: str = ""
    qubo: QuboCandidate

    @model_validator(mode="after")
    def candidate_ids_must_match(self) -> Self:
        """Keep scorecard and QUBO identifiers aligned."""

        if self.candidate_id != self.qubo.candidate_id:
            raise ValueError("scorecard candidate_id must match qubo candidate_id")
        if self.agent_name != self.qubo.agent_name:
            raise ValueError("scorecard agent_name must match qubo agent_name")
        return self


class RankedCandidate(BaseModel):
    """Ranked critic output for one candidate."""

    model_config = ConfigDict(extra="forbid")

    rank: int = Field(ge=1, le=2)
    candidate_id: str = Field(min_length=1)
    agent_name: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class CriticDecision(BaseModel):
    """Validated critic decision from Gemini."""

    model_config = ConfigDict(extra="forbid")

    top_two: list[RankedCandidate] = Field(min_length=2, max_length=2)
    justification: str = Field(min_length=40)

    @model_validator(mode="after")
    def validate_top_two(self) -> Self:
        """Require rank 1 and rank 2 with different candidates."""

        ranks = sorted(candidate.rank for candidate in self.top_two)
        if ranks != [1, 2]:
            raise ValueError("critic must return exactly rank 1 and rank 2")
        candidate_ids = [candidate.candidate_id for candidate in self.top_two]
        if len(set(candidate_ids)) != 2:
            raise ValueError("critic top_two candidates must be distinct")
        return self


class RefinerDecision(BaseModel):
    """Validated refiner decision from Gemini."""

    model_config = ConfigDict(extra="forbid")

    improved_qubo: QuboCandidate | None = None
    message: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_improvement_shape(self) -> Self:
        """Require an explicit no-improvement message when no improved QUBO is returned."""

        if self.improved_qubo is None and self.message != "no improvement found":
            raise ValueError("refiner without improved_qubo must return 'no improvement found'")
        if self.improved_qubo is not None and self.message == "no improvement found":
            raise ValueError("refiner cannot return improved_qubo with no-improvement message")
        return self


class CriticAgent:
    """Rank candidate scorecards using one Gemini JSON call."""

    def __init__(self, gemini_client: GeminiJsonClient) -> None:
        self._gemini_client = gemini_client

    def rank(self, scorecards: list[Scorecard]) -> CriticDecision:
        """Return the top two ranked candidates with paragraph justification."""

        if len(scorecards) != 5:
            raise ValueError("critic requires exactly 5 scorecards")

        response = self._gemini_client.generate_json(_critic_prompt(scorecards))
        decision = _validate_llm_json(response, CriticDecision)
        allowed_candidate_ids = {scorecard.candidate_id for scorecard in scorecards}
        returned_candidate_ids = {candidate.candidate_id for candidate in decision.top_two}
        unknown_candidate_ids = returned_candidate_ids - allowed_candidate_ids
        if unknown_candidate_ids:
            names = ", ".join(sorted(unknown_candidate_ids))
            raise LLMResponseError(f"critic returned unknown candidate ids: {names}")
        return decision


class RefinerAgent:
    """Improve a winning QUBO using one Gemini JSON call."""

    def __init__(self, gemini_client: GeminiJsonClient) -> None:
        self._gemini_client = gemini_client

    def refine(self, winner: Scorecard) -> RefinerDecision:
        """Return either an improved QUBO or an explicit no-improvement result."""

        response = self._gemini_client.generate_json(_refiner_prompt(winner))
        decision = _validate_llm_json(response, RefinerDecision)
        if (
            decision.improved_qubo is not None
            and decision.improved_qubo.candidate_id != winner.candidate_id
        ):
            raise LLMResponseError("refiner changed the winning candidate_id")
        return decision


def _validate_llm_json(response: str, model_type: type[ModelT]) -> ModelT:
    try:
        raw = json.loads(response)
    except json.JSONDecodeError as exc:
        raise LLMResponseError("LLM response was not valid JSON") from exc

    try:
        return model_type.model_validate(raw)
    except ValueError as exc:
        raise LLMResponseError(f"LLM response failed validation: {exc}") from exc


def _critic_prompt(scorecards: list[Scorecard]) -> str:
    scorecards_json = json.dumps(
        [scorecard.model_dump(mode="json") for scorecard in scorecards],
        sort_keys=True,
    )
    return (
        "You are the QSim Playground critic. You will receive exactly five QUBO "
        "scorecards as JSON. Rank the top two candidates only. Return JSON matching "
        'this schema: {"top_two":[{"rank":1,"candidate_id":"...",'
        '"agent_name":"...","reason":"..."},{"rank":2,"candidate_id":"...",'
        '"agent_name":"...","reason":"..."}],"justification":"paragraph"}. '
        "The justification must be one paragraph in this style: X wins because of A; "
        "Y is close runner-up because of B; Z is rejected because of C. "
        f"Scorecards JSON: {scorecards_json}"
    )


def _refiner_prompt(winner: Scorecard) -> str:
    winner_json = json.dumps(winner.model_dump(mode="json"), sort_keys=True)
    return (
        "You are the QSim Playground refiner. You will receive the winning QUBO "
        "scorecard as JSON. Attempt one targeted improvement: re-tune penalty weights, "
        "simplify constraints, or drop redundant terms. Return JSON matching either "
        '{"improved_qubo":{...},"message":"specific improvement"} or '
        '{"improved_qubo":null,"message":"no improvement found"}. '
        "Do not change candidate_id or agent_name. "
        f"Winning scorecard JSON: {winner_json}"
    )
