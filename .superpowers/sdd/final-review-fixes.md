# Final Pre-Merge Review Fixes

Date: 2026-08-11  
Branch: feat/static-demo-hosting  
Worktree: /Users/sammcdonnell/Documents/GlasIntelligence-demo

---

## CRITICAL 1 — scheduleSessionSave() fires in demo mode, watchdog triggers at t≈3 s

**Root cause:** `scheduleSessionSave()` only gated on `suppressAutoSave || !activeSessionId.value`. In demo mode, `onDemoScenarioSelected` set `activeSessionId.value = sessionId` on picker click, so the 2-second auto-save timer fired `PATCH /api/session/<demo id>` — not in the tape → NOT_RECORDED → full-screen watchdog overlay blocked "Start Engine".

**Fix (Home.vue:1223):** Added `if (isDemoMode) return` as the first guard in `scheduleSessionSave()`, matching the existing pattern at line 719 (`if (!isDemoMode) await restoreSession()`).

**Audit of other timer/watcher/lifecycle API calls:**
- `apiGet('/billing/status')` in onMounted — listed in PRE_PICKER_PATHS, safe.
- `loadActiveSessions()` calls `GET /api/session/active` — listed in PRE_PICKER_PATHS, safe.
- `handleEnhancePrompt()` calls `POST /graph/enhance-prompt` — **not gated in demo mode**. The textarea is `:readonly="isDemoMode"` which disables editing but the Enhance button was still rendered and enabled (picker fills the prompt). Added `v-if="!isDemoMode"` to the Enhance button.
- Stripe `auto_research` handler in onMounted calls `GET /billing/status` then `runDeepResearch()` — added `!isDemoMode &&` guard to the entire block.

**Playwright probe (throwaway, deleted after run):**

Command:
```
cd e2e && BASE_URL=http://localhost:4173 npx playwright test tests/_probe_critical1.spec.js --reporter=line --timeout=60000 --retries=0
```

Output:
```
Running 1 test using 1 worker
URL before Start Engine click: http://localhost:4173/
Start Engine button disabled: false
URL after Start Engine click: http://localhost:4173/simulation/demo-demo-e2e-sim/start
CRITICAL 1 probe PASSED: no watchdog after 4 s pause, Start Engine worked.
  1 passed (8.3s)
```

The button was not disabled after 4 seconds, navigation succeeded, and no watchdog overlay appeared.

---

## IMPORTANT 2 — Virtual clock starts at picker-click, not run-start

**Root cause:** `DemoScenarioPicker.vue:48` called `encodeDemoId(Date.now(), ...)` on card click, then `startSimulation` ran some seconds later. At 20× speedup, a 5-second pause burned 100 s of tape, jumping straight to the completed state.

**Fix:**
- `DemoScenarioPicker.vue`: Removed `encodeDemoId` call from `choose()`. The picker now only emits `{ scenarioId, prompt }` — no `sessionId` in the payload.
- `Home.vue::onDemoScenarioSelected`: Removed `activeSessionId.value = sessionId` and `localStorage.setItem(SESSION_KEY, sessionId)`. Now only sets `demoScenarioId.value`.
- `Home.vue::startSimulation` (demo branch): Now mints the session id (`encodeDemoId(Date.now(), ...)`) at the exact moment the run begins, stores it to localStorage, and calls `setActiveScenario(demoScenarioId.value, sessionId)` before navigating.
- Added imports: `encodeDemoId` from `../demo/sessionId` and `setActiveScenario` from `../demo/adapter`.

**`adapter.js` rehydration:** Unchanged — `adapter.js` already decodes `SESSION_KEY` from localStorage to recover scenario + start time on reload. The session id is now written at run-start (not picker-click), which is correct since rehydration is only meaningful once a run has actually started.

**`setActiveScenario` still receives both scenario and session id** — called correctly in `startSimulation`.

---

## IMPORTANT 3 — Cursor-based log endpoints collapsed to a single progressive key

