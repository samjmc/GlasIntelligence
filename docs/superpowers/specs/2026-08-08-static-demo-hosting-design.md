# Static demo hosting — design

Date: 2026-08-08
Status: approved, pending implementation plan
Supersedes: Phase 2 and Phase 5 of `docs/demo-mode-plan.md`

## Problem

`docs/demo-mode-plan.md` turns GlasIntelligence into a recruiter-facing demo by
recording one real run and replaying it. It assumed a server: Phase 2 specified a
Flask `replay.py`, and Phase 5 assumed a working deploy path.

Neither assumption holds.

- The deploy target `87.99.135.45` (Hetzner) is unreachable and the bill has lapsed.
  That single box runs the app, Redis, and four Celery workers.
- Sam does not want to pay for hosting.
- The `Deploy` workflow has never completed successfully. The repo was created
  2026-08-07 with no Actions secrets, so the pipeline has never had credentials.

Only the demo needs to be publicly reachable — not the real application.

## Decision

Ship the demo as a fully static bundle on Cloudflare Pages, with replay running in
the browser. No backend, no Redis, no Celery, no Supabase in the demo build.

Cloudflare Pages free tier: 25 MiB per file, 20,000 files, 500 builds/month,
unlimited bandwidth. SPA fallback to `index.html` is automatic when no top-level
`404.html` exists, so `createWebHistory()` works with no configuration.

`replay.py` is never written. Phase 1's recorder remains server-side and runs on
Sam's machine; it emits fixtures the browser consumes directly.

## Architecture

### Interception

Two transport-layer shims, gated on `VITE_DEMO_MODE=1`. Both pass through
unchanged when the flag is absent.

| Chokepoint | Shim | Consumers |
| --- | --- | --- |
| axios `service` in `frontend/src/api/index.js` | replace the axios **adapter** | `api/simulation.js` (51 fns), `api/graph.js` (5), `api/report.js` (7) → all five Step components, `MainView`, `Home`, `CompareView` |
| `frontend/src/composables/useApi.js` | wrap `fetch` | 8 views |

Replacing the adapter rather than patching methods is deliberate. `api/graph.js`
calls the config-object form, `service({ url, method, data })`, which a per-method
patch would miss. The adapter also sits *below* the existing response interceptor,
so `response.data` unwrapping and the `res.success === false` rejection continue to
work untouched — the shim returns the same shape the real backend did.

63 exported API functions and every calling component stay unmodified.

### Fixtures

Recorded server-side by a Flask `after_request` hook writing JSONL:
`{t_ms, method, path, status, body}`, where `t_ms` is milliseconds since run start.
Normalisation scrubs secrets and rewrites real UUIDs to stable demo IDs.

```
frontend/public/demo/
  manifest.json          # {schema_version, scenarios: [{id, title, blurb, prompt, duration_ms}]}
  <scenario-id>/
    step1.json … step5.json
```

Plain JSON, not gzipped. Cloudflare compresses `application/json` on the fly
(minimum 48 bytes, no maximum), so committing `.gz` gains nothing on the wire while
costing twice: `fetch()` does not transparently decompress a `.gz` response, and
opaque binary defeats git delta compression, appending the whole file to history on
every re-record. This reverses the guidance in `docs/demo-mode-plan.md`.

Only the selected scenario's fixtures load, so scenario count does not affect page
weight.

### Replay

`replay.js` runs a virtual clock:

```
t_elapsed = (Date.now() - demoStartMs) * DEMO_SPEEDUP
```

`demoStartMs` and the scenario are encoded in the session ID —
`demo_<b64(start_ms)>_<scenario>_<nonce>` — so a page reload restores both which
scenario is running and how far in, with zero server state.

Requests match on `method + normalised path`, where normalisation replaces every
demo ID path segment with `:id` — so `GET /api/session/demo_MTcw_energy_a3f9`
matches the recorded `GET /api/session/:id`. Query strings are stripped except
where a recorded entry disambiguates on them. Request bodies are ignored; the tape
is fixed and bodies vary.

Two response classes:

- **Static** — `POST /api/simulation/create`, `GET /api/session/:id`. One recorded
  response, returned whenever asked.
- **Progressive** — all status and log endpoints. Return the last recorded snapshot
  where `t_ms <= t_elapsed`.

Progressive replay reproduces live behaviour for free. `Step3Simulation.vue`
tracks `prevTwitterRound`/`prevRedditRound` and logs only on advance, then calls
`stopPolling()` when `runner_status === 'completed'`. Feeding it time-indexed
snapshots makes the rounds tick up exactly as they did live and terminates the poll
when the tape says so.

### Pacing

Target watch time is **90 seconds** per scenario, end to end. Long enough that
round-by-round progression reads as real computation; short enough to finish before
attention goes.

`DEMO_SPEEDUP` is derived from the measured run length once Phase 0 completes:
start with a flat multiplier of `run_length_ms / 90000`. Move to per-phase
multipliers only if the flat version leaves visible dead air — a stretch where the
UI does not change for more than a few seconds.

### Scenarios

Three canned scenarios from visibly different domains. If two tapes produce similar
graphs and reports, three scenarios read as one scenario with a broken picker.

In demo mode Step 1 shows a scenario picker: three cards with title and blurb.
Selecting one fills the prompt read-only and starts the tape. **The file-upload
control is removed** — Step 1 is where uploads live (`Home.vue:1101`), and a
recruiter dropping a PDF into a demo that ignores it is worse than no control.

