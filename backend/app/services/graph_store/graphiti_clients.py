"""The three clients Graphiti needs, set up for this app (all measured in G0, 2026-09-24).

- LLM: any OpenAI-compatible endpoint (DeepSeek here) in ``json_object`` mode, because
  DeepSeek rejects ``json_schema``. In that mode the schema is not enforced, and DeepSeek
  answered in the schema's own shape (``{"title", "type", "properties": {...values}}``) in
  35% of replies. Graphiti ignores extra keys, so the wrapper reached Neo4j as a Map and
  the episode failed. ``SchemaCheckedLLMClient`` validates, unwraps and retries.
- Embedder: local sentence-transformers. No API key, about 130 MB on first use.
- Reranker: none. Searches use RRF recipes, which never call a cross-encoder.

Graphiti's defaults for all three are OpenAI clients, so all three are always passed.
"""

from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
from typing import Any

from graphiti_core.cross_encoder.client import CrossEncoderClient
from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from openai import AsyncOpenAI
from pydantic import BaseModel

from ...utils.logger import get_logger

logger = get_logger("glas.graph_store.graphiti")

SCHEMA_ATTEMPTS = 3


def normalise_reply(raw: Any, model: type[BaseModel]) -> tuple[dict[str, Any] | None, str | Exception]:
    """Return (reply with only ``model``'s fields, how) or (None, validation error).

    ``how`` is "clean", "extra_keys_dropped" or "unwrapped". A reply that has none of the
    model's fields and exactly one dict value is tried unwrapped FIRST: when every field is
    optional, the wrapper itself would validate as an empty answer and lose the data.
    """
    fields = set(model.model_fields)
    candidates: list[tuple[Any, str]] = [(raw, "clean")]
    if isinstance(raw, dict) and not (fields & set(raw)):
        inner = [v for v in raw.values() if isinstance(v, dict)]
        if len(inner) == 1:
            candidates.insert(0, (inner[0], "unwrapped"))
    err: Exception = ValueError("no candidate")
    for cand, how in candidates:
        try:
            inst = model.model_validate(cand)
        except Exception as e:
            err = e
            continue
        out = inst.model_dump(mode="json", exclude_unset=True)
        if how == "clean" and isinstance(cand, dict) and set(cand) - fields:
            how = "extra_keys_dropped"
        return out, how
    return None, err


class UsageCounter:
    """Token and repair counts for one process, for cost logging."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.calls = self.prompt_tokens = self.completion_tokens = self.cache_hit_tokens = 0
        self.repaired = self.retried = 0

    def add_usage(self, usage: Any) -> None:
        with self._lock:
            self.calls += 1
            if usage is not None:
                self.prompt_tokens += getattr(usage, "prompt_tokens", 0) or 0
                self.completion_tokens += getattr(usage, "completion_tokens", 0) or 0
                self.cache_hit_tokens += getattr(usage, "prompt_cache_hit_tokens", 0) or 0

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "calls": self.calls,
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "cache_hit_tokens": self.cache_hit_tokens,
                "repaired": self.repaired,
                "retried": self.retried,
            }


class _ChatWrapper:
    """Looks like ``AsyncOpenAI`` to Graphiti. Adds ``extra_body`` and records usage."""

    def __init__(self, inner: AsyncOpenAI, extra_body: dict[str, Any] | None, usage: UsageCounter):
        self._inner = inner
        self._extra_body = extra_body
        self._usage = usage
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs: Any) -> Any:
        if self._extra_body:
            kwargs.setdefault("extra_body", self._extra_body)
        resp = await self._inner.chat.completions.create(**kwargs)
        self._usage.add_usage(getattr(resp, "usage", None))
        return resp


class SchemaCheckedLLMClient(OpenAIGenericClient):
    def __init__(self, *, api_key: str, base_url: str, model: str, usage: UsageCounter):
        # DeepSeek V4 reasons by default; hidden reasoning uses up max_tokens and returns
        # empty content (same fix as utils/llm_client.py).
        extra_body = {"thinking": {"type": "disabled"}} if "deepseek" in base_url.lower() else None
        super().__init__(
            config=LLMConfig(api_key=api_key, base_url=base_url, model=model, small_model=model, temperature=0.0),
            client=_ChatWrapper(AsyncOpenAI(api_key=api_key, base_url=base_url), extra_body, usage),
            structured_output_mode="json_object",
        )
        self._usage = usage

    async def _generate_response(self, messages, response_model=None, *args: Any, **kwargs: Any):
        if response_model is None:
            return await super()._generate_response(messages, response_model, *args, **kwargs)
        err: str | Exception = ""
        for _ in range(SCHEMA_ATTEMPTS):
            raw = await super()._generate_response(messages, response_model, *args, **kwargs)
            out, how = normalise_reply(raw, response_model)
            if out is not None:
                if how != "clean":
                    self._usage.repaired += 1
                return out
            self._usage.retried += 1
            err = how
        raise ValueError(
            f"LLM reply failed the {response_model.__name__} schema {SCHEMA_ATTEMPTS} times: {str(err)[:200]}"
        )


class LocalEmbedder(EmbedderClient):
    """sentence-transformers on CPU. ``encode`` is synchronous, so it runs in a worker
    thread: on the bridge loop it would stall every other graph call."""

    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.model = SentenceTransformer(model_name, device="cpu")
        self.dim = int(self.model.get_sentence_embedding_dimension())

    def _encode(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts, normalize_embeddings=True, convert_to_numpy=True).tolist()

    async def create(self, input_data: Any) -> list[float]:
        text = input_data if isinstance(input_data, str) else list(input_data)[0]
        return (await asyncio.to_thread(self._encode, [text]))[0]

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(self._encode, list(input_data_list))


class NoReranker(CrossEncoderClient):
    """Only RRF recipes are used, and they never rerank. Fails loud if one ever does."""

    async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
        raise RuntimeError("cross-encoder reranking was requested, but the graph store uses RRF only")
