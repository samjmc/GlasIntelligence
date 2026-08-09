# Static Demo Hosting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the GlasIntelligence demo as a fully static Cloudflare Pages bundle that replays recorded runs in the browser, with no backend, no vendor keys, and no paid hosting.

**Architecture:** A Flask `after_request` hook records one real run to a time-indexed JSON tape. The tape is committed to `frontend/public/demo/`. In the browser, a custom axios adapter and a `fetch` wrapper intercept every `/api/*` call and answer it from the tape using a virtual clock derived from the session ID. Nothing else in the application changes.

**Tech Stack:** Vue 3, Vite 7, axios 1.13, vitest 3, Playwright 1.52, Flask (backend recorder only), Cloudflare Pages.

**Spec:** `docs/superpowers/specs/2026-08-08-static-demo-hosting-design.md`

## Global Constraints

- Target watch time is **90 seconds** per scenario, end to end.
- Fixture budget is **15MB total per scenario**. Above that, stop and move fixtures out of git.
- The demo build runs with **no environment variables** except `VITE_DEMO_MODE=1`.
- `frontend/vite.config.js` sets `envDir: '..'` — env vars are read from the **repo root**, not `frontend/`.
- Frontend tests are co-located and match `src/**/*.{test,spec}.{js,ts}` (`frontend/vitest.config.js`).
- Add **no new frontend runtime dependencies**. Current deps: `@supabase/supabase-js`, `axios`, `d3`, `dompurify`, `posthog-js`, `vue`, `vue-router`.
- The demo must issue **zero requests to any origin other than its own**.
- Banner copy is exactly: **"Demo — replaying a recorded simulation"**.
- Never enable RLS on Supabase tables as part of this work. It is parked and enabling it without policies breaks the app.

## Deviations from the spec, and why

**One tape file per scenario, not five per-step files.** The spec proposed
`step1.json … step5.json` lazy-loaded per step. Requests do not partition cleanly by
step, so routing a request to the right file requires machinery whose only benefit is
a page-weight saving we cannot yet size. Task 3 measures the real tape. Split then, if
the number demands it. Until then one `tape.json` per scenario, loaded once.

**No `demo_` router guard.** The spec inherited this from Phase 3 of
`docs/demo-mode-plan.md`. It is dead work: `frontend/src/main.js` awaits `initAuth()`
before mounting, and with no Supabase key `initAuth()` sets
`authState.user = { id: 'local', email: 'local@dev' }`, so the guard at
`frontend/src/router/index.js:144` already passes every route.

**Static vs progressive is derived, not declared.** A key with one recorded entry is
static; a key with several is progressive. No endpoint list to maintain.

---

## File Structure

**Create:**

| Path | Responsibility |
| --- | --- |
| `frontend/src/demo/config.js` | Reads `VITE_DEMO_MODE`, exposes `isDemoMode` and `DEMO_SPEEDUP`. Single source of truth for "are we in demo mode". |
| `frontend/src/demo/sessionId.js` | Encode/decode `demo_<b64url(start_ms)>_<scenario>_<nonce>`. |
| `frontend/src/demo/tape.js` | Load a tape, normalise paths, index entries by key, resolve a request against the clock. Pure — no network beyond one `fetch`, no axios knowledge. |
| `frontend/src/demo/adapter.js` | Axios adapter that answers from `tape.js`. |
| `frontend/src/demo/fixtures/synthetic-tape.json` | Hand-authored 6-entry tape. The contract every other task tests against. |
| `frontend/public/demo/manifest.json` | Scenario list. |
| `frontend/public/demo/<scenario>/tape.json` | Recorded tape. Written by Task 3. |
| `frontend/public/fonts/` | Vendored woff2 files. |
| `backend/app/middleware/demo_recorder.py` | Flask `after_request` recorder. |
| `backend/tests/test_demo_recorder.py` | Recorder tests. |
| `.github/workflows/demo-e2e.yml` | Static demo build + Playwright origin assertion. |
| `e2e/tests/demo.spec.js` | Demo walkthrough and origin assertion. |

**Modify:**

| Path | Change |
| --- | --- |
| `frontend/src/api/index.js` | Pass `adapter` into `axios.create` when in demo mode. |
| `frontend/src/composables/useApi.js` | Route through the tape when in demo mode. |
| `frontend/index.html` | Remove three Google Fonts `<link>` tags. |
| `frontend/src/style.css` (or equivalent global sheet) | Add `@font-face` rules. |
| `frontend/src/views/Home.vue` | Scenario picker, hide upload control, hide credit badge. |
| `frontend/src/App.vue` | Demo banner. |
| `backend/app/__init__.py` | Register the recorder alongside `log_response` (line ~94). |
| `docs/demo-mode-plan.md` | Rewrite Phase 2 and 5, delete the gzip guidance. |

---

## Task 1: Demo config, session IDs, and the fixture contract

Establishes the tape format everything else is written against, plus the two smallest
pure modules. Nothing here touches the network.

**Files:**
- Create: `frontend/src/demo/config.js`
- Create: `frontend/src/demo/sessionId.js`
- Create: `frontend/src/demo/fixtures/synthetic-tape.json`
- Test: `frontend/src/demo/sessionId.test.js`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `isDemoMode: boolean`
  - `DEMO_SPEEDUP: number`
  - `encodeDemoId(startMs: number, scenario: string): string`
  - `decodeDemoId(id: string): { startMs: number, scenario: string } | null`
  - Tape JSON shape (below), consumed by Tasks 2, 3, 4, 5.

- [ ] **Step 1: Write the tape format fixture**

Create `frontend/src/demo/fixtures/synthetic-tape.json`. This file is the contract.
`create` appears once (static). `status` appears three times (progressive), with the
last entry terminal.

```json
{
  "schema_version": 1,
  "scenario": "synthetic",
  "duration_ms": 30000,
  "entries": [
    {
      "t_ms": 0,
      "method": "POST",
      "path": "/api/simulation/create",
      "status": 200,
      "body": { "success": true, "data": { "id": "sim-synthetic-1" } }
    },
    {
      "t_ms": 0,
      "method": "GET",
      "path": "/api/simulation/status/:id",
      "status": 200,
      "body": { "success": true, "data": { "runner_status": "running", "twitter_current_round": 0, "total_rounds": 2 } }
    },
    {
      "t_ms": 10000,
      "method": "GET",
      "path": "/api/simulation/status/:id",
      "status": 200,
      "body": { "success": true, "data": { "runner_status": "running", "twitter_current_round": 1, "total_rounds": 2 } }
    },
    {
      "t_ms": 20000,
      "method": "GET",
      "path": "/api/simulation/status/:id",
      "status": 200,
      "body": { "success": true, "data": { "runner_status": "completed", "twitter_current_round": 2, "total_rounds": 2 } }
    },
    {
      "t_ms": 0,
      "method": "GET",
      "path": "/api/session/:id",
      "status": 200,
      "body": { "success": true, "data": { "id": "sess-synthetic-1", "prompt": "synthetic scenario" } }
    },
    {
      "t_ms": 0,
      "method": "GET",
      "path": "/api/billing/can-research",
      "status": 200,
      "body": { "success": true, "data": { "research_credits": null, "is_paid": false } }
    }
  ]
}
```

