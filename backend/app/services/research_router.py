"""Config-driven selection of the research agent chain.

Three implementations share the same dossier schema (see each agent for docs):

- ``DeepResearchAgent`` — OpenAI Responses API + native web search. Highest
  quality, slowest and dearest (30-45 min, billed per minute). Only selected
  when ``DEEP_RESEARCH_ENABLED=1``.
- ``SearchResearchAgent`` — Tavily live search + an iterative Claude prompt
  chain: query generation, synthesis, critique with follow-up queries, and a
  final verification pass. The default when ``TAVILY_API_KEY`` is set. Roughly
  90% of deep-research quality at a fraction of the wall-clock and token cost.
- ``LLMResearchAgent`` — training-knowledge synthesis only, no live search.
  Last-resort fallback when no search backend is configured.

``research_agent_chain()`` returns the ordered candidate list. Callers try each
agent in order until one produces a dossier, mirroring the fallback behaviour
that previously lived inline in ``research_tasks.py``.
"""

from __future__ import annotations

from ..utils.logger import get_logger

logger = get_logger("glas.research_router")


def research_agent_chain() -> list:
    """Return research agents in preference order for the current config."""
    from ..config import Config

    if Config.DEEP_RESEARCH_ENABLED:
        from .deep_research_agent import DeepResearchAgent

        return [DeepResearchAgent()]

    if Config.SEARCH_RESEARCH_ENABLED:
        from .search_research_agent import SearchResearchAgent
        from .llm_research_agent import LLMResearchAgent

        return [SearchResearchAgent(), LLMResearchAgent()]

    from .llm_research_agent import LLMResearchAgent

    return [LLMResearchAgent()]


def run_research_chain(
    prompt: str,
    context: str = "",
    angle_overrides: dict | None = None,
) -> dict:
    """Run the first healthy agent in the chain; raise the last error if all fail."""
    last_exc: Exception | None = None
    for agent in research_agent_chain():
        try:
            return agent.run(  # type: ignore[no-any-return]
                prompt, context=context, angle_overrides=angle_overrides
            )
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "%s failed (%s: %s), trying fallback",
                type(agent).__name__,
                type(exc).__name__,
                exc,
            )
    if last_exc is None:
        raise RuntimeError("No research agent available for the current configuration")
    raise last_exc
