"""
Pluggable context enrichment before graph/simulation (domain-agnostic).

Default: sync upload-based grounding only.
DeepResearch: also ingests dossier sources when available.
"""

from __future__ import annotations

import json
import os
from typing import Protocol, runtime_checkable

from ..config import Config
from ..utils.logger import get_logger
from .grounding_bundle import sync_grounding_sources_from_project, ingest_dossier_sources

logger = get_logger('glas.context_enricher')


@runtime_checkable
class ContextEnricher(Protocol):
    """Refresh project grounding / external snapshots."""

    def refresh(self, project) -> None:
        ...


class DefaultContextEnricher:
    """Uploads-only: rebuild grounding_sources from project files."""

    def refresh(self, project) -> None:
        sync_grounding_sources_from_project(project)
        logger.info(f"Context enricher (default): synced {len(project.grounding_sources or [])} sources")


class DeepResearchContextEnricher(DefaultContextEnricher):
    """Syncs upload grounding, then ingests deep research dossier sources."""

    def refresh(self, project) -> None:
        super().refresh(project)
        dossier_path = getattr(project, 'research_dossier_path', None)
        if dossier_path and os.path.isfile(dossier_path):
            try:
                with open(dossier_path, 'r', encoding='utf-8') as f:
                    dossier = json.load(f)
                ingest_dossier_sources(project, dossier)
                logger.info(
                    f"Context enricher (deep research): ingested dossier, "
                    f"total sources now {len(project.grounding_sources or [])}"
                )
            except (json.JSONDecodeError, OSError):
                logger.warning("Could not load research dossier for context enrichment")


class StubWebContextEnricher(DefaultContextEnricher):
    """Placeholder for future web/news/market fetch."""

    def refresh(self, project) -> None:
        super().refresh(project)
        if Config.ENABLE_WEB_ENRICHER:
            logger.warning(
                "ENABLE_WEB_ENRICHER is set but no network adapter is configured; "
                "only upload grounding applied."
            )


def get_context_enricher() -> ContextEnricher:
    if Config.DEEP_RESEARCH_ENABLED:
        return DeepResearchContextEnricher()
    if Config.ENABLE_WEB_ENRICHER:
        return StubWebContextEnricher()
    return DefaultContextEnricher()
