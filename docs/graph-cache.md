# Graph snapshot cache

Full Zep graph reads (paginated node + edge lists) are cached on disk under `backend/uploads/graph_cache/<graph_id>/` to reduce Zep API usage and mitigate rate limits.

See also **[zep-footprint.md](./zep-footprint.md)** for browser polling, `refresh=true` usage, and graph memory batching.

## Behavior

- **GET** `/api/graph/data/<graph_id>` uses read-through cache when `GRAPH_SNAPSHOT_CACHE_ENABLED=1`.
- Query **`refresh=true`** forces a Zep fetch and re-primes the cache (authenticated, same ownership rules as today).
- Response headers:
  - `X-Glas-Graph-Cache`: `HIT` | `MISS` | `STALE` | `BYPASS` | `DISABLED`
  - `X-Glas-Graph-Cache-Age`: seconds (for HIT/STALE when known)
- If Zep returns an error (e.g. 429) and a snapshot exists within **stale max age**, the API may return **200** with cached data and `X-Glas-Graph-Cache: STALE`.

## Invalidation / freshness

- **`mutation_generation`**: file `mutation_generation` in the cache directory. Incremented when:
  - Graph enrichment completes at least one round (`GraphEnrichmentService`).
  - A graph-memory batch is successfully written (`ZepGraphMemoryUpdater`).
- A snapshot is valid only if its embedded generation matches the file (and soft **TTL** has not expired).
- **Build complete**: Celery task and synchronous build path call `write_snapshot` after `get_graph_data`.
- **Delete graph**: local cache directory is removed after Zep delete.

`ZepEntityReader.get_all_nodes` / `get_all_edges` reuse the same snapshot when it is a cache HIT (same generation + TTL rules).

## Environment variables

| Variable | Default | Meaning |
|----------|---------|---------|
| `GRAPH_SNAPSHOT_CACHE_ENABLED` | `1` | Master switch |
| `GRAPH_SNAPSHOT_TTL_SECONDS` | `604800` | Max age for a normal HIT (7 days; mutation-generation bumps are the primary invalidation, TTL is the time-based safety net) |
| `GRAPH_SNAPSHOT_STALE_MAX_AGE_SECONDS` | `604800` | Max age to serve STALE after Zep failure |
| `GRAPH_SNAPSHOT_MAX_DISK_MB` | `512` | Total quota; LRU eviction of oldest graph dirs (`0` = no quota enforcement) |
| `GRAPH_SNAPSHOT_SINGLEFLIGHT` | `1` | Serialize Zep fetches per `graph_id` in-process |

## Operations

- **Stale or wrong graph in UI**: use in-app graph refresh (sends `refresh=true`) or delete `uploads/graph_cache/<graph_id>/`.
- **Disable quickly**: set `GRAPH_SNAPSHOT_CACHE_ENABLED=0` and restart the API.

## On-disk format

- `snapshot.json`: API-shaped payload plus `_glas_cache_meta` (format version, unix time, mutation generation, content SHA-256). The meta key is stripped before responses.
- `mutation_generation`: single integer as text.

Do not add ad-hoc Zep list calls for the same data; extend this module if new read paths need caching.