Sequencing: record scenario 1, ship it end to end to a live Pages URL, then record
2 and 3. The picker ships from day one with a single card. Recording all three
before the format is proven risks burning three runs of vendor credit to learn one
thing.

### Keyless build

The demo builds with no environment variables at all. This already works:

- `lib/supabase.js` exports `null` when `VITE_SUPABASE_*` are absent.
- `store/auth.js` handles `!supabase` on every path — `initAuth()` sets a local
  user, `signUp`/`signIn` throw, `signOut`/`refreshAccessToken` early-return,
  `getAccessToken()` returns `''`.
- `lib/analytics.js` no-ops without `VITE_POSTHOG_KEY`.

`/login` and `/signup` are hidden in demo mode; they would otherwise render forms
that throw `Auth not configured`.

The landing page states plainly that this is a recorded run. A visitor who works it
out mid-way feels tricked; one told upfront reads it as a deliberate engineering
decision.

## Error handling

| Case | Behaviour |
| --- | --- |
| Unrecorded endpoint | Return `{success: false, error: 'DEMO_NOT_RECORDED'}` — a structured rejection the existing axios interceptor already understands. A global handler renders a visible banner. Never `undefined`. |
| `t_elapsed` past end of tape | Clamp to the final snapshot. Never throw. |
| `manifest.json` `schema_version` mismatch | Fail loudly at load with a visible error. |
| Fixture fetch fails | Retry once, then a full-page "demo failed to load — reload" state. |
| Reload mid-run | Handled by the ID-encoded start time and scenario. |
| `POST /api/session/:id/files` | Returns a recorded success. `Home.vue` already catches failures, so this is belt-and-braces. |

The clamp rule is not a nicety. `fetchRunStatus` catches errors with `console.warn`
and keeps polling. A throwing or missing fixture on that one endpoint produces a
demo that spins forever, silently — the worst available failure mode.

Rollback is a static site revert: `git revert`, redeploy.

## Testing

Two layers.

**vitest** on `replay.js` in isolation — virtual clock maths, snapshot selection at
`t_ms` boundaries, clamp-past-end, `DEMO_NOT_RECORDED` for unknown paths, session ID
encode/decode round-trip. No browser, no real fixtures. Runs inside the existing
`test-frontend` CI job at no extra cost.

**Playwright**, in a new lightweight CI job — build with `VITE_DEMO_MODE=1` and no
environment variables, serve `dist/` statically, click picker → Step 1 → Step 5,
assert a report renders, and assert **zero requests leave the origin**.

That last assertion is the point. `docs/demo-mode-plan.md` claims "if it runs with
an empty `.env`, it cannot rot." The origin assertion converts that from an
intention into something CI enforces.

The existing `build-and-e2e` job is not reusable: it boots the full
`docker-compose.ci.yml` stack and needs `jlumbroso/free-disk-space` because the dev
image pulls camel-ai and PyTorch/CUDA. The demo job reuses the Playwright tooling
and none of the harness, and should run in about a minute.

Component-level tests are deliberately omitted. `Step3Simulation.vue` is
jsdom-safe — it imports only vue, vue-router, the api modules, analytics and config,
with d3 confined to `GraphPanel.vue` — so such a test is feasible. But the
infinite-poll trap it would guard is equally caught by an e2e that reaches Step 5.
Add one only if the e2e proves flaky or hard to debug.

## Risks

**Fixture size is unmeasured and load-bearing.** The ~10MB figure in
`docs/demo-mode-plan.md` is a hedge, not a measurement — nobody has recorded a run.
`.git` is 18MB today. Phase 0's first deliverable is the byte size of one recorded
scenario, produced before any of `replay.js` is written.

Budget: **15MB total per scenario**, summed across its five step files. This is a
git-history and page-weight budget, not a platform limit — Cloudflare's 25 MiB
ceiling is per file and will not bind. Above 15MB, stop and move fixtures to R2 or
a GitHub release asset rather than committing them.

**Phase 0 still needs the full local stack.** Redis, four Celery workers, and all
five vendor keys, on Sam's machine. `docker-compose.yml` exists so this is
feasible, but it remains the serial dependency for everything downstream. Dropping
Hetzner does not change this.

**Tapes go stale silently.** A UI change that reads a field the tape lacks yields a
blank panel, not an error. `schema_version` catches format drift; the e2e is the
only thing that catches content drift.

**Supabase RLS remains parked.** 18 of 27 tables have RLS disabled while the anon
key ships in a public frontend bundle. The demo build carries no Supabase key, so
this design does not widen the exposure — but "raise before public deployment"
stops being hypothetical once Pages is live.

**PostHog is opt-in.** Analytics no-op without a key. Enabling them means the public
demo phones home. Decision deferred.

## Consequences

- `.github/workflows/deploy.yml`, `add-ssh-key.yml`, `docker-compose.prod.yml` and
  `docker-compose.staging.yml` become dead for the demo. PR #3
  (`fix/deploy-pipeline`) adds a secrets preflight for a target being deleted;
  close or park it.
- `DEPLOY_SSH_KEY` is no longer needed.
- `docs/demo-mode-plan.md` needs revising: Phase 2 is rewritten in JS rather than
  Flask, Phase 5 targets Cloudflare Pages, and the gzip guidance is removed.
- The real application keeps its backend. Only the demo goes static.
