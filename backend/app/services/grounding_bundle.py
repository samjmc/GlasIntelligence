"""
Domain-agnostic grounding: source list, staleness, lightweight claim ledger from uploads.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger('glas.grounding_bundle')


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sync_grounding_sources_from_project(project) -> None:
    """
    Rebuild grounding_sources from project.files (uploads).
    Call after ontology generation or file changes.
    """
    if project is None:
        return
    now = _utc_now_iso()
    sources: List[Dict[str, Any]] = []
    for f in (project.files or []):
        label = f.get('filename') or f.get('original_filename') or f.get('saved_filename') or 'document'
        sid = f.get('saved_filename') or label
        sources.append({
            'source_id': f"upload_{project.project_id}_{sid}",
            'kind': 'upload',
            'label': label,
            'retrieved_at': project.updated_at or now,
            'as_of': project.knowledge_as_of or project.updated_at or now,
        })
    project.grounding_sources = sources


def ingest_dossier_sources(project, dossier: Dict[str, Any]) -> None:
    """Append web_research sources from a deep research dossier to grounding_sources."""
    if project is None or not dossier:
        return
    if project.grounding_sources is None:
        project.grounding_sources = []
    existing_ids = {s.get('source_id') for s in project.grounding_sources}
    now = _utc_now_iso()
    from .deep_research_agent import DeepResearchAgent
    for src in dossier.get('sources', []):
        url = src.get('url', '')
        sid = DeepResearchAgent.source_id_from_url(url) if url else None
        if not sid or sid in existing_ids:
            continue
        existing_ids.add(sid)
        project.grounding_sources.append({
            'source_id': sid,
            'kind': 'web_research',
            'label': src.get('title', url),
            'url': url,
            'retrieved_at': now,
            'as_of': now,
        })


def evaluate_grounding_staleness(project) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Returns (warnings as list of dicts, should_block).
    """
    warnings: List[Dict[str, Any]] = []
    if not Config.ENABLE_GROUNDING_FEATURES:
        return warnings, False

    max_age_h = Config.GROUNDING_MAX_AGE_HOURS
    if max_age_h <= 0:
        return warnings, False

    sources = project.grounding_sources or []
    if not sources:
        if Config.GROUNDING_WARN_IF_STALE:
            warnings.append({
                'code': 'no_sources',
                'message': 'No grounding sources recorded; report relies on simulation only.',
            })
        return warnings, False

    now = datetime.now(timezone.utc)
    stale_labels: List[str] = []

    for src in sources:
        ra = src.get('retrieved_at') or src.get('as_of')
        if not ra:
            continue
        try:
            if isinstance(ra, str) and ra.endswith('Z'):
                ra = ra.replace('Z', '+00:00')
            dt = datetime.fromisoformat(ra)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age_h = (now - dt).total_seconds() / 3600.0
            if age_h > max_age_h:
                stale_labels.append(src.get('label', src.get('source_id', 'source')))
        except (TypeError, ValueError) as e:
            logger.debug(f"Could not parse retrieved_at for source: {e}")

    if stale_labels:
        msg = (
            f"The following sources are older than {max_age_h:.0f}h policy: "
            f"{', '.join(stale_labels[:10])}"
        )
        warnings.append({'code': 'stale_sources', 'message': msg, 'labels': stale_labels})

    blocked = bool(stale_labels and Config.GROUNDING_BLOCK_IF_STALE)
    return warnings, blocked


def build_claim_ledger_from_project(project, max_claims: int = 20) -> List[Dict[str, Any]]:
    """
    Claim ledger: one entry per uploaded file + key facts from research dossier.
    """
    claims: List[Dict[str, Any]] = []
    for src in (project.grounding_sources or []):
        if src.get('kind') != 'upload':
            continue
        claims.append({
            'text': f"User-provided document in scope: {src.get('label', 'file')}",
            'source_id': src.get('source_id', 'upload'),
            'evidence_excerpt': '',
            'retrieved_at': src.get('retrieved_at') or src.get('as_of'),
            'classification': 'user_provided_context',
        })
        if len(claims) >= max_claims:
            break

    dossier_path = getattr(project, 'research_dossier_path', None)
    if dossier_path and os.path.isfile(dossier_path) and len(claims) < max_claims:
        try:
            with open(dossier_path, 'r', encoding='utf-8') as f:
                dossier = json.load(f)
            for fact in dossier.get('key_facts', []):
                if len(claims) >= max_claims:
                    break
                claims.append({
                    'text': fact,
                    'source_id': 'deep_research',
                    'evidence_excerpt': '',
                    'retrieved_at': _utc_now_iso(),
                    'classification': 'research_fact',
                })
        except (json.JSONDecodeError, OSError):
            logger.debug("Could not load research dossier for claim ledger")

    return claims


def grounding_summary_text(project) -> str:
    """Human-readable one block for prompts and payload."""
    if project is None:
        return "(No project context)"
    lines: List[str] = []
    as_of = project.knowledge_as_of or project.updated_at
    if as_of:
        lines.append(f"Knowledge as-of (project): {as_of}")
    sources = project.grounding_sources or []
    if not sources:
        lines.append("Grounding: user uploads only (no external live data adapters in this run).")
        return "\n".join(lines)
    lines.append(f"Grounding sources ({len(sources)}):")
    for s in sources[:15]:
        lines.append(
            f"  - [{s.get('kind', '?')}] {s.get('label', s.get('source_id', ''))} "
            f"(retrieved_at={s.get('retrieved_at', 'n/a')})"
        )
    return "\n".join(lines)
