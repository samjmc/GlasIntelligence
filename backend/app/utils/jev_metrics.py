"""
Process-wide ledger of Jev vs LLM decisions.

Every Jev gate (see ``utils/jev_gate.py``) records here: how many items Jev
answered confidently, how many fell back to the LLM, what each path cost, and
— in shadow mode — how often Jev agreed with the LLM. ``summary()`` turns that
into the numbers the "does Jev save us anything?" question needs.

Costs are ESTIMATES. Jev spend uses the ``usage.input_tokens`` the API returns;
LLM spend uses prompt/completion character counts (÷4 ≈ tokens) against the
reference prices in ``Config``. Both are labelled as such in the output.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..config import Config

_CHARS_PER_TOKEN = 4.0


@dataclass
class SiteStats:
    jev_calls: int = 0
    jev_failed_calls: int = 0
    jev_input_tokens: int = 0
    jev_latency_ms: float = 0.0
    items_total: int = 0
    items_jev_confident: int = 0
    items_jev_low_confidence: int = 0
    items_jev_failed: int = 0
    items_llm: int = 0
    llm_calls: int = 0
    llm_prompt_chars: int = 0
    llm_completion_chars: int = 0
    shadow_compared: int = 0
    shadow_agreed: int = 0

    # ---- derived -------------------------------------------------------

    def jev_cost_usd(self) -> float:
        return self.jev_input_tokens * Config.JEV_PRICE_IN_PER_MTOK / 1e6

    def llm_cost_usd_est(self) -> float:
        prompt_tokens = self.llm_prompt_chars / _CHARS_PER_TOKEN
        completion_tokens = self.llm_completion_chars / _CHARS_PER_TOKEN
        return (
            prompt_tokens * Config.JEV_LLM_PRICE_IN_PER_MTOK + completion_tokens * Config.JEV_LLM_PRICE_OUT_PER_MTOK
        ) / 1e6

    def llm_cost_avoided_usd_est(self) -> float | None:
        """What the items Jev answered would have cost on the LLM path.

        Uses this site's observed per-item LLM cost. ``None`` when no LLM call
        was observed for the site (nothing to extrapolate from).
        """
        if self.items_llm <= 0 or self.llm_calls <= 0:
            return None
        per_item = self.llm_cost_usd_est() / self.items_llm
        return per_item * self.items_jev_confident

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["jev_cost_usd"] = round(self.jev_cost_usd(), 8)
        d["llm_cost_usd_est"] = round(self.llm_cost_usd_est(), 8)
        avoided = self.llm_cost_avoided_usd_est()
        d["llm_cost_avoided_usd_est"] = None if avoided is None else round(avoided, 8)
        d["jev_confident_rate"] = round(self.items_jev_confident / self.items_total, 4) if self.items_total else None
        d["jev_mean_latency_ms"] = round(self.jev_latency_ms / self.jev_calls, 1) if self.jev_calls else None
        d["shadow_agreement_rate"] = (
            round(self.shadow_agreed / self.shadow_compared, 4) if self.shadow_compared else None
        )
        return d


class JevLedger:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sites: dict[str, SiteStats] = {}
        self.started_at = time.time()

    def _site(self, name: str) -> SiteStats:
        stats = self._sites.get(name)
        if stats is None:
            stats = self._sites[name] = SiteStats()
        return stats

    # ---- recording -----------------------------------------------------

    def record_jev_call(self, site: str, *, input_tokens: int, latency_ms: float, ok: bool) -> None:
        with self._lock:
            s = self._site(site)
            s.jev_calls += 1
            if ok:
                s.jev_input_tokens += max(0, int(input_tokens))
            else:
                s.jev_failed_calls += 1
            s.jev_latency_ms += max(0.0, float(latency_ms))

    def record_items(
        self,
        site: str,
        *,
        total: int = 0,
        jev_confident: int = 0,
        jev_low_confidence: int = 0,
        jev_failed: int = 0,
        llm: int = 0,
    ) -> None:
        with self._lock:
            s = self._site(site)
            s.items_total += total
            s.items_jev_confident += jev_confident
            s.items_jev_low_confidence += jev_low_confidence
            s.items_jev_failed += jev_failed
            s.items_llm += llm

    def record_llm_call(self, site: str, *, prompt_chars: int, completion_chars: int) -> None:
        with self._lock:
            s = self._site(site)
            s.llm_calls += 1
            s.llm_prompt_chars += max(0, int(prompt_chars))
            s.llm_completion_chars += max(0, int(completion_chars))

    def record_shadow(self, site: str, *, compared: int, agreed: int) -> None:
        with self._lock:
            s = self._site(site)
            s.shadow_compared += compared
            s.shadow_agreed += agreed

    # ---- reading -------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        with self._lock:
            sites = {name: stats.as_dict() for name, stats in sorted(self._sites.items())}
        totals = SiteStats()
        with self._lock:
            for stats in self._sites.values():
                for field_name in SiteStats.__dataclass_fields__:
                    setattr(totals, field_name, getattr(totals, field_name) + getattr(stats, field_name))
        return {
            "mode": Config.JEV_MODE,
            "provider": Config.JEV_PROVIDER,
            "started_at": self.started_at,
            "elapsed_s": round(time.time() - self.started_at, 1),
            "prices": {
                "jev_in_per_mtok": Config.JEV_PRICE_IN_PER_MTOK,
                "llm_in_per_mtok": Config.JEV_LLM_PRICE_IN_PER_MTOK,
                "llm_out_per_mtok": Config.JEV_LLM_PRICE_OUT_PER_MTOK,
                "note": "LLM figures are estimates from prompt/completion characters (4 chars ~ 1 token).",
            },
            "sites": sites,
            "totals": totals.as_dict(),
        }

    def write(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.summary(), indent=2), encoding="utf-8")
        return p

    def reset(self) -> None:
        with self._lock:
            self._sites.clear()
            self.started_at = time.time()


LEDGER = JevLedger()