**Root cause:** `tape.js:normalisePath` stripped the entire query string, so `GET /api/report/:id/agent-log?from_line=0` and `?from_line=5` mapped to the same key. The append logic in `Step4Report.vue` advances `from_line` locally, so under speedup it sampled arbitrary snapshots and re-appended the tail on every poll.

**Fix — JS (`tape.js`):**
- Exported new function `canonicalQuery(path)`: strips path, extracts query string, sorts params by key, percent-encodes, returns stable string.
- `indexEntries()`: For each entry, registers under both the stripped-path key AND (if the entry has query params) a query-aware key.
- `resolve()`: Tries the query-aware key first (when request has query params), falls back to stripped key. This implements the plan's "stripped EXCEPT where a recorded entry disambiguates" rule.

**Fix — Python (`demo_recorder.py`):**
- Added `canonical_query(query_string)` function using `urllib.parse.parse_qsl` + sort + `urlencode`. Must stay behaviourally identical to JS `canonicalQuery()`.
- `_record()`: Builds `recorded_path = f"{npath}?{cq}" if cq else npath` and records the full key including query params.

**Cross-language contract:** Both sides sort params by key and re-encode. Test cases added on both sides.

**Tests added:**
- `tape.test.js`: `canonicalQuery` suite (4 cases) + `query-string disambiguation` suite (5 cases using synthetic-tape agent-log entries with `from_line=0` and `from_line=1`).
- `test_demo_recorder.py`: `test_canonical_query` (4 cases), `test_recorder_preserves_query_string_in_path`.

**Synthetic tape updated** (`frontend/src/demo/fixtures/synthetic-tape.json`): Added agent-log entries with `?from_line=0` and `?from_line=1` to support the new test cases.

---

## IMPORTANT 4 — Recorder has no secret scrubbing

**Fix (demo_recorder.py):** Added `scrub_body(obj)` function that recursively processes decoded JSON values:
- Bearer tokens (`Bearer <token>`) → `<REDACTED>`
- API keys (`sk_`, `pk_`, `rk_` prefixed) → `<REDACTED>`
- Stripe customer IDs (`cus_...`) and subscription IDs (`sub_...`) → `<REDACTED>`
- Real UUIDs → stable demo UUIDs via `_stable_demo_uuid()`: SHA-256 of the input UUID, first 28 hex chars, prefixed with `demo0000-`. Same input always produces same output (memoised), preserving referential integrity across the tape.

`scrub_body()` is called on the response body before appending to `entries`.

**Tests added** (`test_demo_recorder.py`): 6 scrubbing tests + `test_recorder_scrubs_secrets_from_body` integration test.

---

## IMPORTANT 5 — Recorder flushes entire tape on every response (O(n²))

**Fix (demo_recorder.py):** Introduced `FLUSH_EVERY = 20` constant. The `_record` after-request hook increments `unflushed[0]` and flushes only when `unflushed[0] >= FLUSH_EVERY`.

**Final-flush guarantee:** `_final_flush()` registered via `atexit` so the tail (< FLUSH_EVERY entries) is written on process exit. Error handling on atexit flush is log-only (preserves exit code).

**`close()` function returned by `init_recorder()`:** Flush the tail and de-register the atexit handler. Used in tests to read a complete tape without waiting for process exit.

**Init-time flush stays fail-fast** (no `except OSError` guard) — if the directory/path is broken the operator should know immediately, not after a full run.

**Tests updated:** All existing recorder tests updated to call `close()` after requests. New `test_recorder_buffered_flush` test verifies that `os.replace` is called exactly once (init) for `FLUSH_EVERY - 1` requests, then once more on the `FLUSH_EVERY`-th request.

---

## IMPORTANT 6 — manifest.json schema_version never validated + no retry

**Fix (DemoScenarioPicker.vue):**
- Extracted `fetchManifest()` async function with one retry (matching `tape.js:loadTape()` policy: CDN hiccups are usually transient).
- Validates `manifest.schema_version !== SCHEMA_VERSION` and throws a descriptive error if mismatched.
- Error message surfaced through the existing `data-test="picker-error"` element (not console).
- Removed `setActiveScenario` call from picker (moved to `startSimulation` per IMPORTANT 2 fix).

