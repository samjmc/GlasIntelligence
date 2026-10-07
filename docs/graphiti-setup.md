# Knowledge graph setup: Graphiti on Neo4j

Glas Intelligence keeps its knowledge graph in **Graphiti** (the open-source engine behind Zep) on a **Neo4j** database that you run yourself. This is the default (`GRAPH_BACKEND=graphiti`).

- **No metered service.** You pay only for the LLM tokens used to extract entities. A 58,000-character research dossier cost about **$0.15** to build on DeepSeek (measured 2026-09-24). On Zep Cloud's free plan, the same build would cost 287 of the 10,000 monthly credits.
- **Zep Cloud is still supported.** Set `GRAPH_BACKEND=zep` and `ZEP_API_KEY` (see [the end of this page](#switching-to-zep-cloud)).

The design, the measurements and the history are in [`superpowers/plans/2026-09-22-zep-to-graphiti-migration.md`](superpowers/plans/2026-09-22-zep-to-graphiti-migration.md).

## What you need

| Item | Version | Notes |
|---|---|---|
| Neo4j Community | 5.26 LTS (tested: 5.26.31) | Any 5.26+ should work. |
| Java | 21 | Neo4j 5.26 needs JDK 21. |
| An OpenAI-compatible LLM | e.g. DeepSeek `deepseek-flash` | The same `LLM_*` settings the rest of the app uses. It must support `response_format={"type": "json_object"}`. |
| Disk | about 130 MB, plus the database | The local embedding model (`BAAI/bge-small-en-v1.5`) downloads on first use. |

The Python dependencies (`graphiti-core`, `sentence-transformers`) are in `backend/pyproject.toml`; `uv sync` installs them.

## Install Neo4j

### Windows, without admin rights

1. Download two ZIPs and unpack them into a folder you own, e.g. `%USERPROFILE%\tools`:
   - Eclipse Temurin **JDK 21**, from [adoptium.net](https://adoptium.net/temurin/releases/?version=21).
   - **Neo4j Community 5.26**, from [neo4j.com/deployment-center](https://neo4j.com/deployment-center/). Pick the Windows ZIP of the 5.26 LTS.
2. Set user environment variables (no admin needed). `JAVA_HOME` points to the JDK folder, and `NEO4J_HOME` to the Neo4j folder.
3. Optional, for a laptop: add these lines to `%NEO4J_HOME%\conf\neo4j.conf`:
   ```
   server.memory.heap.initial_size=256m
   server.memory.heap.max_size=1g
   server.memory.pagecache.size=256m
   server.default_listen_address=127.0.0.1
   ```
4. Set the database password **before** the first start. Choose a long random password:
   ```powershell
   & "$env:NEO4J_HOME\bin\neo4j-admin.bat" dbms set-initial-password '<your password>'
   ```
5. Start Neo4j: `& "$env:NEO4J_HOME\bin\neo4j.bat" console`. Without admin rights it cannot run as a Windows service, so it stops when you log off or restart. Start it again after each restart. A small script that starts it hidden in the background is handy.

### Linux or macOS (Docker)

```bash
docker run -d --name neo4j -p 7687:7687 -p 7474:7474 \
  -e NEO4J_AUTH=neo4j/<your password> \
  -v neo4j-data:/data neo4j:5.26-community
```

## Configure the app

Keep `NEO4J_PASSWORD` in a **user-level environment variable**, not in a `.env` file.

| Setting | Default | Meaning |
|---|---|---|
| `GRAPH_BACKEND` | `graphiti` | `graphiti`, `zep`, or `fake` (in memory, tests only) |
| `NEO4J_URI` | `bolt://localhost:7687` | |
| `NEO4J_USER` | `neo4j` | |
| `NEO4J_PASSWORD` | (none) | **Required.** Without it the graph routes return "NEO4J_PASSWORD not configured". |
| `GRAPHITI_LLM_MODEL` | empty = `LLM_MODEL_NAME` | A different model for extraction only. |
| `GRAPHITI_EMBED_MODEL` / `GRAPHITI_EMBED_DIM` | `BAAI/bge-small-en-v1.5` / `384` | Recorded in the database on first use. A different model on the same database **is refused**, because mixed vectors would break search without any error. |
| `GRAPHITI_MAX_COROUTINES` | `5` | Parallel LLM calls per episode. Higher values draw rate-limit errors from DeepSeek. |
| `GRAPHITI_CHUNK_SIZE` / `GRAPHITI_CHUNK_OVERLAP` | `2000` / `100` | Graphiti cost follows LLM calls per chunk, so it uses larger chunks than Zep. |
| `GRAPHITI_EPISODE_TIMEOUT_SEC` | `300` | Time limit for one chunk's extraction. |
| `GRAPHITI_MEMORY_BATCH_SIZE` | `20` | Live graph memory: simulation activities per episode. |
| `GRAPH_MEMORY_DRAIN_TIMEOUT_SEC` | `1200` | How long a report waits for a run's live graph memory to finish writing. |

## Check that it works

From `backend/`, with Neo4j running and the settings above in your environment:

```bash
RUN_GRAPHITI_IT=1 uv run python -m pytest tests/test_graph_store_contract.py -v
```

This builds small throwaway graphs, extracts typed entities, searches them and deletes them. It costs a few cents of LLM tokens. All tests should pass. Without `RUN_GRAPHITI_IT=1`, these tests run on the in-memory store only.

## What to expect

- **The first graph call after the backend starts takes about a minute.** It loads the embedding model and checks the database indexes. Later calls reuse them.
- **A graph build takes several minutes.** The pharmacy dossier (34 chunks) took about 7 minutes. Each chunk is extracted before the next one starts, so progress moves chunk by chunk.
- **Search uses RRF ranking.** The optional cross-encoder reranker is a 2.2 GB download and is not used.
- **Graphs do not move between backends.** A graph built on Zep is not in Neo4j. Opening it with `GRAPH_BACKEND=graphiti` gives a clear "not in this Neo4j database" error. Rebuild the graph from the project instead.
- **Live graph memory** (`enable_graph_memory_update`) writes agent activity to the graph during a simulation. It is off by default, and the UI always sends it off. When it is on:
  - Activities go in batches of `GRAPHITI_MEMORY_BATCH_SIZE` (default 20). Measured on a real run, that is about 75 activities a minute at 2.3x fewer tokens than batches of 5.
  - Likes and reposts quote only the first 80 characters of the post. Searches, trend clicks and refreshes are not written.
  - Writing continues after the run ends. **A report waits** until the run's memory is written (up to `GRAPH_MEMORY_DRAIN_TIMEOUT_SEC`, default 20 minutes), so it can search what the agents did.

## Switching to Zep Cloud

Set `GRAPH_BACKEND=zep` and `ZEP_API_KEY`. Zep is metered: each text episode costs 1 credit per 350 bytes. The app's default chunking is 300/30 characters, so 1 credit per chunk; the 58k-character dossier costs about 287 credits. The free plan has 10,000 credits a month. The tests never call Zep.

## Production

Decided on 2026-10-05: production runs Neo4j Community as a container next to the API, on one Hetzner server, with Docker Compose. The kit is in `deploy/`, and the runbook is [hosting.md](hosting.md).