- [ ] **Step 2: Write the failing session ID test**

Create `frontend/src/demo/sessionId.test.js`:

```js
import { describe, it, expect } from 'vitest'
import { encodeDemoId, decodeDemoId } from './sessionId'

describe('demo session IDs', () => {
  it('round-trips a start time and scenario', () => {
    const id = encodeDemoId(1754650000000, 'energy-price-cap')
    const decoded = decodeDemoId(id)
    expect(decoded).toEqual({ startMs: 1754650000000, scenario: 'energy-price-cap' })
  })

  it('produces a URL-safe id with the demo_ prefix', () => {
    const id = encodeDemoId(1754650000000, 'energy-price-cap')
    expect(id.startsWith('demo_')).toBe(true)
    expect(id).toMatch(/^[A-Za-z0-9_-]+$/)
  })

  it('produces a different id each call for the same inputs', () => {
    const a = encodeDemoId(1754650000000, 'energy-price-cap')
    const b = encodeDemoId(1754650000000, 'energy-price-cap')
    expect(a).not.toBe(b)
  })

  it('returns null for a non-demo id', () => {
    expect(decodeDemoId('550e8400-e29b-41d4-a716-446655440000')).toBeNull()
    expect(decodeDemoId('')).toBeNull()
    expect(decodeDemoId('demo_notbase64')).toBeNull()
  })

  it('returns null when the scenario segment is missing', () => {
    expect(decodeDemoId('demo_MTc1NDY1MDAwMDAwMA')).toBeNull()
  })
})
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
cd frontend && npm ci && npx vitest run src/demo/sessionId.test.js
```

Expected: FAIL — `Failed to resolve import "./sessionId"`.

- [ ] **Step 4: Write `sessionId.js`**

Create `frontend/src/demo/sessionId.js`:

```js
// Demo session IDs are stateless: they carry the demo's start time and the chosen
// scenario, so a page reload resumes at the right point with no server involved.
// Format: demo_<b64url(start_ms)>_<scenario>_<nonce>

const PREFIX = 'demo_'

function b64urlEncode(str) {
  return btoa(str).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function b64urlDecode(str) {
  const padded = str.replace(/-/g, '+').replace(/_/g, '/')
  return atob(padded + '='.repeat((4 - (padded.length % 4)) % 4))
}

export function encodeDemoId(startMs, scenario) {
  const nonce = Math.random().toString(36).slice(2, 10)
  return `${PREFIX}${b64urlEncode(String(startMs))}_${scenario}_${nonce}`
}

export function decodeDemoId(id) {
  if (typeof id !== 'string' || !id.startsWith(PREFIX)) return null

  const parts = id.slice(PREFIX.length).split('_')
  if (parts.length < 3) return null

  const [encodedStart, scenario] = parts

  let startMs
  try {
    startMs = Number(b64urlDecode(encodedStart))
  } catch {
    return null
  }
  if (!Number.isFinite(startMs)) return null

  return { startMs, scenario }
}
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
cd frontend && npx vitest run src/demo/sessionId.test.js
```

Expected: PASS, 5 tests.

- [ ] **Step 6: Write `config.js`**

Create `frontend/src/demo/config.js`:

```js
// Vite statically replaces import.meta.env.* at build time, so a production build
// with VITE_DEMO_MODE unset can dead-code-eliminate every demo branch.
// Note: vite.config.js sets envDir: '..', so these are read from the repo root.

export const isDemoMode = import.meta.env.VITE_DEMO_MODE === '1'

// Derived from the measured run length in Task 3: run_length_ms / 90000.
// 1 until a real tape exists.
export const DEMO_SPEEDUP = Number(import.meta.env.VITE_DEMO_SPEEDUP) || 1

export const DEMO_TARGET_MS = 90000
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/demo/
git commit -m "feat(demo): add session id codec, demo config, and tape format fixture"
```

---

## Task 2: Backend recorder

Written before the golden run so Sam can record as early as possible. Emits exactly the
Task 1 format.

**Files:**
- Create: `backend/app/middleware/demo_recorder.py`
- Create: `backend/tests/test_demo_recorder.py`
- Modify: `backend/app/__init__.py` (near the existing `log_response` at line ~94)

**Interfaces:**
- Consumes: the tape JSON shape from Task 1.
- Produces:
  - `normalise_path(path: str) -> str`
  - `init_recorder(app, out_path: str, scenario: str) -> None`
  - A `tape.json` on disk matching the Task 1 schema.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_demo_recorder.py`:

```python
import json

import pytest
from flask import Flask

from app.middleware.demo_recorder import init_recorder, normalise_path


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("/api/simulation/create", "/api/simulation/create"),
        ("/api/session/550e8400-e29b-41d4-a716-446655440000", "/api/session/:id"),
        ("/api/session/demo_MTc1NDY1MA_energy_ab12cd34", "/api/session/:id"),
        ("/api/graph/task/12345", "/api/graph/task/:id"),
        ("/api/graph/data/graph_abc123def456789?refresh=true", "/api/graph/data/:id"),
        # Regression: a long endpoint name is not an id. "suggest-followups" is
        # 17 characters, so a naive length-only rule collapses it to :id and
        # silently merges it with any sibling endpoint.
        ("/api/simulation/suggest-followups", "/api/simulation/suggest-followups"),
        ("/api/billing/can-research", "/api/billing/can-research"),
    ],
)
def test_normalise_path(raw, expected):
    assert normalise_path(raw) == expected


def test_recorder_writes_entries_in_tape_format(tmp_path):
    out = tmp_path / "tape.json"
    app = Flask(__name__)

    @app.route("/api/simulation/create", methods=["POST"])
    def create():
        return {"success": True, "data": {"id": "sim-1"}}

    init_recorder(app, str(out), scenario="test-scenario")

    with app.test_client() as client:
        client.post("/api/simulation/create", json={})

    tape = json.loads(out.read_text())

    assert tape["schema_version"] == 1
    assert tape["scenario"] == "test-scenario"
    assert len(tape["entries"]) == 1

    entry = tape["entries"][0]
    assert entry["method"] == "POST"
    assert entry["path"] == "/api/simulation/create"
    assert entry["status"] == 200
    assert entry["body"] == {"success": True, "data": {"id": "sim-1"}}
    assert entry["t_ms"] >= 0


