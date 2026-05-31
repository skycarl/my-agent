"""Optional loader for private agents.

Private agents/tools live in a separate (private) repository, made
importable as `my_agent_private` at the repo root (a symlink locally, a
real clone on the Pi—see README). If that package is absent, this loader
no-ops so the public repo runs standalone.

The only contract is `my_agent_private.create_agents(model)` returning a
list of agents to add as orchestrator handoffs.
"""

from agents import Agent
from loguru import logger


def load_private_agents(model: str | None = None) -> list[Agent]:
    """Return private agents to register as handoffs, or [] if none are present."""
    try:
        import my_agent_private
    except ImportError:
        return []

    agents = my_agent_private.create_agents(model)
    logger.debug(f"Loaded {len(agents)} private agent(s): {[a.name for a in agents]}")
    return agents
