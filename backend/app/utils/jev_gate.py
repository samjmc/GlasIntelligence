"""
One confidence-gated decision path for every Jev site.

    jev = JevClient.from_config()
    result = gated(
        site="tool_roles",
        jev=jev,
        items=agent_configs,
        key=lambda ac: ac["agent_id"],
        jev_run=lambda client, items: client.evaluate_many([...], site="tool_roles"),
        accept=lambda item, answers: role_or_none(answers),   # None = unsure / invalid -> LLM
        llm_run=lambda subset: {key: value, ...},        # the ORIGINAL batch prompt over a subset
    )
    result.values   # {key: value} — the merged answer
    result.source   # {key: "jev" | "llm"}

Modes come from ``Config.JEV_MODE`` (``off`` / ``shadow`` / ``active``), forced
to ``off`` for a site listed in ``Config.JEV_DISABLED_SITES`` or when no Jev
client is configured:

    off     -> llm_run(items)                                  (byte-for-byte old behaviour)
    active  -> Jev on all; accepted answers kept; the rest -> llm_run(remaining)
    shadow  -> Jev on all AND llm_run(all); agreement recorded; LLM answers returned

Every path records item counts to ``utils.jev_metrics.LEDGER`` so the
"what did Jev save / how often did it agree" numbers fall out for free.
Callers are responsible for ``LEDGER.record_llm_call`` inside ``llm_run``
(prompt/completion sizes are only known there).
"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass, field
from typing import Any, TypeVar

from ..config import Config
from .jev_client import JevAnswer, JevClient
from .jev_metrics import LEDGER
from .logger import get_logger

logger = get_logger("glas.jev_gate")

T = TypeVar("T")
K = TypeVar("K", bound=Hashable)
V = TypeVar("V")

MODE_OFF = "off"
MODE_SHADOW = "shadow"
MODE_ACTIVE = "active"


@dataclass
class GateResult:
    mode: str
    values: dict[Any, Any] = field(default_factory=dict)
    source: dict[Any, str] = field(default_factory=dict)
    jev_confident: int = 0
    jev_low_confidence: int = 0
    jev_failed: int = 0
    llm_items: int = 0
    shadow_compared: int = 0
    shadow_agreed: int = 0


def site_mode(site: str, jev: JevClient | None) -> str:
    if jev is None or site in Config.JEV_DISABLED_SITES:
        return MODE_OFF
    mode = (Config.JEV_MODE or MODE_OFF).lower()
    if mode not in (MODE_OFF, MODE_SHADOW, MODE_ACTIVE):
        logger.warning(f"Unknown JEV_MODE {mode!r}; treating as off")
        return MODE_OFF
    return mode


def gated(
    *,
    site: str,
    jev: JevClient | None,
    items: Sequence[T],
    key: Callable[[T], K],
    jev_run: Callable[[JevClient, list[T]], list[dict[str, JevAnswer] | None]],
    accept: Callable[[T, dict[str, JevAnswer]], V | None],
    llm_run: Callable[[list[T]], dict[K, V]],
    compare: Callable[[V, V], bool] | None = None,
) -> GateResult:
    items = list(items)
    mode = site_mode(site, jev)
    result = GateResult(mode=mode)
    if not items:
        return result

    if mode == MODE_OFF:
        llm_values = llm_run(items)
        result.values.update(llm_values)
        result.source.update({k: "llm" for k in llm_values})
        result.llm_items = len(items)
        LEDGER.record_items(site, total=len(items), llm=len(items))
        return result

    assert jev is not None  # site_mode guarantees this for shadow/active
    try:
        answers = jev_run(jev, items)
    except Exception as e:  # a gate must never take the pipeline down
        logger.warning(f"[{site}] Jev batch failed ({e}); falling back to the LLM for all items")
        answers = [None] * len(items)
    if len(answers) != len(items):
        logger.warning(f"[{site}] Jev returned {len(answers)} answers for {len(items)} items; treating as failed")
        answers = [None] * len(items)

    jev_values: dict[K, V] = {}
    remaining: list[T] = []
    for item, ans in zip(items, answers, strict=True):
        k = key(item)
        if ans is None:
            result.jev_failed += 1
            remaining.append(item)
            continue
        value = accept(item, ans)
        if value is None:
            result.jev_low_confidence += 1
            remaining.append(item)
            continue
        result.jev_confident += 1
        jev_values[k] = value

    if mode == MODE_ACTIVE:
        result.values.update(jev_values)
        result.source.update({k: "jev" for k in jev_values})
        if remaining:
            llm_values = llm_run(remaining)
            result.values.update(llm_values)
            result.source.update({k: "llm" for k in llm_values})
            result.llm_items = len(remaining)
        LEDGER.record_items(
            site,
            total=len(items),
            jev_confident=result.jev_confident,
            jev_low_confidence=result.jev_low_confidence,
            jev_failed=result.jev_failed,
            llm=len(remaining),
        )
        logger.info(
            f"[{site}] active: {result.jev_confident} via Jev, {len(remaining)} via LLM "
            f"({result.jev_low_confidence} unsure, {result.jev_failed} failed)"
        )
        return result

    # shadow: LLM decides everything; Jev is measured against it
    llm_values = llm_run(items)
    result.values.update(llm_values)
    result.source.update({k: "llm" for k in llm_values})
    result.llm_items = len(items)
    eq = compare or (lambda a, b: a == b)
    for k, jv in jev_values.items():
        if k in llm_values:
            result.shadow_compared += 1
            if eq(jv, llm_values[k]):
                result.shadow_agreed += 1
    LEDGER.record_items(
        site,
        total=len(items),
        jev_confident=result.jev_confident,
        jev_low_confidence=result.jev_low_confidence,
        jev_failed=result.jev_failed,
        llm=len(items),
    )
    LEDGER.record_shadow(site, compared=result.shadow_compared, agreed=result.shadow_agreed)
    logger.info(
        f"[{site}] shadow: Jev confident on {result.jev_confident}/{len(items)}, "
        f"agreed with LLM on {result.shadow_agreed}/{result.shadow_compared}"
    )
    return result