def test_recorder_ignores_non_api_routes(tmp_path):
    out = tmp_path / "tape.json"
    app = Flask(__name__)

    @app.route("/healthz")
    def health():
        return {"ok": True}

    init_recorder(app, str(out), scenario="test-scenario")

    with app.test_client() as client:
        client.get("/healthz")

    assert json.loads(out.read_text())["entries"] == []


def test_recorder_skips_non_json_responses(tmp_path):
    out = tmp_path / "tape.json"
    app = Flask(__name__)

    @app.route("/api/report/download")
    def download():
        return "binary-ish", 200, {"Content-Type": "application/pdf"}

    init_recorder(app, str(out), scenario="test-scenario")

    with app.test_client() as client:
        client.get("/api/report/download")

    assert json.loads(out.read_text())["entries"] == []
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend && python -m pytest tests/test_demo_recorder.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.middleware.demo_recorder'`.

- [ ] **Step 3: Write the recorder**

Create `backend/app/middleware/demo_recorder.py`:

```python
"""Records a real run to a time-indexed tape the browser can replay.

Enabled only when DEMO_RECORD=1. Writes after every /api/* response so a crashed
run still leaves a usable partial tape.

normalise_path must stay byte-identical in behaviour to normalisePath() in
frontend/src/demo/tape.js. If one changes, change the other.
"""

import json
import os
import re
import time

SCHEMA_VERSION = 1

# A path segment is an ID if it is a UUID, a demo id, an all-digit id, or a long
# opaque token. Recorder and replayer share this rule, so a false positive is
# symmetric — but two distinct endpoints collapsing to one key would silently
# serve the wrong response, so the opaque rule requires at least one digit.
# Without that, "/api/simulation/suggest-followups" (17 chars) becomes
# "/api/simulation/:id".
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_DEMO = re.compile(r"^demo[_-]")
_DIGITS = re.compile(r"^\d+$")
_OPAQUE = re.compile(r"^(?=.*\d)[A-Za-z0-9_-]{16,}$")


def normalise_path(path: str) -> str:
    path = path.split("?", 1)[0]
    segments = path.split("/")
    out = []
    for seg in segments:
        if seg and (
            _UUID.match(seg) or _DEMO.match(seg) or _DIGITS.match(seg) or _OPAQUE.match(seg)
        ):
            out.append(":id")
        else:
            out.append(seg)
    return "/".join(out)


def init_recorder(app, out_path: str, scenario: str) -> None:
    start = time.monotonic()
    entries: list[dict] = []

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    def flush() -> None:
        tmp = out_path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(
                {
                    "schema_version": SCHEMA_VERSION,
                    "scenario": scenario,
                    "duration_ms": int((time.monotonic() - start) * 1000),
                    "entries": entries,
                },
                fh,
            )
        os.replace(tmp, out_path)

    @app.after_request
    def _record(response):
        from flask import request

        if not request.path.startswith("/api/"):
            return response
        if "json" not in (response.content_type or ""):
            return response

        try:
            body = json.loads(response.get_data(as_text=True))
        except (ValueError, UnicodeDecodeError):
            return response

        entries.append(
            {
                "t_ms": int((time.monotonic() - start) * 1000),
                "method": request.method,
                "path": normalise_path(request.path),
                "status": response.status_code,
                "body": body,
            }
        )
        flush()
        return response

    flush()
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd backend && python -m pytest tests/test_demo_recorder.py -v
```

Expected: PASS, 8 tests (5 parametrised + 3).

- [ ] **Step 5: Register the recorder**

In `backend/app/__init__.py`, immediately after the existing `log_response`
`@app.after_request` block (around line 98), add:

```python
    # Demo tape recorder. Off unless explicitly recording a golden run.
    if os.environ.get("DEMO_RECORD") == "1":
        from .middleware.demo_recorder import init_recorder

        init_recorder(
            app,
            out_path=os.environ.get("DEMO_TAPE_PATH", "demo-tape.json"),
            scenario=os.environ.get("DEMO_SCENARIO", "scenario-1"),
        )
        logger.info("Demo recorder enabled")
```

Confirm `import os` is already present at the top of the file; add it if not.

- [ ] **Step 6: Verify the app still starts without the recorder**

```bash
cd backend && python -c "from app import create_app; create_app(); print('ok')"
```

Expected: `ok`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/middleware/demo_recorder.py backend/tests/test_demo_recorder.py backend/app/__init__.py
git commit -m "feat(demo): record api traffic to a replayable tape"
```

---

## Task 3: Golden run and size measurement — **SAM ONLY**

Cannot be done by an agent. Needs Redis, four Celery workers, and all five vendor keys
on Sam's machine. This is the serial dependency for the whole project, and its output
is a number that may change the design.

**Files:**
- Create: `frontend/public/demo/<scenario>/tape.json`
- Create: `frontend/public/demo/manifest.json`

- [ ] **Step 1: Start the stack with recording on**

```bash
cd /Users/sammcdonnell/Documents/GlasIntelligence
docker compose up -d redis

cd backend
DEMO_RECORD=1 \
DEMO_SCENARIO=energy-price-cap \
DEMO_TAPE_PATH=../frontend/public/demo/energy-price-cap/tape.json \
  python run.py
```

Start the Celery workers and the frontend as normal in separate shells. The frontend
must run **without** `VITE_DEMO_MODE`, so it talks to the real backend through the
vite proxy at `localhost:5001` and the recorder sees genuine traffic.

- [ ] **Step 2: Run one scenario end to end in the browser**

Steps 1 through 5. Do not refresh. Let it finish.

- [ ] **Step 3: Measure the tape — this is the gate**

```bash
ls -lh frontend/public/demo/energy-price-cap/tape.json
python3 -c "import json;t=json.load(open('frontend/public/demo/energy-price-cap/tape.json'));print('entries',len(t['entries']),'duration_ms',t['duration_ms'])"
```

**STOP and report the numbers before continuing.**
- Under 15MB → commit the tape, continue.
- Over 15MB → do not commit. Move fixtures to Cloudflare R2 or a GitHub release asset and revise the spec first.

Record `duration_ms`. `VITE_DEMO_SPEEDUP` for Task 11 is `duration_ms / 90000`.

- [ ] **Step 4: Scrub the tape**

The repository is public and the tape carries whatever the real run passed through it.

```bash
grep -oE '(sk-[A-Za-z0-9-]+|eyJ[A-Za-z0-9._-]+|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+)' frontend/public/demo/energy-price-cap/tape.json | sort -u
```

Expected: no output. Any hit must be removed before the file is committed.

- [ ] **Step 5: Write the manifest**

Create `frontend/public/demo/manifest.json`, using the real `duration_ms` from Step 3:

```json
{
  "schema_version": 1,
  "scenarios": [
    {
      "id": "energy-price-cap",
      "title": "Energy price cap",
      "blurb": "Model the second-order effects of a retail energy price cap.",
      "prompt": "COPY VERBATIM the prompt typed in Step 2 — the picker fills this into the read-only prompt box, so any difference makes the demo describe a run it did not perform",
      "duration_ms": 0
    }
  ]
}
```

- [ ] **Step 6: Commit**

```bash
git add frontend/public/demo/
git commit -m "feat(demo): add recorded tape and manifest for the energy price cap scenario"
```

---

## Task 4: Tape loading, matching, and resolution

The core of the replayer. Pure logic plus one `fetch`. Testable with no browser and no
real tape.

**Files:**
- Create: `frontend/src/demo/tape.js`
- Test: `frontend/src/demo/tape.test.js`

**Interfaces:**
- Consumes: `decodeDemoId` (Task 1), the tape shape (Task 1), `DEMO_SPEEDUP` (Task 1).
- Produces:
  - `normalisePath(path: string): string`
  - `indexEntries(entries: Array): Map<string, Array>`
  - `resolve(index: Map, method: string, path: string, elapsedMs: number): { status: number, body: object }`
  - `loadTape(scenario: string): Promise<{ schema_version, scenario, duration_ms, entries }>`
  - `elapsedFor(sessionId: string, now: number): number`
  - Constant `NOT_RECORDED = 'DEMO_NOT_RECORDED'`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/demo/tape.test.js`:

```js
import { describe, it, expect } from 'vitest'
import { normalisePath, indexEntries, resolve, NOT_RECORDED } from './tape'
import synthetic from './fixtures/synthetic-tape.json'

describe('normalisePath', () => {
  it.each([
    ['/api/simulation/create', '/api/simulation/create'],
    ['/api/session/550e8400-e29b-41d4-a716-446655440000', '/api/session/:id'],
    ['/api/session/demo_MTc1NDY1MA_energy_ab12cd34', '/api/session/:id'],
    ['/api/graph/task/12345', '/api/graph/task/:id'],
    ['/api/graph/data/graph_abc123def456789?refresh=true', '/api/graph/data/:id'],
    // Regression: a long endpoint name is not an id.
    ['/api/simulation/suggest-followups', '/api/simulation/suggest-followups'],
    ['/api/billing/can-research', '/api/billing/can-research'],
  ])('normalises %s', (raw, expected) => {
    expect(normalisePath(raw)).toBe(expected)
  })

  // If this file and backend/app/middleware/demo_recorder.py disagree, the
  // recorded key and the requested key differ and every lookup misses. The
  // cases above are duplicated verbatim in
  // backend/tests/test_demo_recorder.py::test_normalise_path — change both or
  // neither.
  it('treats a demo session id as an id', () => {
    expect(normalisePath('/api/session/demo_a_b_c')).toBe('/api/session/:id')
  })
})

describe('resolve', () => {
  const index = indexEntries(synthetic.entries)

  it('returns the single entry for a static key regardless of time', () => {
    const a = resolve(index, 'POST', '/api/simulation/create', 0)
    const b = resolve(index, 'POST', '/api/simulation/create', 999999)
    expect(a.body.data.id).toBe('sim-synthetic-1')
    expect(b.body.data.id).toBe('sim-synthetic-1')
  })

  it('advances a progressive key with elapsed time', () => {
    expect(resolve(index, 'GET', '/api/simulation/status/demo_a_b_c', 0).body.data.twitter_current_round).toBe(0)
    expect(resolve(index, 'GET', '/api/simulation/status/demo_a_b_c', 10000).body.data.twitter_current_round).toBe(1)
    expect(resolve(index, 'GET', '/api/simulation/status/demo_a_b_c', 20000).body.data.twitter_current_round).toBe(2)
  })

  it('returns the entry in force between snapshots, not the next one', () => {
    expect(resolve(index, 'GET', '/api/simulation/status/demo_a_b_c', 9999).body.data.twitter_current_round).toBe(0)
    expect(resolve(index, 'GET', '/api/simulation/status/demo_a_b_c', 10001).body.data.twitter_current_round).toBe(1)
  })

  it('clamps past the end of the tape instead of throwing', () => {
    const r = resolve(index, 'GET', '/api/simulation/status/demo_a_b_c', 10 ** 9)
    expect(r.body.data.runner_status).toBe('completed')
  })

  it('clamps before the start of the tape', () => {
    const r = resolve(index, 'GET', '/api/simulation/status/demo_a_b_c', -5000)
    expect(r.body.data.twitter_current_round).toBe(0)
  })

  it('returns a structured not-recorded response for an unknown path', () => {
    const r = resolve(index, 'GET', '/api/does/not/exist', 0)
    expect(r.status).toBe(200)
    expect(r.body.success).toBe(false)
    expect(r.body.error).toBe(NOT_RECORDED)
  })

  it('distinguishes methods on the same path', () => {
    const r = resolve(index, 'DELETE', '/api/simulation/create', 0)
    expect(r.body.error).toBe(NOT_RECORDED)
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd frontend && npx vitest run src/demo/tape.test.js
```

Expected: FAIL — `Failed to resolve import "./tape"`.

- [ ] **Step 3: Write `tape.js`**

Create `frontend/src/demo/tape.js`:

```js
import { decodeDemoId } from './sessionId'
import { DEMO_SPEEDUP } from './config'

export const NOT_RECORDED = 'DEMO_NOT_RECORDED'
export const SCHEMA_VERSION = 1

// Must stay behaviourally identical to normalise_path() in
// backend/app/middleware/demo_recorder.py. If one changes, change the other.
// The opaque rule requires a digit: without it "/api/simulation/suggest-followups"
// (17 chars) would be treated as an id and merged with sibling endpoints.
const UUID = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/
const DEMO = /^demo[_-]/
const DIGITS = /^\d+$/
const OPAQUE = /^(?=.*\d)[A-Za-z0-9_-]{16,}$/

export function normalisePath(path) {
  return path
    .split('?')[0]
    .split('/')
    .map((seg) =>
      seg && (UUID.test(seg) || DEMO.test(seg) || DIGITS.test(seg) || OPAQUE.test(seg))
        ? ':id'
        : seg,
    )
    .join('/')
}

function keyFor(method, normalisedPath) {
  return `${method.toUpperCase()} ${normalisedPath}`
}

export function indexEntries(entries) {
  const index = new Map()
  for (const entry of entries) {
    const key = keyFor(entry.method, entry.path)
    if (!index.has(key)) index.set(key, [])
    index.get(key).push(entry)
  }
  for (const list of index.values()) list.sort((a, b) => a.t_ms - b.t_ms)
  return index
}

export function resolve(index, method, path, elapsedMs) {
  const list = index.get(keyFor(method, normalisePath(path)))

  if (!list || list.length === 0) {
    return {
      status: 200,
      body: { success: false, error: NOT_RECORDED, path: normalisePath(path) },
    }
  }

  // One recorded entry means the response never varied: return it whenever asked.
  if (list.length === 1) return { status: list[0].status, body: list[0].body }

  // Otherwise return the snapshot in force at elapsedMs, clamping at both ends.
  // Clamping is load-bearing: Step3Simulation.vue swallows errors and polls
  // forever, so running off the end of the tape must never throw.
  let chosen = list[0]
  for (const entry of list) {
    if (entry.t_ms <= elapsedMs) chosen = entry
    else break
  }
  return { status: chosen.status, body: chosen.body }
}

export function elapsedFor(sessionId, now = Date.now()) {
  const decoded = decodeDemoId(sessionId)
  if (!decoded) return 0
  return (now - decoded.startMs) * DEMO_SPEEDUP
}

const cache = new Map()

export async function loadTape(scenario) {
  if (cache.has(scenario)) return cache.get(scenario)

  const promise = (async () => {
    // One retry: a CDN hiccup on a static asset is usually transient, and the
    // alternative is a dead demo. A second failure is real and must surface.
    let res
    try {
      res = await fetch(`/demo/${scenario}/tape.json`)
      if (!res.ok) throw new Error(String(res.status))
    } catch {
      res = await fetch(`/demo/${scenario}/tape.json`)
    }
    if (!res.ok) throw new Error(`Demo tape for "${scenario}" failed to load (${res.status})`)

    const tape = await res.json()
    if (tape.schema_version !== SCHEMA_VERSION) {
      throw new Error(
        `Demo tape schema ${tape.schema_version} does not match expected ${SCHEMA_VERSION}`,
      )
    }

    tape.index = indexEntries(tape.entries)
    return tape
  })()

  // Evict on failure so a transient error does not poison the cache for the
  // lifetime of the page.
  promise.catch(() => cache.delete(scenario))

  cache.set(scenario, promise)
  return promise
}
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd frontend && npx vitest run src/demo/tape.test.js
```

Expected: PASS, 13 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/demo/tape.js frontend/src/demo/tape.test.js
git commit -m "feat(demo): resolve requests against a time-indexed tape"
```

---

## Task 5: Axios adapter and fetch shim

Wires the tape into both transports. After this task the application replays.

**Files:**
- Create: `frontend/src/demo/adapter.js`
- Test: `frontend/src/demo/adapter.test.js`
- Modify: `frontend/src/api/index.js`
- Modify: `frontend/src/composables/useApi.js`

**Interfaces:**
- Consumes: `loadTape`, `resolve`, `elapsedFor`, `NOT_RECORDED` (Task 4); `isDemoMode` (Task 1).
- Produces:
  - `demoAdapter(config): Promise<AxiosResponse>`
  - `demoFetch(url, options): Promise<Response>`
  - `activeScenario` getter/setter used by Task 6's picker.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/demo/adapter.test.js`:

```js
import { describe, it, expect, beforeEach, vi } from 'vitest'
import synthetic from './fixtures/synthetic-tape.json'

beforeEach(() => {
  vi.resetModules()
  global.fetch = vi.fn(async () => ({
    ok: true,
    status: 200,
    json: async () => synthetic,
  }))
})

describe('demoAdapter', () => {
  it('resolves with a valid axios response shape', async () => {
    const { demoAdapter, setActiveScenario } = await import('./adapter')
    setActiveScenario('synthetic')

    const res = await demoAdapter({ url: '/api/simulation/create', method: 'post' })

    expect(res).toHaveProperty('data')
    expect(res).toHaveProperty('status', 200)
    expect(res).toHaveProperty('statusText')
    expect(res).toHaveProperty('headers')
    expect(res).toHaveProperty('config')
    expect(res.data.data.id).toBe('sim-synthetic-1')
  })

  it('defaults to GET when no method is given', async () => {
    const { demoAdapter, setActiveScenario } = await import('./adapter')
    setActiveScenario('synthetic')

    // A UUID segment, so normalisePath collapses it to /api/session/:id.
    const res = await demoAdapter({ url: '/api/session/550e8400-e29b-41d4-a716-446655440000' })
    expect(res.data.data.prompt).toBe('synthetic scenario')
  })

  it('returns a not-recorded body rather than rejecting', async () => {
    const { demoAdapter, setActiveScenario } = await import('./adapter')
    setActiveScenario('synthetic')

    const res = await demoAdapter({ url: '/api/nope', method: 'get' })
    expect(res.status).toBe(200)
    expect(res.data.success).toBe(false)
    expect(res.data.error).toBe('DEMO_NOT_RECORDED')
  })

  it('never issues a network request for an api path', async () => {
    const { demoAdapter, setActiveScenario } = await import('./adapter')
    setActiveScenario('synthetic')

    await demoAdapter({ url: '/api/simulation/create', method: 'post' })

    const urls = global.fetch.mock.calls.map((c) => c[0])
    expect(urls).toEqual(['/demo/synthetic/tape.json'])
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd frontend && npx vitest run src/demo/adapter.test.js
```

Expected: FAIL — `Failed to resolve import "./adapter"`.

- [ ] **Step 3: Write `adapter.js`**

Create `frontend/src/demo/adapter.js`:

```js
import { loadTape, resolve, elapsedFor, NOT_RECORDED } from './tape'

let activeScenario = null
let activeSessionId = null

export function setActiveScenario(scenario, sessionId = null) {
  activeScenario = scenario
  activeSessionId = sessionId
}

function announceIfMissing(body, path) {
  if (body && body.error === NOT_RECORDED && typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('demo:not-recorded', { detail: { path } }))
  }
}

async function answer(method, url) {
  const tape = await loadTape(activeScenario)
  const elapsed = elapsedFor(activeSessionId, Date.now())
  const result = resolve(tape.index, method, url, elapsed)
  announceIfMissing(result.body, url)
  return result
}

// Axios calls the adapter with a normalised config and expects a promise resolving
// to a full response object. Replacing the adapter rather than patching methods
// covers the config-object call form used in api/graph.js, keeps the existing
// response interceptor working, and guarantees nothing falls through to the vite
// dev proxy at localhost:5001 when a fixture is missing.
export async function demoAdapter(config) {
  const method = (config.method || 'get').toUpperCase()
  const url = config.url || ''
  const { status, body } = await answer(method, url)

  return {
    data: body,
    status,
    statusText: 'OK',
    headers: {},
    config,
    request: null,
  }
}

export async function demoFetch(url, options = {}) {
  const method = (options.method || 'GET').toUpperCase()
  const { status, body } = await answer(method, String(url))

  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: 'OK',
    json: async () => body,
    text: async () => JSON.stringify(body),
  }
}
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd frontend && npx vitest run src/demo/adapter.test.js
```

Expected: PASS, 4 tests.

