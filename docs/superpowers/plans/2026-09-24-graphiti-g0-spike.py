"""G0 go/no-go spike: build one Graphiti graph from the pharmacy dossier on local Neo4j.

Zero Zep calls. LLM = DeepSeek (thinking off, json_object mode). Embedder = local
sentence-transformers bge-small (384 dims). Reranker = none (RRF recipes only).

Prints counts, timings, token usage and truncated search hits. Never prints secrets.
Writes the full result to g0_result.json next to this file.
"""

import os

os.environ["GRAPHITI_TELEMETRY_ENABLED"] = "false"  # before any graphiti import
os.environ.setdefault("EMBEDDING_DIM", "384")
os.environ.setdefault("SEMAPHORE_LIMIT", "5")

import asyncio
import json
import logging
import pathlib
import sys
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Optional

import requests
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from graphiti_core import Graphiti
from graphiti_core.cross_encoder.client import CrossEncoderClient
from graphiti_core.edges import EntityEdge
from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.nodes import EntityNode, EpisodeType
from graphiti_core.search.search_config_recipes import EDGE_HYBRID_SEARCH_RRF, NODE_HYBRID_SEARCH_RRF

HERE = pathlib.Path(__file__).parent
BACKEND = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
CHUNK, OVERLAP = 2000, 100
MAX_CHUNKS = int(os.environ.get("G0_MAX_CHUNKS", "0")) or None
PRICE_IN, PRICE_OUT = 0.27, 1.10  # USD / Mtok, the app's reference DeepSeek prices (upper bound: ignores cache hits)
RESERVED = {"uuid", "name", "group_id", "labels", "created_at", "summary", "attributes", "name_embedding"}


# ---------- logging: count graphiti errors/warnings ----------
class Counter(logging.Handler):
    def __init__(self):
        super().__init__(logging.WARNING)
        self.errors, self.warnings, self.samples = 0, 0, []

    def emit(self, record):
        if record.levelno >= logging.ERROR:
            self.errors += 1
        else:
            self.warnings += 1
        if len(self.samples) < 12:
            self.samples.append(f"{record.levelname} {record.name}: {record.getMessage()[:240]}")


counter = Counter()
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("graphiti_core").addHandler(counter)
logging.getLogger("graphiti_core").propagate = False  # keep the console readable; counter keeps samples
logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)  # "unknown property" noise on a fresh DB


# ---------- LLM: DeepSeek with thinking disabled + token accounting ----------
usage = {"calls": 0, "prompt": 0, "completion": 0, "cache_hit": 0}


class NoThinkingClient:
    """Wraps AsyncOpenAI so every chat call disables DeepSeek thinking and records usage."""

    def __init__(self, inner: AsyncOpenAI):
        self._inner = inner
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kw):
        kw.setdefault("extra_body", {"thinking": {"type": "disabled"}})
        resp = await self._inner.chat.completions.create(**kw)
        u = getattr(resp, "usage", None)
        usage["calls"] += 1
        if u:
            usage["prompt"] += u.prompt_tokens or 0
            usage["completion"] += u.completion_tokens or 0
            usage["cache_hit"] += getattr(u, "prompt_cache_hit_tokens", 0) or 0
        return resp


# ---------- schema check: json_object mode does not enforce the schema ----------
schema = {"checked": 0, "clean": 0, "extra_keys_dropped": 0, "unwrapped": 0, "invalid_retried": 0, "gave_up": 0, "samples": []}


def normalise(raw, model):
    """Return (dict, how) matching ``model`` with only its own fields, or (None, error).

    DeepSeek in json_object mode sometimes wraps the answer ({"Organization": {...}}) or adds
    keys. Graphiti's own check ignores extra keys, so a wrapper reached Neo4j as a Map and
    failed the whole episode (G0 dry run, 2026-09-24).
    """
    fields = set(model.model_fields)
    candidates = [(raw, "clean")]
    if isinstance(raw, dict) and not (fields & set(raw)):
        inner = [v for v in raw.values() if isinstance(v, dict)]
        if len(inner) == 1:
            # first: with all-optional fields the wrapper itself "validates" as an empty answer
            candidates.insert(0, (inner[0], "unwrapped"))
    err = None
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


class SchemaCheckedClient(OpenAIGenericClient):
    async def _generate_response(self, messages, response_model=None, max_tokens=16384, model_size=None, **kw):
        args = (messages, response_model, max_tokens) + ((model_size,) if model_size is not None else ())
        if response_model is None:
            return await super()._generate_response(*args, **kw)
        schema["checked"] += 1
        last = None
        for attempt in range(3):
            raw = await super()._generate_response(*args, **kw)
            out, how = normalise(raw, response_model)
            if out is not None:
                schema[how] += 1
                if how != "clean" and len(schema["samples"]) < 8:
                    schema["samples"].append(f"{response_model.__name__}: {how} keys={sorted(raw)[:6] if isinstance(raw, dict) else type(raw).__name__}")
                return out
            schema["invalid_retried"] += 1
            last = how
        schema["gave_up"] += 1
        raise ValueError(f"LLM reply failed the {response_model.__name__} schema 3 times: {str(last)[:200]}")