**Manifest fixture updated** (`e2e/fixtures/demo/manifest.json`): Added `"schema_version": 1`.

**Tests updated** (`DemoScenarioPicker.test.js`):
- Test "emits a demo session id..." renamed and updated: `sessionId` is no longer in the emitted payload (by design).
- New test: "shows a visible error when the manifest schema_version does not match".
- Test "shows a visible error when a scenario id contains an underscore" replaced: underscore check now happens in `startSimulation` (via `encodeDemoId` throwing TypeError), not in the picker. New test verifies the picker emits `select` even for underscore ids.

---

## MINOR 7 — DEMO_SPEEDUP silently swallows bad values

**Fix (config.js):** `Number(import.meta.env.VITE_DEMO_SPEEDUP) || 1` replaced with explicit validation:
- If `VITE_DEMO_MODE === '1'` and `VITE_DEMO_SPEEDUP` is set, throws `Error` at module-load time if the parsed value is not finite or is ≤ 0.
- `DEMO_SPEEDUP` is set from the validated value (or 1 as safe fallback for non-demo builds where `VITE_DEMO_SPEEDUP` is unset).

---

## MINOR 8 — Python/JS path normalisation diverge on Unicode digits and trailing newline

**Fix (demo_recorder.py):**
- `_DIGITS`: `r"^\d+$"` → `r"^[0-9]+\Z"` (`\d` is Unicode-aware in Python; `[0-9]` is ASCII-only, matching JS).
- `_UUID`, `_OPAQUE`: `$` → `\Z` (`$` matches before a trailing `\n` from Werkzeug percent-decoding `%0A`; `\Z` is unconditional end-of-string).

The comment "byte-identical in behaviour to normalisePath()" becomes true after this fix.

**Test cases added** (`test_demo_recorder.py`):
- `/api/x/٠١٢` (Arabic-Indic digits) → stays literal (was being normalised to `:id` with `\d`).
- `/api/simulation/create\n` (trailing newline) → stays literal (was matching `$` anchor and collapsing to `:id`).

---

## MINOR 9 — DEMO_TARGET_MS is a dead export

Verified: `grep -rn "DEMO_TARGET_MS" frontend/` returns no results. The export was removed as part of the MINOR 7 config.js rewrite (it was in the same block).

---

## MINOR 10 — DemoBanner.test.js:19 misleading test name

**Fix (`DemoBanner.test.js`):** Renamed "shows not-recorded failure state and stops the run when the event fires" → "shows not-recorded overlay when the event fires". The test only asserts that the overlay appears; it makes no assertion about stopping the run (there is no such mechanism in the component — stopping is an indirect effect of the overlay blocking pointer events).

---

## MINOR 11 — setActiveScenario(scenario) defaults sessionId to null, freezing tape at t=0

**Fix (adapter.js):** Changed `setActiveScenario(scenario, sessionId = null)` to `setActiveScenario(scenario, sessionId)` with `activeSessionId = sessionId ?? null` internally. The `= null` default was misleadingly suggesting null was acceptable at the call site; now callers must be explicit.

**Tests added (adapter.test.js):** New "time progression through the adapter" describe block with 3 cases:
1. `setActiveScenario('synthetic')` (no sessionId) returns t=0 snapshot — frozen clock is the expected behavior when no session id is passed.
2. `setActiveScenario('synthetic', sessionId)` with a session id encoding `startMs = now - 10000/DEMO_SPEEDUP` — verifies the t=10000 snapshot is returned.
3. A session id with `startMs` far in the past — verifies clamping at the last snapshot (not throw).

---

## Verification Commands and Output

### `cd frontend && npx vitest run`

