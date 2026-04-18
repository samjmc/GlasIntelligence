# Low-Zep footprint (client + graph memory)

This complements [graph-cache.md](./graph-cache.md) (server snapshot cache). It covers **browser polling**, **when `refresh=true` is sent**, **simulation graph memory**, and **backend batch tuning**.

## Frontend (`VITE_ZEP_*`)

Values are inlined at **Vite build time**. After changing them, **rebuild the frontend image** (see deployment runbook).

| Variable | Default (in code) | Meaning |
|----------|-------------------|---------|
| `VITE_ZEP_GRAPH_POLL_VISIBLE_MS` | `120000` | Graph poll interval when tab visible and graph not building |
| `VITE_ZEP_GRAPH_POLL_HIDDEN_MS` | `300000` | Interval when `document.hidden` (still schedules; fetch may be skipped) |
| `VITE_ZEP_GRAPH_POLL_DURING_BUILD_MS` | `8000` | Interval while `graph_building` / build phase |
| `VITE_ZEP_GRAPH_POLL_WHILE_SIMULATING_MS` | `0` | Auto-poll graph during simulation (`0` = off; manual refresh only) |
| `VITE_ZEP_GRAPH_SKIP_WHEN_HIDDEN` | `true` | Skip graph/status poll **requests** while tab hidden |
| `VITE_ZEP_STEP2_POLL_MS_INITIAL` | `2000` | Step 2 prepare/config polling (first ticks) |
| `VITE_ZEP_STEP2_POLL_MS_DECAY` | `5000` | Step 2 polling after 5 ticks (reduces chatter) |
| `VITE_ZEP_STEP3_STATUS_MS` | `4000` | Step 3 run status poll |
| `VITE_ZEP_STEP3_DETAIL_MS` | `6000` | Step 3 action detail poll |

### Operator presets

**Staging / low Zep traffic**

```env
VITE_ZEP_GRAPH_POLL_VISIBLE_MS=120000
VITE_ZEP_GRAPH_POLL_HIDDEN_MS=300000
VITE_ZEP_GRAPH_POLL_DURING_BUILD_MS=8000
VITE_ZEP_GRAPH_POLL_WHILE_SIMULATING_MS=0
VITE_ZEP_GRAPH_SKIP_WHEN_HIDDEN=true
```

**Faster graph UX during sim (more Zep reads)**

```env
VITE_ZEP_GRAPH_POLL_WHILE_SIMULATING_MS=600000
```

### `refresh=true` contract

Only **user-initiated** graph refresh should pass `refresh: true` to `getGraphData`. Timers and initial loads use the snapshot cache (`refresh: false` / omitted).

## Graph memory (simulation → Zep writes)

- **Default**: `enable_graph_memory_update` is **off** in the UI unless the user enables “Live graph memory” (stored in `sessionStorage` key `glas_pref_graph_memory`).
- **Backend batching** (when memory is on):

| Variable | Default | Meaning |
|----------|---------|---------|
| `ZEP_GRAPH_MEMORY_BATCH_SIZE` | `5` | Activities per batch per platform before `graph.add` |
| `ZEP_GRAPH_MEMORY_SEND_INTERVAL_SEC` | `0.5` | Sleep between batch sends in the worker loop |

Larger batches / longer intervals → fewer Zep writes and fewer cache generation bumps (often **better** cache hit rate); first write to Zep may appear later.

## Rollback

1. Revert or adjust `VITE_ZEP_*` / Docker build args and rebuild the frontend.
2. Set graph memory checkbox default via UI session clear, or redeploy prior frontend build.
3. Unset or restore `ZEP_GRAPH_MEMORY_*` on the API if you changed them.

## Verification checklist (manual / HAR)

1. Open a project with `graph_id`: count `GET /api/graph/data/...` over several minutes; should match configured intervals; **no** `refresh=true` unless the refresh control is used.
2. Hidden tab: request rate should drop when `VITE_ZEP_GRAPH_SKIP_WHEN_HIDDEN=true`.
3. Start simulation **without** graph memory: `POST` body contains `enable_graph_memory_update: false`.
4. Enable graph memory: `true` in body; logs note Zep graph memory when server enables it.

Automated Playwright coverage is gated on auth/session fixtures; use this checklist for production validation. The e2e test `zep-footprint.spec.js` only checks that the app shell loads so CI stays green without auth fixtures.