# ---------- embedder: local sentence-transformers ----------
class LocalEmbedder(EmbedderClient):
    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name, device="cpu")

    def _encode(self, texts):
        return self.model.encode(texts, normalize_embeddings=True, convert_to_numpy=True).tolist()

    async def create(self, input_data):
        text = input_data if isinstance(input_data, str) else list(input_data)[0]
        return (await asyncio.to_thread(self._encode, [text]))[0]

    async def create_batch(self, input_data_list):
        return await asyncio.to_thread(self._encode, list(input_data_list))


class NoReranker(CrossEncoderClient):
    async def rank(self, query, passages):
        raise RuntimeError("cross-encoder called; the spike uses RRF recipes only")


# ---------- ontology dict -> Graphiti types ----------
def safe(n: str) -> str:
    return f"entity_{n}" if n.lower() in RESERVED else n


def build_types(onto: dict):
    entity_types, edge_types, edge_map = {}, {}, {}
    for e in onto["entity_types"]:
        ann = {safe(a["name"]): Optional[str] for a in e.get("attributes", [])}  # noqa: UP045
        attrs = {safe(a["name"]): Field(default=None, description=a.get("description", a["name"])) for a in e.get("attributes", [])}
        cls = type(e["name"], (BaseModel,), {"__annotations__": ann, "__doc__": e.get("description", ""), **attrs})
        entity_types[e["name"]] = cls
    for e in onto.get("edge_types", []):
        ann = {safe(a["name"]): Optional[str] for a in e.get("attributes", [])}  # noqa: UP045
        attrs = {safe(a["name"]): Field(default=None, description=a.get("description", a["name"])) for a in e.get("attributes", [])}
        edge_types[e["name"]] = type(e["name"], (BaseModel,), {"__annotations__": ann, "__doc__": e.get("description", ""), **attrs})
        for st in e.get("source_targets", []):
            edge_map.setdefault((st["source"], st["target"]), []).append(e["name"])
    edge_map.setdefault(("Entity", "Entity"), list(edge_types))
    return entity_types, edge_types, edge_map


def chunk(text: str) -> list[str]:
    if BACKEND:
        sys.path.insert(0, str(BACKEND))
        from app.utils.file_parser import split_text_into_chunks

        return split_text_into_chunks(text, CHUNK, OVERLAP)
    return [text[i : i + CHUNK] for i in range(0, len(text), CHUNK - OVERLAP)]


def balance():
    try:
        r = requests.get(
            "https://api.deepseek.com/user/balance",
            headers={"Authorization": f"Bearer {os.environ['LLM_API_KEY']}"},
            timeout=20,
        )
        return float(r.json()["balance_infos"][0]["total_balance"])
    except Exception:
        return None


