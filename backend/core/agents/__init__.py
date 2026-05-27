"""Agent registry for QUBO formulation agents."""

from __future__ import annotations

from collections.abc import Callable

from core.agents.base import QUBOAgent

_AGENT_REGISTRY: dict[str, type[QUBOAgent]] = {}


def register_agent(cls: type[QUBOAgent]) -> type[QUBOAgent]:
    """Register an agent class by its public name."""

    if cls.name in _AGENT_REGISTRY:
        raise ValueError(f"agent '{cls.name}' is already registered")
    _AGENT_REGISTRY[cls.name] = cls
    return cls


def get_agent(name: str) -> type[QUBOAgent]:
    """Return a registered agent class."""

    try:
        return _AGENT_REGISTRY[name]
    except KeyError as exc:
        available = ", ".join(sorted(_AGENT_REGISTRY)) or "none"
        raise KeyError(f"unknown agent '{name}'. Available agents: {available}") from exc


def list_agents() -> list[type[QUBOAgent]]:
    """Return registered agent classes in registration order."""

    return list(_AGENT_REGISTRY.values())


AgentDecorator = Callable[[type[QUBOAgent]], type[QUBOAgent]]


from core.agents import penalty as penalty  # noqa: E402
from core.agents import slack as slack  # noqa: E402
