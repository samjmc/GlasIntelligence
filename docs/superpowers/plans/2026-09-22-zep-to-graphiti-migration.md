# Plan: move the knowledge graph from Zep Cloud to self-hosted Graphiti

**Date:** 2026-09-22 · **Status:** proposed, **vetted 2026-09-22 (verdict: needs rework → reworked below)** · **G0.5 + G0 done 2026-09-24: GO** (next: G1, after PR #11 merges; PR #13 merged 2026-09-24) · **Parent plan:** `2026-09-22-jev-evidence-and-zep-independence.md` (Phase 4)

## Vet results (2026-09-22) — these override anything below that conflicts

Three independent read-only passes checked this plan against `main` at 837527d, the open PRs, and PyPI and Hugging Face metadata.

**Blocker — dependency conflict (new step G0.5).** `camel-oasis==0.2.5` pins **`neo4j==5.23.0`** and **`sentence-transformers==3.0.0`** exactly. Every graphiti-core release since 0.12.0 needs `neo4j>=5.26`, and the `[sentence-transformers]` extra needs `>=3.2.1`. OASIS really imports both: `oasis/social_agent/agent_graph.py:19` and `oasis/social_platform/recsys.py:27`. So `uv add graphiti-core` will not resolve. **G0.5:**
- **Option A (recommended):** in a scratch copy, add `[tool.uv] override-dependencies = ["neo4j>=5.26,<6", "sentence-transformers>=3.2.1,<4"]`. Both caps are mandatory: uncapped, uv picks neo4j 6.x and sentence-transformers 6.x, which drag in transformers 5. Then `uv lock`, run the full backend suite, and run an 8-round OASIS smoke (`scripts/jev_live_ab.py --rounds 8 --only off`). Accept only if the suite's failure set is unchanged and the smoke run has zero errors.
- **Option B (fallback if A breaks OASIS):** run Graphiti in its own venv as a small sidecar process that the app calls over localhost HTTP. The async bridge then disappears too, at the cost of one extra process.

**High — live graph memory is ON for every UI simulation today.** The API default is `False` (`simulation_run_routes.py:76`), but `frontend/src/components/Step3Simulation.vue:409` hard-codes `enable_graph_memory_update: true`. The sessionStorage key `glas_pref_graph_memory` that `docs/zep-footprint.md:45` describes does not exist in `frontend/src`. **This is a live Zep credit drain now**, so it moves to Phase 4.0 step 1 in the parent plan: the default becomes off, an explicit per-run opt-in, and a credit estimate is shown before starting.
The updater also sends while holding `_buffer_lock` (`zep_graph_memory_updater.py:370-382`). Graphiti's `add_episode` blocks until extraction finishes, so send outside the lock, and add memory to the Graphiti cost table (one episode per 5 actions × several DeepSeek calls).

**High — the "top-5 types for Zep" cap as written breaks things.** `Person` and `Organization` are appended *last* (`ontology_generator.py:407-425`). `graph_enrichment_service._CATEGORY_LABEL` (`:31-43`) sends 10 of its 11 categories to those two types. `zep_entity_reader.filter_defined_entities` (`:273-276`) drops `Entity`-only nodes, and `oasis_profile_generator` INDIVIDUAL/GROUP sets (`:169-178`) expect `person` / `organization`. **Fix:**
- keep `Person` + `Organization` + the top 3 specific types;
- remap dropped types to the fallbacks inside `add_nodes` labels;
- filter `source_targets` to the kept types.

**High — gate G1 AND the parent plan's Phase 4.0 on PR #11 merging.** PR #11 (CI health, 67 files) reformats `graph_builder.py`, `zep_tools.py`, `oasis_profile_generator.py`, `zep_entity_reader.py`, `zep_graph_memory_updater.py`, `ontology_generator.py`, `api/graph.py`, `config.py`, `zep_paging.py`, `graph_enrichment_service.py`, `tasks/graph_tasks.py`, `pyproject.toml` and `uv.lock`. The offline-interviews branch (not yet a PR) also edits `zep_tools.py` and `simulation_runner.py`, so add `simulation_runner.py` to the do-not-touch list until it merges.

**High — the G1 inventory is incomplete.** The real surface is **18 SDK call sites using 13 methods, live in 7 service files plus `utils/zep_paging.py`**. `ontology_generator.py:453` is only a code-generation string. Services are also constructed, or `Config.ZEP_API_KEY` is checked directly, in:
- `tasks/graph_tasks.py:38`, a Celery build path duplicating `api/graph.py`;
- `api/graph.py:396,484,708,716,758,764`;
- `api/simulation.py:63,75,101,107,135,143,463,1378,1391`;
- `api/simulation_entities.py:29,38,55,58,76,81`;
- `api/report.py:983,1056`;
- `api/report_tools_routes.py:41,97`;
- `services/report_agent.py:1017`;
- `services/simulation_manager.py:276,326`.

**G1 delta:**
- keep every service constructor signature, and resolve the store internally;
- replace every `ZEP_API_KEY` check with `graph_store_available()`;
- `oasis_profile_generator.py:205` builds a Zep client only when the key exists, and otherwise *silently* returns no grounding facts (`:300`), so it must use the store;
- `graph_builder.build_graph_async` / `_build_graph_worker` (`:53-185`) has no callers: delete it rather than migrate it.

**High — a CPU embedder or reranker would stall the single event loop.** sentence-transformers `encode` and the BGE reranker are synchronous. On the bridge loop they block every graph call: the build-time graph poll, the 30 s simulation auto-refresh, and 5 profile workers × 2 searches, each with a 30 s timeout that silently means "no grounding". Wrap both in `asyncio.to_thread`.

**High — the reranker download is ~2.2 GB, not 570 MB.** `BAAI/bge-reranker-v2-m3` `model.safetensors` is 2,166 MB; 568 M is its parameter count. `bge-small-en-v1.5` is 127 MB. Default `GRAPHITI_RERANKER=rrf`. The cross-encoder is opt-in once disk allows; C: now has 15 GB free after old clones were removed.

**High — tests would make live, paid calls.** `tests/conftest.py` keeps a real `LLM_API_KEY` if one is in the environment, and Sam's user env vars include `NEO4J_URI`. So a "skip unless NEO4J_URI" contract test would run on every local `pytest`. **Fix:**
- make Graphiti integration tests opt-in via `RUN_GRAPHITI_IT=1`;
- register an `integration` marker and add `addopts = -m "not integration"`;
- use `pytest.importorskip("graphiti_core")`;
- import `graphiti_store` lazily so app import never needs graphiti.

The planned "`ZEP_API_KEY` unset" guard cannot work, because `conftest.py:31` always sets a placeholder. Instead, monkeypatch `zep_cloud.client.Zep` to raise.

**Tests G1 will break** (list them as required edits):
- `test_graph_enrichment_materialize.py`: the `zep_client=` kwarg; asserts `AddNodeItem` reaches `client.graph.add_nodes` and `client.task.get.call_count`; patches `fetch_all_nodes`.
- `test_graph_cache_wiring.py`: constructs a real `Zep`, swaps `updater.client`, and patches `er.fetch_all_nodes/edges`.
- `test_jev_simulation.py:517`: patches `zep_entity_reader.Zep`.
- `test_zep_paging.py:11`: the import path changes.

**Medium:**
- **Snapshot cache is backend-blind.** The key is only `graph_id` (`graph_snapshot_cache.py:69-74`), with a 24 h TTL. Add `graph_backend` to the snapshot meta, bump `SNAPSHOT_FORMAT_VERSION`, and add `graph_backend` to the project record (no such field today).
- **Chunking lives in the callers:** `api/graph.py:491` and `graph_tasks.py:41`. The real default is the project's **300/30** (`project.py:49-50`), not 500/50. `preferred_chunk_size()` must be applied in both callers and override the stored project value. The Zep store's 700-byte target needs a **byte-aware** splitter, because `utils/file_parser.split_text_into_chunks` counts characters and backs off to sentence breaks.
- **Progress bands and timeouts assume Zep's separate wait stage.** `api/graph.py` uses 15–50% add and 50–75% wait, plus 600 s / 300 s polls. Redesign them for a blocking `add_texts`. The frontend only displays `task.message` / `progress` and parses neither. `Step1GraphBuild.vue:125` has static "via Zep" copy to update.
- **Historical facts.** `panorama_search` (`zep_tools.py:134-141,1196-1201`) depends on `invalid_at` / `expired_at`. Measure in G0 whether `add_episode_bulk` sets them; if not, use `add_episode` for the first build too, or accept the loss.
- **G3 cost is larger than stated.** The pharmacy dossier is **58,449 characters** (the tape's `research/status` `summary_md`), not 30k. At today's 300/30 chunking that is about 215 chunks × 1 credit, **≈ 215 credits** plus enrichment. Compute the exact figure with the credit ledger's dry-run on the real text before asking to spend it.
- **Production** (G5): the Hetzner pipeline was retired on 2026-08-10 (`579c7d9`, `6414ffd`); `docker-compose.prod.yml`, `deploy.yml` and `deploy.sh` no longer exist. Only GitHub Pages deploys, and there is no Zep secret anywhere. So G5 is "fix the README (lines 104-123, 156-211 describe the retired pipeline) and decide hosting from scratch", not "add a service to `docker-compose.prod.yml`".

**Low:**
- Also read: `processed`, `episode_ids`, `fact_type`, edge `attributes` / `created_at`, `add_nodes` `.nodes` / `.task_id`, and task `.status` / `.error`. The adapter value types must expose these, or the callers must change.
- Graphiti `get_by_uuid` raises when a node is missing, so the adapter must catch it and return `None`.
- `graph_builder` never calls `bump_mutation_generation`; `api/graph.py:605` writes the snapshot instead. Keep that behaviour, and don't claim "callers bump after writes".
- Set `GRAPHITI_TELEMETRY_ENABLED=false` in the process env **before** the first `graphiti_core` import (posthog is a hard dependency).
- The 750-line rule (`AGENTS.md:51`): split `zep_store.py` by concern (build / enrichment / read / memory).
- Force-rebuild and reset (`api/graph.py:128,439`) leave old graphs behind, and there is no cleanup job. Add a group-delete sweep once we host Neo4j.

**Corrected sequence:**
- G0: spike in a throwaway venv, with the constraints `torch==2.9.1` and `sentence-transformers<4` so it doesn't download a new torch.
- G0.5: resolvability.
- Wait for PR #11 (and the interviews PR).
- Then G1 → G2 → G3 → G4 → G5.

## G0.5 + G0 results (2026-09-24) — verdict: GO

Run in a scratch worktree (PR #11 head e44f351 + `main` 837527d), 0 Zep credits.

**G0.5 — resolvability: PASS, with ONE override, not two.**
- Change: add `"graphiti-core==0.30.2"` to `[project] dependencies`, and `[tool.uv] override-dependencies = ["neo4j>=5.26,<6"]`.
- The sentence-transformers override is **not needed**. graphiti-core needs it only for its `[sentence-transformers]` extra (the BGE reranker), and we default to RRF. So OASIS keeps its pinned `sentence-transformers==3.0.0` (`recsys.py:27` is untouched), and our local embedder uses 3.0.0 too.
- `uv lock` changed 3 packages only: +graphiti-core 0.30.2, neo4j 5.23.0 → 5.28.6, +posthog 7.60.0 (Graphiti telemetry; set `GRAPHITI_TELEMETRY_ENABLED=false`). torch stays 2.9.1+cpu; nothing re-downloaded.
- OASIS's only neo4j use is `agent_graph.py:19` (`from neo4j import GraphDatabase`) for its optional `backend="neo4j"`; the app uses the default `igraph`.
- Full backend suite: **458 passed** before and after (identical).
- OASIS smoke, `jev_live_ab.py --rounds 8 --only off` on neo4j 5.28.6: exit 0, 138 actions over 9 rounds, 0 ERROR lines in `simulation.log`.

**G0 — spike: GO on all three criteria.** Pharmacy dossier (58,449 chars, the tape's `summary_md`), the app's real 10-entity / 10-edge ontology, 2,000/100-char chunks (34 episodes), sequential `add_episode`, DeepSeek `deepseek-flash` with thinking disabled, `bge-small-en-v1.5` (384 dims) local embedder, RRF search, no reranker.

| Measure | Result | Go threshold |
|---|---|---|
| Episodes ingested | **34 / 34 (100%)** | ≥ 90% |
| Real stakeholder nodes | **35** in the stakeholder types (12 pharmacy bodies, 11 chains, 5 political, 3 named people, 4 patient groups), plus real bodies typed `Organization` (DHSC, NHS England, NICE, CQC, NHSBSA, King's Fund…) | ≥ 8 |
| Cost per build | **$0.15** (DeepSeek balance delta, ±$0.01; 674 calls, 2.28 M prompt tokens of which 0.77 M cache hits, 68 k completion) | ≤ $1 |
| Graph | 115 nodes (94 typed), 287 edges, 16 edges invalidated (so temporal facts work with `add_episode`) | — |
| Wall time | 456 s (7.6 min), ~13 s per episode, slowest 42 s | — |
| Search | 0.1–0.3 s per edge+node query; relevant facts on all 5 sample queries | — |
| Zep equivalent | ~215 credits for the same text | — |

**Finding that G2 MUST carry — DeepSeek mirrors the JSON schema.** In `json_object` mode Graphiti appends the Pydantic JSON schema to the prompt, and DeepSeek often answers in the schema's own shape: `{"title", "type", "description", "properties": {<the real values>}}`. Graphiti validates with `entity_type(**merged)`, which ignores extra keys, so the wrapper passes and a Map reaches Neo4j: `CypherTypeError: Property values can only be of primitive types`, and the **whole episode fails**. In the first dry run, 2 of 2 episodes failed this way.
- Fix (in our client, not in Graphiti): subclass `OpenAIGenericClient._generate_response`. Validate each reply with `response_model.model_validate`. If the reply has none of the model's fields and exactly one dict value, try that inner dict **first** (with all-optional fields the wrapper itself "validates" as an empty answer and silently loses the data). Return `model_dump(mode="json", exclude_unset=True)`, so only the model's own fields are returned. Retry up to 3 times on a real mismatch, then raise. Graphiti's own tenacity retry covers only JSON decode and rate-limit errors.
- Measured over the full build: **237 of 674 replies (35%) needed the unwrap**; 0 needed a retry; 0 gave up. So this is not an edge case. Without it Graphiti on DeepSeek does not work.
- DeepSeek thinking must be off here too. `OpenAIGenericClient` has no `extra_body`, so pass `client=` a thin wrapper whose `chat.completions.create` adds `extra_body={"thinking": {"type": "disabled"}}`.

**Other G0 facts for G2:**
- Graphiti's defaults for llm, embedder and cross-encoder are all OpenAI clients (`graphiti.py:219-227`). The spike passed a `CrossEncoderClient` that raises if called, which proves RRF recipes never call it.
- `EntityEdge.get_by_group_ids` **raises** `GroupsEdgesNotFoundError` on an empty group; it does not return `[]`. The adapter must catch it.
- The Neo4j driver logs `UnknownPropertyKeyWarning` for every query on a fresh DB. Set `neo4j.notifications` to ERROR.
- Graphiti creates free-form relation names outside `edge_types` (44 distinct names; the 10 typed ones are 216 of 287 edges, 75%). Callers that group by edge name must accept unknown names.
- Quality risks to track in G3: non-actor nodes typed `Organization` (Australia, Brexit, England, "Pharmacy First" as the top-degree node), and missed merges (CPE / Community Pharmacy England, NHSBSA / NHS Business Services Authority). The Jev actor filter was not run in the spike (no Jev provider configured); run it in G3.
- First load of the embedder downloads ~130 MB and took 52 s; later loads are local.

The spike script is `docs/superpowers/plans/2026-09-24-graphiti-g0-spike.py` (reference only, not app code). It is the starting point for `graphiti_store.py`, `ontology.py` and the client above.

## Why

Zep Cloud's free plan gives 10,000 credits a month (1 credit per 350 bytes per episode). It allows 5 custom types, and when the quota runs out the account drops to 5 requests/minute with no paid overage. Flex costs $125/month.

A graph build costs about 135 credits, and live graph memory costs about 2,000+ per simulation. The app's ontology asks for 10 entity types, double the free limit.

Graphiti ([getzep/graphiti](https://github.com/getzep/graphiti), `graphiti-core` 0.30.2, Apache-2.0, Python ≥3.10) is the open-source engine behind Zep Cloud. It has no credit meter and no type limit. We pay only for LLM tokens.

## What we give up (from Zep, for this app)

| Zep does it for us | With Graphiti we must |
|---|---|
| Runs extraction on its own tuned models, included in credits | Pay DeepSeek tokens (est. $0.15–0.40 per build) and own the quality risk |
| Queues ingestion; we poll `episode.get` | Run extraction inside our process; `add_episode(_bulk)` awaits until done |
| Hosts storage | Run Neo4j ourselves (local for dev; a host for prod) |
| Embeddings + rerankers included | Supply an embedder and a reranker explicitly |
| Web console | Use Neo4j Browser |

We do not use Zep's user/thread memory, context assembly, custom extraction instructions or fact ratings (checked 2026-09-22), so nothing is lost there.

## Goals

1. A full pipeline run (graph → prepare → simulate → report) makes **zero Zep calls** when `GRAPH_BACKEND=graphiti`.
2. Graph quality on the same dossier is **no worse for the stakeholders that matter**. Acceptance in G3.
3. Zep stays available behind the same interface (`GRAPH_BACKEND=zep`) as the rollback.
4. Local development on Windows needs no Docker.

**Non-goals:** changing the frontend graph view; changing snapshot-cache semantics; moving production hosting in this plan (G5 asks for a separate decision).

## The Zep surface today (17 operations, 8 files)

| Caller | Zep operation | Credits |
|---|---|---|
| `services/graph_builder.py` `create_graph` | `graph.create` | 0 |
| `graph_builder.set_ontology` | `graph.set_ontology` (Pydantic `EntityModel` / `EdgeModel` + `EntityEdgeSourceTarget`) | 0 |
| `graph_builder.add_text_batches` | `graph.add_batch` (EpisodeData text, 3 per batch) | ≥1 per 350 B |
| `graph_builder._wait_for_episodes` | `graph.episode.get` (poll `processed`) | 0 |
| `graph_builder.delete_graph` | `graph.delete` | 0 |
| `graph_builder._get_graph_info`, `get_graph_data` | `graph.node/edge.get_by_graph_id` via `utils/zep_paging.py` | 0 |
| `services/graph_enrichment_service.py` `_materialize_inventory` | `graph.add_nodes` (AddNodeItem) + `task.get` (poll) | per node |
| `graph_enrichment_service._send_episodes` / `_wait_for_episodes` | `graph.add_batch` + `graph.episode.get` | ≥1 per 350 B |
| `graph_enrichment_service._get_node_stats` | node listing | 0 |
| `services/zep_entity_reader.py` | node/edge listing, `node.get_entity_edges`, `node.get` | 0 |
| `services/zep_tools.py` search (`reranker="cross_encoder"`), `node.get`, listing | `graph.search`, `node.get` | 0 |
| `services/oasis_profile_generator.py` persona grounding (`reranker="rrf"`, edges + nodes) | `graph.search` ×2 | 0 |
| `services/zep_graph_memory_updater.py` | `graph.add` (combined activity text) | ≥1 per 350 B |
| `api/graph.py` | passes `builder.client` into enrichment | — |
| `services/ontology_generator.py` | imports Zep ontology models | — |

**Callers read Zep objects by attribute:** `uuid_` (sometimes `uuid`), `name`, `labels`, `summary`, `attributes`, `created_at`; edges add `fact`, `name`, `source_node_uuid`, `target_node_uuid`, `valid_at`, `invalid_at`, `expired_at`, `episodes`. Graphiti's `EntityNode` and `EntityEdge` carry the same fields, but name the id `uuid`. So adapter value objects that expose both `uuid_` and `uuid` keep every caller unchanged.

## Target design

```
backend/app/services/graph_store/
  __init__.py        get_graph_store() -> GraphStore   (by Config.GRAPH_BACKEND, default "zep")
  base.py            GraphStore protocol + value types GraphNode, GraphEdge, GraphSearchResult
  zep_store.py       ZepGraphStore: today's calls, moved verbatim; credit ledger lives here
  graphiti_store.py  GraphitiGraphStore
  async_bridge.py    one event loop on a daemon thread; run(coro, timeout) for sync callers
  ontology.py        app ontology dict -> (entity_types, edge_types, edge_type_map), shared by both stores
  fake_store.py      in-memory store for tests
```

**`GraphStore` protocol** (sync, because every caller is a sync Flask or worker thread):

- `create_graph(name, description) -> graph_id`
- `set_ontology(graph_id, ontology: dict)`
- `add_texts(graph_id, texts: list[str], progress_cb) -> None`. It blocks until processed, so callers stop polling.
- `add_nodes(graph_id, items: list[NewNode]) -> int`
- `add_memory(graph_id, text) -> None`
- `list_nodes(graph_id, max_items=2000) -> list[GraphNode]` and `list_edges(graph_id) -> list[GraphEdge]`
- `get_node(uuid) -> GraphNode | None` and `get_node_edges(uuid) -> list[GraphEdge]`
- `search(graph_id, query, scope: "edges" | "nodes", limit, reranker: "rrf" | "cross_encoder") -> GraphSearchResult`
- `delete_graph(graph_id)`

### Zep → Graphiti mapping (verified against graphiti-core source, 2026-09-22)

| Operation | Graphiti | Notes |
|---|---|---|
| create | none; `graph_id` becomes the `group_id` on every node and edge | Name and description already live in the project record |
| set_ontology | none stored. Build the types once and pass `entity_types=`, `edge_types=` and `edge_type_map=` on **every** `add_episode(_bulk)` | Cache the built classes per `graph_id` in the store, and persist the ontology dict in `projects/<id>` (already saved) |
| add_texts | `await graphiti.add_episode_bulk([RawEpisode(name, content, source=EpisodeType.text, source_description, reference_time)], group_id=graph_id, entity_types, edge_types, edge_type_map)` | Returns when done. Feed it sub-batches of ~5 so progress can be reported |
| add_memory | `await graphiti.add_episode(..., group_id=graph_id, source=EpisodeType.text)` | Batch ~10 agent actions per episode |
| add_nodes | `EntityNode(name, group_id, labels=["Entity", label], summary, attributes)`, then `await node.generate_name_embedding(embedder)` and `await node.save(driver)` | No dedup: keep the app's name-based `_find_missing_entities` |
| list_nodes / list_edges | `EntityNode.get_by_group_ids(driver, [gid], limit, uuid_cursor)` / `EntityEdge.get_by_group_ids(...)` | Cursor = last uuid received (ordered by uuid DESC) |
| get_node / get_node_edges | `EntityNode.get_by_uuid(driver, uuid)` / `EntityEdge.get_by_node_uuid(driver, uuid)` | |
| search | `await graphiti.search_(query, config=RECIPE.model_copy(update={"limit": n}), group_ids=[gid])` | edges+rrf → `EDGE_HYBRID_SEARCH_RRF`; edges+cross_encoder → `EDGE_HYBRID_SEARCH_CROSS_ENCODER`; same for nodes |
| delete | `await Node.delete_by_group_id(driver, gid)` | From `graphiti_core.nodes` |
| startup | `await graphiti.build_indices_and_constraints()` once; set `GRAPHITI_TELEMETRY_ENABLED=false` | |

### Decisions and why

1. **Async bridge.** Graphiti is async-only, and the Neo4j async driver is bound to the loop that created it. So run one long-lived loop on a daemon thread, build `Graphiti` inside it, and have sync callers use `asyncio.run_coroutine_threadsafe(...).result(timeout)`. Never call `asyncio.run` per request.
2. **LLM = DeepSeek-V4.1-Flash through `OpenAIGenericClient(config=LLMConfig(api_key, base_url, model="deepseek-flash"), structured_output_mode="json_object")`.** DeepSeek rejects `json_schema`. In `json_object` mode Graphiti puts the schema in the prompt, so the output shape is NOT enforced. This is the main quality risk, and G0 measures it before anything else is built.
3. **Pass all three clients explicitly** (llm, embedder, cross-encoder). Graphiti's defaults for each are OpenAI clients that would fail without an OpenAI key, or silently use one if present.
4. **Embedder.** graphiti-core has no local embedder class. Options:
   - **(a)** A ~40-line `EmbedderClient` subclass wrapping `sentence-transformers`, using a small model (for example `BAAI/bge-small-en-v1.5`, 384 dimensions, about 130 MB). Pure pip, no extra server. **Recommended.**
   - **(b)** Ollama running locally, via `OpenAIEmbedder(base_url=...)`.
   - **(c)** A hosted API (Voyage or Gemini).

   Whatever we pick, set `EMBEDDING_DIM` to match. Store the model name and dimension in a `graph_store_meta` node, and refuse to start on a mismatch, because mismatched vectors fail silently.
5. **Reranker.** *(Vet: the model is ~2.2 GB, not 570 MB, so default to RRF; see the Vet results above.)* Use `BGERerankerClient` (local `BAAI/bge-reranker-v2-m3`) only for the `cross_encoder` path, which is `zep_tools` search. Persona grounding uses RRF, which needs no model. If the download size or CPU latency is a problem, fall back to RRF everywhere and note the quality change.
6. **Ontology** (`ontology.py`), shared by both stores:
   - Build Pydantic models from the generator's dict.
   - Extend the reserved-name list to `uuid, name, group_id, labels, created_at, summary, attributes, name_embedding`. Graphiti raises `EntityTypeValidationError` on a clash; today's Zep list lacks `labels`, `attributes` and `name_embedding`.
   - Map each `source_targets` pair to an `edge_type_map[(source, target)]` entry.
   - The Zep store applies the 5-type cap (`ZEP_MAX_CUSTOM_TYPES`). The Graphiti store sends all 10.
7. **Chunking.** Zep store: ≤700-byte chunks, to fit whole 2-credit units. Graphiti store: ~2,000-character chunks, because cost scales with LLM calls, not bytes. So the chunk size belongs to the store: `store.preferred_chunk_size()`.
8. **Concurrency.** Set `SEMAPHORE_LIMIT=5` (default 10) so DeepSeek doesn't return 429s. Make it configurable.
9. **Silent-failure guards**, in the Graphiti store, after every `add_texts`:
   - node and edge counts for the group must grow;
   - an empty result is an error, not a success;
   - log episodes sent vs. episodes stored.
10. **Snapshot cache.** Unchanged. Callers still call `bump_mutation_generation(graph_id)` after writes, and the store is transparent to the cache.
11. **Rollback.** Set `GRAPH_BACKEND=zep`. Graphs built on one backend cannot be read by the other. The project record stores `graph_backend`, and reading a graph on the wrong backend gives a clear error.

## Phases

Each phase ends green. The full backend suite's failure set must equal `main`'s at every step.

### G0 — Go/no-go spike (≈half a day, 0 Zep credits, ≈$1 DeepSeek)
- Install Neo4j Community 5.26 LTS plus JDK 21 natively. Run `neo4j console`, or `neo4j windows-service install`.
- Install `graphiti-core[sentence-transformers]==0.30.2` in a **throwaway venv**, not the project lockfile, because the CI session is regenerating it.
- Build one graph from the pharmacy dossier text. Find the source in G0: the tape's research payload `summary_md` if it was recorded, else `docs/reports/pharmacy_first_caps_report_EN.md` as a stand-in. Use the app's 10-type ontology, DeepSeek `json_object` mode, the sentence-transformers embedder, and RRF search.
- Measure: episodes OK vs. parse failures, entity and edge counts, actor share (using the Jev actor filter), wall time, DeepSeek cost (balance delta), and 5 sample searches.
- **Go if:** ≥ 90% of episodes are ingested without an unrecoverable parse error, ≥ 8 real stakeholder nodes, and a build costs ≤ $1.
- **No-go** → record why. Then either try `deepseek-v4-pro` for extraction only, or stop and keep Zep with the Phase 4.0 credit guard.

### G1 — Interface + Zep adapter (no behaviour change, 0 credits)
- Move all 17 operations behind `GraphStore`. `ZepGraphStore` contains today's code verbatim, including the poll loops and `task.get`.
- The callers (`graph_builder`, `graph_enrichment_service`, `zep_entity_reader`, `zep_tools`, `oasis_profile_generator`, `zep_graph_memory_updater`, `api/graph.py`) receive a store instead of constructing `Zep()`.
- Add `FakeGraphStore`, and rewrite Zep-mocking tests to use it where that is simpler.
- A guard test runs the suite with `ZEP_API_KEY` unset and zero network, and checks that no test constructs `zep_cloud.Zep`.
- **Sequencing:** `zep_tools.py` is shared with the offline-interviews PR. Rebase after it merges, and do not touch `interview_agents`.

### G2 — Graphiti adapter (0 credits)
- Implement `GraphitiGraphStore`, `async_bridge.py` and `ontology.py`, following the mapping table.
- Add dependencies (`graphiti-core[sentence-transformers]` pinned, `neo4j`) **after the CI session's lockfile PR merges**, using `uv add`. Then `uv lock`, commit, and check that `uv sync --frozen` works on a clean clone.
- **Contract tests:** one test module runs the same scenarios against `FakeGraphStore` always, and against `GraphitiGraphStore` when `NEO4J_URI` is set (integration marker, skipped in CI). The scenarios: create → ontology → add_texts → list → search → get_node → get_node_edges → add_nodes → delete (and the group is empty afterwards).
- Config: `GRAPH_BACKEND`, `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` (a user-level env var, never a file), `GRAPHITI_SEMAPHORE_LIMIT`, `GRAPHITI_EMBED_MODEL`, `GRAPHITI_EMBED_DIM`, `GRAPHITI_RERANKER` (`bge` | `rrf`). Add them to `.env.example`.

### G3 — Head-to-head on one dossier (**one Zep build ≈100–135 credits: Sam's OK required**)
- Build the same dossier on both backends with the same ontology. Zep receives its 5 capped types.
- Compare node and edge counts, stakeholder names found by both or by only one, actor share (Jev actor filter), the persona-grounding search hit rate (at least one relevant fact per agent), build time, and cost.
- **Accept if:** the Graphiti actor count is within 20% of Zep's; Graphiti finds every stakeholder Zep finds among the top 10 by degree; the search hit rate is ≥ 90%; and the build costs ≤ $1.

### G4 — End-to-end on Graphiti (0 Zep credits)
- Run graph → prepare → simulate (8 rounds, `jev_live_ab.py`-style) → report with `GRAPH_BACKEND=graphiti`.
- Assert zero Zep calls: `ZepGraphStore` raises if constructed while the backend is `graphiti`.
- Read the report and compare it with a Zep-era report. Its grounding section must cite graph facts.

### G5 — Switch the default and document (0 credits)
- Make `GRAPH_BACKEND=graphiti` the development default. Update `README.md`, `AGENTS.md` and `docs/zep-footprint.md` with a Neo4j setup section.
- Production hosting is **a separate decision for Sam**. Options:
  - a Neo4j container next to the API in `docker-compose.prod.yml`;
  - Neo4j AuraDB Free (it pauses after 3 idle days; fine for a demo);
  - keep Zep in production and use Graphiti only for development and testing.

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| DeepSeek `json_object` output breaks Graphiti's parsers | Medium | Measured in G0 before any build-out; fallback is to use `deepseek-v4-pro` for extraction only |
| Silent bulk-ingest drops or embedding-dimension mismatch | Medium | Count guards after each `add_texts`; the dimension sentinel refuses to start on a mismatch |
| Our own process does the extraction work, so builds are slower | High | Already a thread today; progress reported per sub-batch; semaphore tuned |
| Reranker model download (570 MB) and CPU latency | Medium | RRF fallback via `GRAPHITI_RERANKER=rrf` |
| Behaviour drift in callers during G1 | Low | Verbatim move; full suite failure set compared with `main` |
| Lockfile conflict with the CI session | High if unsequenced | G2 waits for that PR |

## Cost summary

| Step | Zep credits | Money |
|---|---|---|
| G0 | 0 | ~$1 DeepSeek |
| G1, G2 | 0 | 0 |
| G3 | ~100–135 (≈1% of the month) | ~$1 DeepSeek |
| G4 | 0 | ~$1 DeepSeek |
| Per graph build afterwards | 0 | ~$0.15–0.40 DeepSeek (G0 measures the real figure) |

## Decisions Sam needs to make

1. OK to install Neo4j 5.26 + JDK 21 on this PC (G0).
2. OK to spend about 135 Zep credits on the single comparison build (G3).
3. Production hosting (G5): a Neo4j container, AuraDB Free, or keep Zep in production.
