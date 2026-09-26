"""Graphiti backend pieces that need no Neo4j and no LLM.

The live contract (real Neo4j + DeepSeek) is in test_graph_store_contract.py and is
opt-in with RUN_GRAPHITI_IT=1.
"""

import asyncio
import threading
import time
from types import SimpleNamespace
from typing import Optional

import pytest
from pydantic import BaseModel

from app import config as app_config
from app.services import graph_store as gs
from app.services.graph_store.async_bridge import AsyncBridge
from app.services.graph_store.graphiti_clients import (
    NoReranker,
    SchemaCheckedLLMClient,
    UsageCounter,
    _ChatWrapper,
    normalise_reply,
)
from app.services.graph_store.ontology import build_graphiti_types, safe_attr_name


class Org(BaseModel):
    org_name: Optional[str] = None  # noqa: UP045
    sector: Optional[str] = None  # noqa: UP045


class Required(BaseModel):
    name: str


# ---------- normalise_reply (the G0 schema-mirror fix) ----------


def test_clean_reply_passes_through():
    assert normalise_reply({"org_name": "NHS"}, Org) == ({"org_name": "NHS"}, "clean")


def test_extra_keys_are_dropped():
    out, how = normalise_reply({"org_name": "NHS", "junk": 1}, Org)
    assert (out, how) == ({"org_name": "NHS"}, "extra_keys_dropped")


def test_schema_shaped_wrapper_is_unwrapped_not_emptied():
    # What DeepSeek sent in 35% of G0 replies. All fields are optional, so the wrapper
    # itself would "validate" as {} and silently drop the values.
    raw = {"title": "Org", "type": "object", "description": "d", "properties": {"org_name": "NHS", "sector": "health"}}
    assert normalise_reply(raw, Org) == ({"org_name": "NHS", "sector": "health"}, "unwrapped")


def test_nested_map_value_is_rejected_not_stored():
    out, err = normalise_reply({"org_name": {"value": "NHS"}}, Org)
    assert out is None and "org_name" in str(err)


def test_required_field_missing_is_rejected():
    out, _err = normalise_reply({"other": "x"}, Required)
    assert out is None


# ---------- SchemaCheckedLLMClient ----------


def _client(monkeypatch, replies, base_url="https://api.deepseek.com"):
    usage = UsageCounter()
    client = SchemaCheckedLLMClient(api_key="k", base_url=base_url, model="deepseek-flash", usage=usage)
    queue = list(replies)

    async def fake_parent(self, messages, response_model=None, *a, **k):
        return queue.pop(0)

    monkeypatch.setattr(
        "graphiti_core.llm_client.openai_generic_client.OpenAIGenericClient._generate_response", fake_parent
    )
    return client, usage


def test_client_repairs_then_returns(monkeypatch):
    client, usage = _client(monkeypatch, [{"properties": {"org_name": "NHS"}}])
    out = asyncio.run(client._generate_response([], Org))
    assert out == {"org_name": "NHS"}
    assert (usage.repaired, usage.retried) == (1, 0)


def test_client_retries_a_bad_reply(monkeypatch):
    client, usage = _client(monkeypatch, [{"org_name": {"x": 1}}, {"org_name": "NHS"}])
    assert asyncio.run(client._generate_response([], Org)) == {"org_name": "NHS"}
    assert usage.retried == 1


def test_client_fails_loud_after_three_bad_replies(monkeypatch):
    client, usage = _client(monkeypatch, [{"org_name": {"x": 1}}] * 3)
    with pytest.raises(ValueError, match="failed the Org schema 3 times"):
        asyncio.run(client._generate_response([], Org))
    assert usage.retried == 3


def test_client_without_a_schema_is_untouched(monkeypatch):
    client, _usage = _client(monkeypatch, [{"anything": {"nested": True}}])
    assert asyncio.run(client._generate_response([], None)) == {"anything": {"nested": True}}


def test_chat_wrapper_disables_thinking_and_counts_usage():
    seen = {}

    async def create(**kw):
        seen.update(kw)
        return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=10, completion_tokens=3, prompt_cache_hit_tokens=4))

    usage = UsageCounter()
    inner = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    wrapper = _ChatWrapper(inner, {"thinking": {"type": "disabled"}}, usage)
    asyncio.run(wrapper.chat.completions.create(model="m", messages=[]))
    assert seen["extra_body"] == {"thinking": {"type": "disabled"}}
    assert usage.snapshot()["prompt_tokens"] == 10 and usage.snapshot()["cache_hit_tokens"] == 4