- [ ] **Step 5: Wire the adapter into axios**

In `frontend/src/api/index.js`, add these imports at the top, after the existing
`import { getAccessToken } from '../store/auth'`:

```js
import { isDemoMode } from '../demo/config'
import { demoAdapter } from '../demo/adapter'
```

Then change the `axios.create` call to:

```js
const service = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 300000,
  headers: { 'Content-Type': 'application/json' },
  ...(isDemoMode ? { adapter: demoAdapter } : {}),
})
```

Leave both interceptors and `requestWithRetry` exactly as they are. The adapter sits
below them, so `response.data` unwrapping and the `res.success === false` rejection
continue to work unchanged.

- [ ] **Step 6: Wire the shim into useApi**

In `frontend/src/composables/useApi.js`, add at the top:

```js
import { isDemoMode } from '../demo/config'
import { demoFetch } from '../demo/adapter'

const http = isDemoMode ? demoFetch : (...args) => fetch(...args)
```

Then replace every `fetch(` call in that file with `http(`.

- [ ] **Step 7: Run the full frontend suite**

```bash
cd frontend && npx vitest run
```

Expected: PASS. Existing `App.test.js`, `router/index.test.js` and
`config/zepFootprint.spec.js` must stay green — the demo branches are inert when
`VITE_DEMO_MODE` is unset.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/demo/adapter.js frontend/src/demo/adapter.test.js frontend/src/api/index.js frontend/src/composables/useApi.js
git commit -m "feat(demo): answer api calls from the tape via axios adapter and fetch shim"
```

---

## Task 6: Vendor the fonts

Prerequisite for Task 8's origin assertion, and the last external runtime dependency.

**Files:**
- Create: `frontend/public/fonts/*.woff2`
- Modify: `frontend/index.html`
- Modify: `frontend/src/style.css`
- Test: `e2e/tests/demo.spec.js` (Task 8 asserts this)

- [ ] **Step 1: Download the two families as woff2**

Latin subsets only. Plus Jakarta Sans weights 300/400/500/600/700; JetBrains Mono
400/500/600/700 — matching the weights the current `<link>` requests.

```bash
mkdir -p frontend/public/fonts
cd frontend/public/fonts
curl -sL -A "Mozilla/5.0" "https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" -o /tmp/gf.css
grep -oE 'https://fonts.gstatic.com[^)]+\.woff2' /tmp/gf.css | sort -u | while read -r url; do curl -sO "$url"; done
ls -la
```

- [ ] **Step 2: Remove the external links**

In `frontend/index.html`, delete these three lines:

```html
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
```

- [ ] **Step 3: Add `@font-face` rules**

Prepend to `frontend/src/style.css`, one block per downloaded file, substituting the
real filenames from Step 1:

```css
/* Vendored so the app makes no third-party requests. Previously loaded from
   fonts.googleapis.com, which was both a privacy leak and a rot vector. */
@font-face {
  font-family: 'Plus Jakarta Sans';
  font-style: normal;
  font-weight: 300 700;
  font-display: swap;
  src: url('/fonts/<plus-jakarta-file>.woff2') format('woff2');
}

@font-face {
  font-family: 'JetBrains Mono';
  font-style: normal;
  font-weight: 400 700;
  font-display: swap;
  src: url('/fonts/<jetbrains-file>.woff2') format('woff2');
}
```

- [ ] **Step 4: Verify no external references remain**

```bash
cd frontend && grep -rn "fonts.googleapis.com\|fonts.gstatic.com" index.html src/ && echo "FOUND — fix before continuing" || echo "clean"
```

Expected: `clean`.

- [ ] **Step 5: Build and eyeball the result**

```bash
cd frontend && npm run build && npm run preview
```

Open the preview URL. Headings and monospace log output must look unchanged.

- [ ] **Step 6: Commit**

```bash
git add frontend/public/fonts frontend/index.html frontend/src/style.css
git commit -m "feat: vendor webfonts so the app makes no third-party requests"
```

---

## Task 7: Demo UI — picker, banner, suppression

**Files:**
- Create: `frontend/src/components/DemoBanner.vue`
- Create: `frontend/src/components/DemoScenarioPicker.vue`
- Test: `frontend/src/components/DemoScenarioPicker.test.js`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/views/Home.vue`

**Interfaces:**
- Consumes: `isDemoMode` (Task 1), `encodeDemoId` (Task 1), `setActiveScenario` (Task 5), `manifest.json` (Task 3).
- Produces: a `select` event carrying `{ scenarioId, sessionId, prompt }`.

- [ ] **Step 1: Write the failing picker test**

Create `frontend/src/components/DemoScenarioPicker.test.js`:

```js
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import DemoScenarioPicker from './DemoScenarioPicker.vue'

const manifest = {
  schema_version: 1,
  scenarios: [
    { id: 'energy-price-cap', title: 'Energy price cap', blurb: 'Retail cap effects.', prompt: 'Model a cap', duration_ms: 120000 },
  ],
}

beforeEach(() => {
  global.fetch = vi.fn(async () => ({ ok: true, status: 200, json: async () => manifest }))
})

describe('DemoScenarioPicker', () => {
  it('renders a card per scenario from the manifest', async () => {
    const wrapper = mount(DemoScenarioPicker)
    await flushPromises()

    expect(wrapper.findAll('[data-test="scenario-card"]')).toHaveLength(1)
    expect(wrapper.text()).toContain('Energy price cap')
    expect(wrapper.text()).toContain('Retail cap effects.')
  })

  it('emits a demo session id and prompt when a card is clicked', async () => {
    const wrapper = mount(DemoScenarioPicker)
    await flushPromises()

    await wrapper.find('[data-test="scenario-card"]').trigger('click')

    const [payload] = wrapper.emitted('select')[0]
    expect(payload.scenarioId).toBe('energy-price-cap')
    expect(payload.prompt).toBe('Model a cap')
    expect(payload.sessionId).toMatch(/^demo_/)
  })

  it('shows an error state when the manifest fails to load', async () => {
    global.fetch = vi.fn(async () => ({ ok: false, status: 404, json: async () => ({}) }))

    const wrapper = mount(DemoScenarioPicker)
    await flushPromises()

    expect(wrapper.find('[data-test="picker-error"]').exists()).toBe(true)
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd frontend && npx vitest run src/components/DemoScenarioPicker.test.js
```

Expected: FAIL — cannot resolve `./DemoScenarioPicker.vue`.

- [ ] **Step 3: Write the picker**

Create `frontend/src/components/DemoScenarioPicker.vue`:

```vue
<template>
  <div class="demo-picker">
    <h2 class="demo-picker-title">Choose a worked example</h2>

    <p v-if="error" data-test="picker-error" class="demo-picker-error">
      Demo failed to load. Please reload the page.
    </p>

    <div v-else class="demo-picker-grid">
      <button
        v-for="s in scenarios"
        :key="s.id"
        data-test="scenario-card"
        class="demo-picker-card"
        @click="choose(s)"
      >
        <span class="demo-picker-card-title">{{ s.title }}</span>
        <span class="demo-picker-card-blurb">{{ s.blurb }}</span>
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { encodeDemoId } from '../demo/sessionId'
import { setActiveScenario } from '../demo/adapter'

const scenarios = ref([])
const error = ref(false)

const emit = defineEmits(['select'])

onMounted(async () => {
  try {
    const res = await fetch('/demo/manifest.json')
    if (!res.ok) throw new Error(`manifest ${res.status}`)
    scenarios.value = (await res.json()).scenarios
  } catch {
    error.value = true
  }
})

function choose(scenario) {
  const sessionId = encodeDemoId(Date.now(), scenario.id)
  setActiveScenario(scenario.id, sessionId)
  emit('select', { scenarioId: scenario.id, sessionId, prompt: scenario.prompt })
}
</script>

<style scoped>
.demo-picker-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 1rem;
}
.demo-picker-card {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 1.25rem;
  text-align: left;
  cursor: pointer;
  border: 1px solid var(--border-color, #333);
  border-radius: 8px;
  background: transparent;
  color: inherit;
}
.demo-picker-card:hover {
  border-color: var(--accent-color, #6ee7b7);
}
.demo-picker-card-title {
  font-weight: 600;
}
.demo-picker-card-blurb {
  opacity: 0.75;
  font-size: 0.9rem;
}
</style>
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd frontend && npx vitest run src/components/DemoScenarioPicker.test.js
```

Expected: PASS, 3 tests.

- [ ] **Step 5: Write the banner**

Create `frontend/src/components/DemoBanner.vue`:

```vue
<template>
  <div v-if="visible" class="demo-banner">
    <span>Demo — replaying a recorded simulation</span>
    <button class="demo-banner-dismiss" aria-label="Dismiss" @click="visible = false">&times;</button>
  </div>

  <div v-if="missing" class="demo-banner demo-banner-warn">
    <span>This part of the app is not included in the demo.</span>
    <button class="demo-banner-dismiss" aria-label="Dismiss" @click="missing = false">&times;</button>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

const visible = ref(true)
const missing = ref(false)

function onMissing() {
  missing.value = true
}

onMounted(() => window.addEventListener('demo:not-recorded', onMissing))
onUnmounted(() => window.removeEventListener('demo:not-recorded', onMissing))
</script>

<style scoped>
.demo-banner {
  position: sticky;
  top: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  padding: 0.5rem 1rem;
  font-size: 0.875rem;
  background: #1f2937;
  color: #e5e7eb;
}
.demo-banner-warn {
  background: #7c2d12;
}
.demo-banner-dismiss {
  background: none;
  border: none;
  color: inherit;
  font-size: 1.1rem;
  cursor: pointer;
}
</style>
```

- [ ] **Step 6: Mount the banner**

In `frontend/src/App.vue`, add to the script block:

```js
import { isDemoMode } from './demo/config'
import DemoBanner from './components/DemoBanner.vue'
```

and render it as the first element inside the root template element:

```vue
<DemoBanner v-if="isDemoMode" />
```

- [ ] **Step 7: Wire the picker into Home.vue and suppress paid UI**

In `frontend/src/views/Home.vue`:

Add to the script setup block:

```js
import { isDemoMode } from '../demo/config'
import DemoScenarioPicker from '../components/DemoScenarioPicker.vue'

function onDemoScenarioSelected({ sessionId, prompt }) {
  formData.value.simulationRequirement = prompt
  activeSessionId.value = sessionId
  localStorage.setItem(SESSION_KEY, sessionId)
}
```

Render the picker above the prompt field:

```vue
<DemoScenarioPicker v-if="isDemoMode" @select="onDemoScenarioSelected" />
```

Make the prompt field read-only in demo mode by adding `:readonly="isDemoMode"` to the
`simulationRequirement` textarea.

Hide the file-upload control by adding `v-if="!isDemoMode"` to its wrapper element.

Hide the credit badge at line ~381 by extending its existing condition:

```vue
<span v-if="!isDemoMode && isPaidUser && researchCredits !== null" class="research-credits-badge">{{ researchCredits }}</span>
```

No change is needed for the upgrade modal in `Step3Simulation.vue` (line ~344). It is
gated on `err.response?.status === 402 || respData?.error === 'insufficient_credits'`
at line ~668, and the tape never returns either, so it cannot fire in demo mode.
Verify this holds after Task 3 by confirming no recorded entry has status 402:

```bash
python3 -c "import json;t=json.load(open('frontend/public/demo/energy-price-cap/tape.json'));print([e['path'] for e in t['entries'] if e['status']==402] or 'none')"
```

Expected: `none`.

- [ ] **Step 8: Run the full suite and build**

```bash
cd frontend && npx vitest run && npm run lint && npm run build
```

Expected: tests PASS, lint clean, build succeeds.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/DemoBanner.vue frontend/src/components/DemoScenarioPicker.vue frontend/src/components/DemoScenarioPicker.test.js frontend/src/App.vue frontend/src/views/Home.vue
git commit -m "feat(demo): add scenario picker, banner, and paid-ui suppression"
```

---

## Task 8: Demo e2e and CI job

The origin assertion is the mechanical proof that the demo cannot rot.

**Files:**
- Create: `e2e/tests/demo.spec.js`
- Create: `.github/workflows/demo-e2e.yml`

- [ ] **Step 1: Write the e2e spec**

Create `e2e/tests/demo.spec.js`:

```js
import { test, expect } from '@playwright/test'

test('demo makes no third-party requests', async ({ page }) => {
  const external = []

  page.on('request', (req) => {
    const url = new URL(req.url())
    if (url.origin !== new URL(page.url() || 'http://localhost:4173').origin) {
      external.push(req.url())
    }
  })

  await page.goto('/')
  await page.waitForLoadState('networkidle')

  expect(external, `demo requested external origins:\n${external.join('\n')}`).toEqual([])
})

test('demo replays a scenario through to a report', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByText('Demo — replaying a recorded simulation')).toBeVisible()

  await page.locator('[data-test="scenario-card"]').first().click()
  await page.getByRole('button', { name: /start|run|begin/i }).first().click()

  // The tape is sped up to a 90s target, so allow generous headroom.
  await expect(page.getByText(/simulation complete/i)).toBeVisible({ timeout: 180000 })
})
```

- [ ] **Step 2: Write the CI workflow**

Create `.github/workflows/demo-e2e.yml`:

```yaml
name: Demo E2E

on:
  pull_request:
  push:
    branches: [main]

