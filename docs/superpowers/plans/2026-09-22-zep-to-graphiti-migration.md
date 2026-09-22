# Plan: move the knowledge graph from Zep Cloud to self-hosted Graphiti

**Date:** 2026-09-22 · **Status:** proposed · **Parent plan:** `2026-09-22-jev-evidence-and-zep-independence.md` (Phase 4)

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
5. **Reranker.** Use `BGERerankerClient` (local `BAAI/bge-reranker-v2-m3`, about 570 MB downloaded on first use) only for the `cross_encoder` path, which is `zep_tools` search. Persona grounding uses RRF, which needs no model. If the download size or CPU latency is a problem, fall back to RRF everywhere and note the quality change.
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