```
 RUN  v3.2.4 /Users/sammcdonnell/Documents/GlasIntelligence-demo/frontend

 ✓ src/demo/sessionId.test.js (6 tests) 5ms
 ✓ src/demo/tape.test.js (23 tests) 15ms
 ✓ src/components/DemoScenarioPicker.test.js (5 tests) 58ms
 ✓ src/App.test.js (2 tests) 45ms
 ✓ src/components/DemoBanner.test.js (7 tests) 69ms
 ✓ src/demo/adapter.test.js (15 tests) 287ms
 ✓ src/config/zepFootprint.spec.js (4 tests) 1ms
 ✓ src/router/index.test.js (3 tests) 963ms

 Test Files  8 passed (8)
      Tests  65 passed (65)
   Start at  21:44:12
   Duration  1.71s
```

### `cd backend && /Users/sammcdonnell/.hermes/bin/uv run pytest tests/test_demo_recorder.py`

```
============================= test session starts ==============================
platform darwin -- Python 3.11.15, pytest-8.2.0
collected 26 items

tests/test_demo_recorder.py::test_normalise_path[...] x9  PASSED
tests/test_demo_recorder.py::test_canonical_query[...] x4  PASSED
tests/test_demo_recorder.py::test_scrub_body_*  x6  PASSED
tests/test_demo_recorder.py::test_recorder_*  x7  PASSED

============================== 26 passed in 0.07s ==============================
```

### e2e build + serve + Playwright

Build:
```
cd frontend && VITE_DEMO_MODE=1 npm run build
# → built in 1.76s
```

Fixtures copied:
```
cp e2e/fixtures/demo/manifest.json frontend/dist/demo/manifest.json
cp e2e/fixtures/demo/demo-e2e/tape.json frontend/dist/demo/demo-e2e/tape.json
```

Server: `npx vite preview --port 4173`

```
cd e2e && BASE_URL=http://localhost:4173 npx playwright test tests/demo.spec.js --reporter=line
Running 2 tests using 1 worker
  2 passed (11.5s)
```

### CRITICAL 1 Playwright probe (throwaway, deleted after run)

```
cd e2e && BASE_URL=http://localhost:4173 npx playwright test tests/_probe_critical1.spec.js --reporter=line --timeout=60000 --retries=0

Running 1 test using 1 worker
URL before Start Engine click: http://localhost:4173/
Start Engine button disabled: false
URL after Start Engine click: http://localhost:4173/simulation/demo-demo-e2e-sim/start
CRITICAL 1 probe PASSED: no watchdog after 4 s pause, Start Engine worked.
  1 passed (8.3s)
```

The probe confirmed: after a 4-second pause the Start Engine button was not disabled, navigation succeeded, and no watchdog overlay appeared.

---

## Files Changed

### Frontend
- `frontend/src/views/Home.vue`: guard `scheduleSessionSave()` + Enhance button + Stripe handler; session id minted at run-start; added imports.
- `frontend/src/components/DemoScenarioPicker.vue`: removed session id minting; added manifest retry + schema_version validation.
- `frontend/src/demo/tape.js`: added `canonicalQuery()`, updated `indexEntries()` and `resolve()` for query-string disambiguation.
- `frontend/src/demo/adapter.js`: changed `setActiveScenario` signature.
- `frontend/src/demo/config.js`: hardened `DEMO_SPEEDUP` validation; removed dead `DEMO_TARGET_MS`.
- `frontend/src/demo/fixtures/synthetic-tape.json`: added agent-log entries with query params.
- `frontend/src/demo/tape.test.js`: added canonicalQuery + query-disambiguation suites.
- `frontend/src/demo/adapter.test.js`: added time-progression suite.
- `frontend/src/components/DemoBanner.test.js`: renamed misleading test.
- `frontend/src/components/DemoScenarioPicker.test.js`: updated for new picker behavior.

### Backend
- `backend/app/middleware/demo_recorder.py`: full rewrite with secret scrubbing, buffered flushing, query-string recording, MINOR 8 regex fixes.
- `backend/tests/test_demo_recorder.py`: added canonical_query, scrub_body, query-string, buffered-flush tests; updated existing tests to call `close()`.

### Fixtures
- `e2e/fixtures/demo/manifest.json`: added `"schema_version": 1`.