async def main():
    dossier = (HERE / "g0_dossier.txt").read_text(encoding="utf-8")
    onto = json.loads((HERE / "g0_ontology.json").read_text(encoding="utf-8"))
    entity_types, edge_types, edge_map = build_types(onto)
    chunks = chunk(dossier)[:MAX_CHUNKS]
    group = "g0_spike_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    print(f"group={group} chunks={len(chunks)} (size {CHUNK}/{OVERLAP}) entity_types={len(entity_types)} edge_types={len(edge_types)} map_pairs={len(edge_map)}")

    llm = SchemaCheckedClient(
        config=LLMConfig(
            api_key=os.environ["LLM_API_KEY"],
            base_url=os.environ.get("LLM_BASE_URL", "https://api.deepseek.com"),
            model=os.environ.get("LLM_MODEL_NAME", "deepseek-flash"),
            small_model=os.environ.get("LLM_MODEL_NAME", "deepseek-flash"),
            temperature=0.0,
        ),
        client=NoThinkingClient(AsyncOpenAI(api_key=os.environ["LLM_API_KEY"], base_url=os.environ.get("LLM_BASE_URL", "https://api.deepseek.com"))),
        structured_output_mode="json_object",
    )
    t = time.time()
    embedder = LocalEmbedder(os.environ.get("GRAPHITI_EMBED_MODEL", "BAAI/bge-small-en-v1.5"))
    embed_load_s = round(time.time() - t, 1)

    g = Graphiti(os.environ["NEO4J_URI"], os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"], llm_client=llm, embedder=embedder, cross_encoder=NoReranker())
    await g.build_indices_and_constraints()

    bal0 = balance()
    per_episode, t0 = [], time.time()
    for i, c in enumerate(chunks):
        te = time.time()
        try:
            res = await g.add_episode(
                name=f"dossier_{i:03d}",
                episode_body=c,
                source_description="pharmacy-first-caps research dossier",
                reference_time=datetime.now(timezone.utc),
                source=EpisodeType.text,
                group_id=group,
                entity_types=entity_types,
                edge_types=edge_types,
                edge_type_map=edge_map,
            )
            per_episode.append({"i": i, "ok": True, "nodes": len(res.nodes), "edges": len(res.edges), "s": round(time.time() - te, 1)})
        except Exception as e:  # record, keep going: the spike measures the failure rate
            per_episode.append({"i": i, "ok": False, "err": f"{type(e).__name__}: {str(e)[:200]}", "s": round(time.time() - te, 1)})
        p = per_episode[-1]
        print(f"  ep {i:02d} {'OK ' if p['ok'] else 'ERR'} {p.get('nodes', '-')}n {p.get('edges', '-')}e {p['s']}s {p.get('err', '')}", flush=True)
    build_s = round(time.time() - t0, 1)
    bal1 = balance()

    nodes = await EntityNode.get_by_group_ids(g.driver, [group], limit=5000)
    try:
        edges = await EntityEdge.get_by_group_ids(g.driver, [group], limit=20000)
    except Exception:  # GroupsEdgesNotFoundError when nothing was stored
        edges = []
    by_label: dict[str, int] = {}
    for n in nodes:
        for lab in n.labels:
            if lab != "Entity":
                by_label[lab] = by_label.get(lab, 0) + 1
    typed = [n for n in nodes if any(lab != "Entity" for lab in n.labels)]
    degree: dict[str, int] = {}
    for e in edges:
        degree[e.source_node_uuid] = degree.get(e.source_node_uuid, 0) + 1
        degree[e.target_node_uuid] = degree.get(e.target_node_uuid, 0) + 1
    name_of = {n.uuid: (n.name, [lab for lab in n.labels if lab != "Entity"]) for n in nodes}
    top = sorted(degree.items(), key=lambda kv: -kv[1])[:15]
    edge_names: dict[str, int] = {}
    for e in edges:
        edge_names[e.name] = edge_names.get(e.name, 0) + 1

    queries = [
        "Who opposes the caps on Pharmacy First?",
        "What does the pharmacy association say about funding?",
        "Which government minister or department is responsible for the policy?",
        "How are patients affected by the changes?",
        "What are pharmacy chains planning to do?",
    ]
    searches = []
    for q in queries:
        ts = time.time()
        er = await g.search_(q, config=EDGE_HYBRID_SEARCH_RRF.model_copy(update={"limit": 5}), group_ids=[group])
        nr = await g.search_(q, config=NODE_HYBRID_SEARCH_RRF.model_copy(update={"limit": 5}), group_ids=[group])
        searches.append({"q": q, "s": round(time.time() - ts, 2), "facts": [e.fact[:160] for e in er.edges], "nodes": [n.name for n in nr.nodes]})
    await g.close()

    ok = sum(1 for p in per_episode if p["ok"])
    cost_tokens = usage["prompt"] / 1e6 * PRICE_IN + usage["completion"] / 1e6 * PRICE_OUT
    result = {
        "group": group,
        "chunks": len(chunks),
        "episodes_ok": ok,
        "episodes_ok_pct": round(100 * ok / max(1, len(chunks)), 1),
        "nodes": len(nodes),
        "edges": len(edges),
        "typed_nodes": len(typed),
        "nodes_by_type": dict(sorted(by_label.items(), key=lambda kv: -kv[1])),
        "edges_by_name": dict(sorted(edge_names.items(), key=lambda kv: -kv[1])),
        "edges_invalidated": sum(1 for e in edges if e.invalid_at or e.expired_at),
        "top_degree": [(name_of.get(u, ("?", []))[0], name_of.get(u, ("?", []))[1], d) for u, d in top],
        "build_s": build_s,
        "embed_model_load_s": embed_load_s,
        "llm_usage": usage,
        "schema_checks": schema,
        "cost_usd_token_estimate_upper": round(cost_tokens, 4),
        "cost_usd_balance_delta": None if bal0 is None or bal1 is None else round(bal0 - bal1, 2),
        "graphiti_log_errors": counter.errors,
        "graphiti_log_warnings": counter.warnings,
        "log_samples": counter.samples,
        "per_episode": per_episode,
        "searches": searches,
    }
    (HERE / "g0_result.json").write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("per_episode",)}, indent=1, default=str))


asyncio.run(main())