jobs:
  demo-e2e:
    name: Static demo build and replay
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
          cache-dependency-path: frontend/package-lock.json

      # No secrets, no .env, no backend. If this build needs a credential,
      # the demo has stopped being keyless and this job should fail.
      - name: Build the demo bundle
        run: npm ci && npm run build
        working-directory: frontend
        env:
          VITE_DEMO_MODE: '1'

      - name: Serve the bundle
        run: npx --yes serve -s dist -l 4173 &
        working-directory: frontend

      - name: Install Playwright
        run: npm ci && npx playwright install --with-deps chromium
        working-directory: e2e

      - name: Run demo tests
        run: npx playwright test tests/demo.spec.js
        working-directory: e2e
        env:
          BASE_URL: http://localhost:4173

      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: demo-e2e-results
          path: |
            e2e/test-results/
            e2e/playwright-report/
```

- [ ] **Step 3: Run the e2e locally**

```bash
cd frontend && VITE_DEMO_MODE=1 npm run build && npx serve -s dist -l 4173 &
cd e2e && npm ci && npx playwright install chromium && BASE_URL=http://localhost:4173 npx playwright test tests/demo.spec.js
```

Expected: both tests PASS. If the origin test fails, Task 6 is incomplete.

- [ ] **Step 4: Commit**

```bash
git add e2e/tests/demo.spec.js .github/workflows/demo-e2e.yml
git commit -m "test(demo): assert the static demo replays and makes no external requests"
```

---

## Task 9: Retire the dead deploy machinery

**Files:**
- Delete: `.github/workflows/deploy.yml`, `.github/workflows/add-ssh-key.yml`
- Delete: `docker-compose.prod.yml`, `docker-compose.staging.yml`
- Modify: `docs/demo-mode-plan.md`

- [ ] **Step 1: Confirm nothing references them**

```bash
grep -rn "deploy.yml\|add-ssh-key\|docker-compose.prod\|docker-compose.staging" --include="*.yml" --include="*.md" --include="*.sh" . | grep -v node_modules
```

Review every hit. Update any documentation reference before deleting.

- [ ] **Step 2: Delete**

```bash
git rm .github/workflows/deploy.yml .github/workflows/add-ssh-key.yml docker-compose.prod.yml docker-compose.staging.yml
```

- [ ] **Step 3: Revise the plan document**

In `docs/demo-mode-plan.md`:
- Phase 2: replace the Flask `replay.py` description with in-browser replay, pointing at `frontend/src/demo/`.
- Phase 3: delete the `POST /api/demo/start` bullet and the `demo_` router-guard bullet. Note the CTA generates the session ID client-side, and that a keyless build already reaches every route because `initAuth()` sets a local user.
- Phase 5: replace the Hetzner deploy with Cloudflare Pages Git integration.
- Delete the line advising gzipped JSONL — Cloudflare compresses `application/json` on the fly.
- Add a pointer to `docs/superpowers/specs/2026-08-08-static-demo-hosting-design.md`.

- [ ] **Step 4: Confirm CI is still coherent**

```bash
ls .github/workflows/
```

Expected: `ci.yml`, `demo-e2e.yml`, and any unrelated workflows. No deploy workflow.

- [ ] **Step 5: Commit**

```bash
git add -A .github/workflows docs/demo-mode-plan.md docker-compose.prod.yml docker-compose.staging.yml
git commit -m "chore: retire the hetzner deploy pipeline in favour of static hosting"
```

---

## Task 10: Cloudflare Pages setup — **SAM ONLY**

Dashboard work. No agent can do it, and it needs no GitHub secrets.

- [ ] **Step 1: Create the project**

Cloudflare dashboard → Workers & Pages → Create → Pages → Connect to Git → authorise
GitHub → select `samjmc/GlasIntelligence`.

- [ ] **Step 2: Configure the build**

| Setting | Value |
| --- | --- |
| Production branch | `main` |
| Root directory | `frontend` |
| Build command | `npm ci && npm run build` |
| Output directory | `dist` |

- [ ] **Step 3: Set environment variables**

In Settings → Environment variables, production:

- `VITE_DEMO_MODE` = `1`
- `VITE_DEMO_SPEEDUP` = `<duration_ms from Task 3, Step 3, divided by 90000>`

Set nothing else. No Supabase keys, no PostHog key, no Anthropic key. If the build
needs one, something has regressed.

- [ ] **Step 4: Deploy and verify**

Trigger a deploy. When it completes, open the `*.pages.dev` URL and confirm:
- The banner reads "Demo — replaying a recorded simulation".
- The scenario picker renders its cards.
- A full run reaches a report in roughly 90 seconds.
- DevTools → Network shows requests to the Pages origin only.
- A deep link such as `<url>/pricing` loads rather than 404ing, confirming the
  automatic SPA fallback.

- [ ] **Step 5: Note the URL**

Record the deployed URL in `docs/demo-mode-plan.md` and commit.

---

## Task 11: Second and third scenarios — **SAM ONLY, after Task 10 is live**

Deliberately last. The pipeline is proven end to end before more vendor credit is spent.

- [ ] **Step 1: Record scenario 2**

Repeat Task 3 with `DEMO_SCENARIO=<id>` and
`DEMO_TAPE_PATH=frontend/public/demo/<id>/tape.json`. Choose a visibly different
domain — if two tapes produce similar graphs and reports, three scenarios read as one
scenario with a broken picker.

- [ ] **Step 2: Measure and scrub**

Same gate as Task 3, Steps 3 and 4. 15MB budget. Secret scan must come back empty.

- [ ] **Step 3: Append to the manifest**

Add the scenario object to `scenarios` in `frontend/public/demo/manifest.json`.

- [ ] **Step 4: Verify the picker**

```bash
cd frontend && VITE_DEMO_MODE=1 npm run build && npm run preview
```

Confirm two cards render and each plays its own tape.

- [ ] **Step 5: Commit, then repeat for scenario 3**

```bash
git add frontend/public/demo/
git commit -m "feat(demo): add second scenario tape"
```

---

## Execution order and gates

```
Task 1 (contract) ──┬─► Task 2 (recorder) ──► Task 3 [SAM: golden run + SIZE GATE]
                    │                              │
                    └─► Task 4 (tape) ──► Task 5 (shims) ──► Task 7 (demo ui) ──┤
                                                                                 │
                        Task 6 (fonts) ────────────────────► Task 8 (e2e) ◄──────┤
                                                                                 │
                                             Task 9 (retire deploy) ─────────────┤
                                                                                 ▼
                                                            Task 10 [SAM: Cloudflare]
                                                                                 │
                                                                                 ▼
                                                            Task 11 [SAM: scenarios 2-3]
```

Tasks 4 through 9 run against the synthetic tape and need no recording. Task 3's size
measurement is a hard gate: over 15MB, stop and revise the spec before committing
fixtures to a public repository.