def test_thinking_switch_only_for_deepseek():
    usage = UsageCounter()
    ds = SchemaCheckedLLMClient(api_key="k", base_url="https://api.deepseek.com/v1", model="m", usage=usage)
    other = SchemaCheckedLLMClient(api_key="k", base_url="https://api.openai.com/v1", model="m", usage=usage)
    assert ds.client._extra_body == {"thinking": {"type": "disabled"}}
    assert other.client._extra_body is None
    assert ds.structured_output_mode == "json_object"


def test_no_reranker_fails_loud():
    with pytest.raises(RuntimeError, match="RRF only"):
        asyncio.run(NoReranker().rank("q", ["p"]))


# ---------- ontology ----------


def test_ontology_maps_types_edges_and_reserved_names():
    ontology = {
        "entity_types": [
            {"name": "Person", "description": "A person.", "attributes": [{"name": "name"}, {"name": "labels"}]},
            {"name": "Organization", "attributes": [{"name": "org_name", "description": "n"}]},
        ],
        "edge_types": [
            {
                "name": "WORKS_FOR",
                "description": "employment",
                "source_targets": [
                    {"source": "Person", "target": "Organization"},
                    {"source": "Person", "target": "Organization"},
                ],
            },
            {"name": "SUPPORTS", "source_targets": [{"source": "Person", "target": "Organization"}]},
        ],
    }
    entities, edges, edge_map = build_graphiti_types(ontology)
    assert set(entities) == {"Person", "Organization"}
    assert set(entities["Person"].model_fields) == {"entity_name", "entity_labels"}
    assert entities["Person"].__doc__ == "A person."
    assert set(edges) == {"WORKS_FOR", "SUPPORTS"}
    assert edge_map[("Person", "Organization")] == ["WORKS_FOR", "WORKS_FOR", "SUPPORTS"]
    assert edge_map[("Entity", "Entity")] == ["WORKS_FOR", "SUPPORTS"]


def test_empty_ontology_gives_no_types():
    assert build_graphiti_types(None) == ({}, {}, {})
    assert safe_attr_name("Summary") == "entity_Summary" and safe_attr_name("role") == "role"


# ---------- AsyncBridge ----------


def test_bridge_runs_coroutines_on_one_loop():
    bridge = AsyncBridge("test-bridge")
    try:

        async def loop_id():
            return id(asyncio.get_running_loop())

        assert bridge.run(loop_id()) == bridge.run(loop_id())
        with pytest.raises(TimeoutError):
            bridge.run(asyncio.sleep(5), timeout=0.05)
    finally:
        bridge.close()


# ---------- backend selection ----------


def test_graphiti_backend_reports_missing_settings(monkeypatch):
    monkeypatch.setattr(app_config.Config, "GRAPH_BACKEND", "graphiti")
    monkeypatch.setattr(app_config.Config, "NEO4J_PASSWORD", None)
    monkeypatch.setattr(app_config.Config, "LLM_API_KEY", "x")
    assert gs.graph_store_available() is False
    assert gs.graph_store_unavailable_reason() == "NEO4J_PASSWORD not configured for GRAPH_BACKEND=graphiti"
    with pytest.raises(ValueError, match="NEO4J_PASSWORD"):
        gs.get_graph_store()


def test_zep_and_fake_keep_the_callers_chunking():
    assert gs.get_graph_store().preferred_chunking() is None  # fake, in tests


# ---------- memory updater: send outside the buffer lock ----------


def test_memory_updater_sends_without_holding_the_buffer_lock():
    from app.services.zep_graph_memory_updater import AgentActivity, ZepGraphMemoryUpdater

    lock_free_during_send = []

    class SlowStore:
        def add_text(self, graph_id, text):
            got = updater._buffer_lock.acquire(timeout=0.2)
            lock_free_during_send.append(got)
            if got:
                updater._buffer_lock.release()
            time.sleep(0.05)

    updater = ZepGraphMemoryUpdater("g", store=SlowStore())
    updater.SEND_INTERVAL = 0
    for i in range(updater.BATCH_SIZE):
        updater._activity_queue.put(
            AgentActivity(
                platform="twitter",
                agent_id=i,
                agent_name=f"a{i}",
                action_type="CREATE_POST",
                action_args={"content": "x"},
                round_num=1,
                timestamp="t",
            )
        )
    updater._running = False  # the loop drains the queue, then exits
    worker = threading.Thread(target=updater._worker_loop)
    worker.start()
    worker.join(timeout=10)
    assert lock_free_during_send == [True]
