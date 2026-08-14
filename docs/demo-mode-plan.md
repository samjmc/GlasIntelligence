# Portfolio Demo Mode — Where We Are, and the Plan

**Goal:** a visitor clicks one link and walks the entire Glas Intelligence pipeline — scenario → research → knowledge graph → agent population → live simulation → report → agent interview — start to finish, with no waiting, no signup, and no API spend.

---

## Part 1 — Where the project stands

### 1.1 The pipeline, as actually wired today

The "5 steps" in the header are **not** one component tree. They are four separate routes plus a legacy container:

| Step | Route | View | Step component | Hands off via |
|------|-------|------|----------------|---------------|
| 0. Intake | `/` | `Home.vue` | — | `router.push('/process/new')` (`Home.vue:1343`) |
| 1. Knowledge Graph | `/process/:projectId` | `MainView.vue` | `Step1GraphBuild.vue` | `router.push({name:'Simulation'})` (`Step1GraphBuild.vue:256`) |
| 2. Environment Setup | `/simulation/:simulationId` | `SimulationView.vue` | `Step2EnvSetup.vue` | `router.push({name:'SimulationRun'})` (`SimulationView.vue:188`) |
| 3. Run Simulation | `/simulation/:simulationId/start` | `SimulationRunView.vue` | `Step3Simulation.vue` | `router.push({name:'Report'})` (`Step3Simulation.vue:960`) |
| 4. Report | `/report/:reportId` | `ReportView.vue` | `Step4Report.vue` | `router.push({name:'Interaction'})` (`Step4Report.vue:1093`) |
| 5. Deep Interaction | `/interaction/:reportId` | `InteractionView.vue` | `Step5Interaction.vue` | terminal |

Each step is genuinely built out — `Step4Report.vue` is 1,723 lines, `Step2EnvSetup.vue` 1,264, `Step3Simulation.vue` 1,086. This is not a skeleton. The work is not "build the flow"; it's "make the flow survive a stranger clicking it."

### 1.2 State lives in three places

1. **Supabase** — `projects`, `simulations`, `reports`, `scenario_sessions`, `decision_bundles`, `profiles`, `credit_transactions`, `simulation_reminders`.
2. **Zep Cloud** — the knowledge graph itself (nodes/edges), external and metered.
3. **Local filesystem** — `backend/uploads/simulations/<sim_id>/` holding `simulation_config.json`, `reddit_profiles.json`, `twitter_profiles.csv`, `run_state.json`, action logs. Plus `backend/uploads/graph_cache/<graph_id>/`.

That third one matters: **simulation artifacts are not in the database.** Any demo built on "just point at an old row in Supabase" will find the row and then fail to find the profiles, config, and action logs behind it.

### 1.3 What already works in our favour

- **`extract_user_from_request` / `require_auth` already have an anonymous path** (`backend/app/middleware/auth.py`): when `SUPABASE_URL`/`SUPABASE_JWT_SECRET` are unset, every request runs as `ANONYMOUS_USER_ID`. A keyless demo deployment does not need auth surgery at the middleware layer.
- **A public surface already exists** — `/feed`, `/feed/report/:id`, `/landing`, `/insights` are `meta: { public: true }` in the router. There is a precedent for unauthenticated report viewing.
- **Real completed runs exist as artifacts** — `docs/reports/pharmacy_first_caps_report_EN.md` (17KB), `scenario1_report.md`, `scenario2_report.md`, `comparison_summary.md`. The Pharmacy First funding-cap scenario is a proven, domain-credible candidate for the demo scenario.
- **The graph snapshot cache is already a read-through disk cache** (`graph_snapshot_cache.py`, `docs/graph-cache.md`). The pattern for "serve this from disk instead of the vendor" is established in the codebase.
- **Polling is already centralised** — `useAdaptiveStepPolling.js` and `config/zepFootprint.js` govern intervals. One place to speed the demo clock up.

### 1.4 What blocks a click-through demo

**A. Auth wall.** `router.beforeEach` (`router/index.js`) redirects any non-`public` route to `/login` when `authState.user` is null. `/process`, `/simulation`, `/report`, `/interaction` are all gated. A recruiter hits a login form.

**B. Billing gates.** `/api/billing/can-research` and `/api/billing/can-simulate` sit in front of the two expensive stages, and `profiles.research_credits` is decremented per run.

**C. Five external dependencies, any of which can be down or unfunded** — Zep Cloud, the LLM provider (DeepSeek/OpenAI/Anthropic), Tavily, Supabase, Redis+Celery. Recent commit history is largely firefighting exactly this: `fix(research): don't retry on insufficient_quota`, `Add LLM research fallback`, `Fix deep research TPM rate-limit failures`, `fix: bundle analysis always failing ("Analysis Failed" screen)`. A live demo inherits every one of those failure modes on the day someone looks at it.

**D. Wall-clock time.** Deep research is multi-round Tavily + LLM refinement (`SEARCH_RESEARCH_MAX_ROUNDS=3`). Graph build is a Celery task polled every 2s. Profile generation is per-agent LLM calls. The simulation is an OASIS subprocess running N rounds. Report generation is a tool-using agent (`AGENT_TOOLS_MAX_ITERATIONS=3`) streaming to `agent-log`. Realistically this is **tens of minutes**, not seconds.

**E. Step 5 cannot be replayed naively.** `/api/simulation/interview` calls `SimulationRunner.check_env_alive(simulation_id)` and 400s if the OASIS environment process isn't still resident in wait-for-command mode. Interviewing agents from a *cached* run is impossible against the real code path — the process is gone. This stage **must** be served from canned Q&A or it will dead-end the demo at the final screen.

**F. Two real bugs / rot in the flow:**
- `MainView.vue` `handleNextStep` increments `currentStep` to 3, but the template only mounts `Step1GraphBuild` and `Step2EnvSetup` — `MAX_IMPLEMENTED_STEP = 2`. If Step 2 is ever reached *inside* `MainView` (rather than via `SimulationView`), advancing leaves a blank panel. Today it's unreachable because `Step1GraphBuild` routes away first, but it's a live trap.
- `frontend/src/views/Process.vue` (1,082 lines) is dead — the router imports `MainView.vue` under the name `Process`. Pure confusion cost.

**G. Schema drift.** `docs/schema/supabase_schema.sql` predates `backend/migrations/004`–`009`. It has no `scenario_sessions`, no `decision_bundles`, no `research_credits`. Anyone (including future-you) provisioning a fresh Supabase from that file gets a broken app.

### 1.5 Honest unknown

**Nobody has confirmed a green end-to-end run recently.** The commit log shows targeted fixes to individual stages, not a verified full traverse. Everything below depends on Phase 0 producing one, and Phase 0 is the phase most likely to expand.

---

## Part 2 — The approach

Three options were on the table:

1. **Live backend, cached rows** — keep the real stack up, point the demo at a pre-computed project. Rejected: inherits all five external dependencies, costs money monthly, and shared mutable state means visitor #2 sees whatever visitor #1 did.
2. **Hybrid** — fixtures for expensive stages, live for cheap reads. Rejected for now: most plumbing, and the "cheap reads" are exactly the Zep/Supabase reads that break when a key lapses.
3. **Record once, replay from static fixtures.** ✅

**Chosen: record one real run, freeze it, replay it.** The demo becomes a pure function of committed JSON. No LLM spend, no Zep quota, no Supabase dependency, no Redis. It cannot break because a vendor changed pricing eight months after you last touched it — which is precisely the property a portfolio piece needs.

Two design decisions make this cheap:

**Stateless demo identity.** `/demo` mints IDs that embed their own creation timestamp — `demo_<base64(start_ms)>_<nonce>` for project/simulation/report. Replay derives "how far into the run are we" from `now − start_ms` decoded straight out of the URL. No Redis, no server-side session table, and two simultaneous visitors are naturally isolated.

**Time-indexed fixtures.** The recorder stamps every captured response with its offset from run start. The replayer serves the response whose offset ≤ `(now − start) × SPEEDUP`. Polling endpoints then *animate on their own* — the graph fills in, agents post round by round, the report streams — with zero frontend changes, just a different `SPEEDUP` constant. Default target: **~2–4s per stage, ~90s for the full traverse.**

---

## Part 3 — The plan

### Phase 0 — Get one real run green (the golden run)

There is nothing to cache until a run completes. Everything else is blocked on this.

1. Stand up a working local `.env` (Zep, LLM, Tavily, Supabase, Redis) and `make dev`.
2. Pick the demo scenario. **Recommendation: the Pharmacy First funding cap** — a real report already exists for it (`docs/reports/pharmacy_first_caps_report_EN.md`), the domain is concrete, and the stakeholder set (NHS England, pharmacy multiples, independents, patients) is legible to a non-expert in five seconds.
3. Walk all six screens manually. Log every failure.
4. Fix blockers only. Resist the urge to refactor — Phase 4 covers polish.
5. **Exit criterion:** one traverse from `/` to `/interaction/:reportId` with no error screens, and `backend/uploads/simulations/<sim_id>/` fully populated.

*Risk: this is the phase that can blow up. Budget generously.*

### Phase 1 — The recorder

`backend/app/demo/recorder.py` — an `after_request` hook active under `DEMO_RECORD=1`.

- Captures method, path, normalised query/body signature, status, JSON body, and `offset_ms` from run start.
- Writes to `backend/app/demo/fixtures/<scenario>/tape.jsonl` plus a `manifest.json` recording the real ID → placeholder mapping (`proj_abc123` → `{{PROJECT_ID}}`).
- A `scripts/scrub_demo_tape.py` pass strips JWTs, emails, Supabase user IDs, and any key material before the tape is committed. **Non-negotiable — this tape goes into a public repo.**

Then re-run Phase 0's traverse with the recorder on. That produces the tape.

### Phase 2 — In-browser replay

**Status: shipped.** Replay runs entirely client-side. `frontend/src/demo/` contains:

- `tape.js` — loads `tape.json` for the chosen scenario, indexes entries by `METHOD normalised-path[?query]`, and resolves requests against the virtual clock via `resolve(index, method, path, elapsedMs)`. Query strings are stripped from index keys *except* where a recorded entry explicitly carries a query string — so cursor-based endpoints like `GET /api/report/:id/agent-log?from_line=N` are keyed separately per cursor value and fall back to the stripped key when no cursor-specific entry exists. This is the fix that prevents `from_line=0` responses from collapsing all subsequent cursor polls into one.
- `adapter.js` — replaces the axios adapter and `window.fetch` with the tape resolver. Any path not in the tape returns `{ error: "DEMO_NOT_RECORDED" }` (the `NOT_RECORDED` sentinel) and fires a `demo:not-recorded` event instead of returning the nearest recorded response. The deliberate design choice is that a fixture gap must surface loudly — not silently return a plausible-looking stale answer.
- `config.js` — exports `isDemoMode` (from `VITE_DEMO_MODE`) and `DEMO_SPEEDUP` (from `VITE_DEMO_SPEEDUP`, defaulting to `1`).
- `sessionId.js` — mints and decodes `demo_<base64(startMs)>_<scenario>_<nonce>` IDs; `elapsedFor(sessionId)` decodes `start_ms` and returns `(now − start_ms) × DEMO_SPEEDUP`.

When a `demo_`-prefixed scenario is active:
- `adapter.js` intercepts all axios and fetch calls; matches against the tape index; serves the snapshot in force at `elapsedFor(sessionId, now)`.
- `start_ms` is embedded in the demo session ID, so two simultaneous visitors are naturally isolated with no server state.
- **Unmatched requests return `DEMO_NOT_RECORDED` and trigger a visible full-screen watchdog overlay** (in `DemoBanner.vue`, `[data-test="watchdog-not-recorded"]`). A tape-load failure triggers a separate overlay (`[data-test="watchdog-tape-failed"]`). These are the regression guard: if a fixture gap is introduced, the demo shows an unmissable error screen rather than silently hanging on a spinner.

**Fixture inventory** (what the tape must contain, by screen):

- *Intake:* `POST /api/session`, `POST /api/session/<id>/files`, `POST /api/session/<id>/research`, `GET /api/session/<id>/research/status`, `POST /api/source/deep-research` + `/status/<task_id>` + `/result/<task_id>`
- *Step 1:* `POST /api/graph/ontology/generate`, `POST /api/graph/build`, `GET /api/graph/task/<task_id>`, `GET /api/graph/project/<id>`, `GET /api/graph/data/<graph_id>`, `POST /api/simulation/create`
- *Step 2:* `GET /api/simulation/<id>`, `POST /api/simulation/prepare`, `POST /api/simulation/prepare/status`, `GET /api/simulation/<id>/profiles{,/realtime}`, `GET /api/simulation/<id>/config{,/realtime}`, `GET /api/simulation/entities/<graph_id>`
- *Step 3:* `POST /api/simulation/start`, `GET /api/simulation/<id>/run-status{,/detail}`, `/actions`, `/timeline`, `/agent-stats`, `/posts`, `/comments`, `POST /api/report/generate`
- *Step 4:* `GET /api/report/<id>`, `GET /api/report/<id>/agent-log?from_line=0`, `GET /api/report/<id>/agent-log?from_line=N` (one entry per cursor advance), `GET /api/report/<id>/payload`, `/console-log`, `/sections`, `/section/<i>`, `/progress`
- *Step 5:* `POST /api/simulation/env-status`, `/interview/batch`, `/suggest-followups`, `POST /api/report/chat`

**Fixture inventory** (what the tape must contain, by screen):

- *Intake:* `POST /api/session`, `POST /api/session/<id>/files`, `POST /api/session/<id>/research`, `GET /api/session/<id>/research/status`, `POST /api/source/deep-research` + `/status/<task_id>` + `/result/<task_id>`
- *Step 1:* `POST /api/graph/ontology/generate`, `POST /api/graph/build`, `GET /api/graph/task/<task_id>`, `GET /api/graph/project/<id>`, `GET /api/graph/data/<graph_id>`, `POST /api/simulation/create`
- *Step 2:* `GET /api/simulation/<id>`, `POST /api/simulation/prepare`, `POST /api/simulation/prepare/status`, `GET /api/simulation/<id>/profiles{,/realtime}`, `GET /api/simulation/<id>/config{,/realtime}`, `GET /api/simulation/entities/<graph_id>`
- *Step 3:* `POST /api/simulation/start`, `GET /api/simulation/<id>/run-status{,/detail}`, `/actions`, `/timeline`, `/agent-stats`, `/posts`, `/comments`, `POST /api/report/generate`
- *Step 4:* `POST /api/report/generate/status`, `GET /api/report/<id>`, `/payload`, `/agent-log`, `/console-log`, `/sections`, `/section/<i>`, `/progress`
- *Step 5:* `POST /api/simulation/env-status`, `/interview/batch`, `/suggest-followups`, `POST /api/report/chat`

### Phase 3 — Public entry

- A "See a worked example →" CTA on `LandingView.vue` and `Home.vue` generating a demo session ID client-side (`demo_<base64(timestamp)>_<nonce>`) and routing to Step 1 with that ID.
- A persistent, dismissible **"Demo — replaying a recorded simulation"** banner. Being straight about it is a credibility gain, not a loss; the alternative reads as a fake if anyone notices.
- Suppress signup/upgrade prompts and the credit counter while in demo mode.

*Note: a router guard treating `demo_`-prefixed routes as public is unnecessary. `frontend/src/main.js` awaits `initAuth()` before mounting, and with no Supabase key `initAuth()` creates a local user, so `router.beforeEach` already passes all routes when `authState.user` is set.*

### Phase 4 — Pacing and Step 5

- Tune `DEMO_SPEEDUP` per stage — research and graph build compress hardest, the simulation rounds and report stream want to breathe. Target ~90s total.
- **Step 5 is bespoke work.** `check_env_alive` will always be false for a recorded run. Ship a `DEMO_MODE` branch in `simulation_interview_env_routes.py` serving a canned interview set: ~6 pre-recorded agent Q&As, with the frontend offering those as suggested-question chips so a visitor lands on a real answer rather than a miss. Free-typed questions fall back to nearest-match with a visible "this is a recorded response" note.
- Fix **F** and **G** from §1.4 while in here: delete `views/Process.vue`, remove the `MainView` step-3 dead-end, regenerate `docs/schema/supabase_schema.sql` from migrations `002`–`009`.

### Phase 5 — Ship it

- Static build with `VITE_DEMO_MODE=1` and **no** vendor keys — proves the demo is genuinely keyless. If the built frontend runs with an empty `.env`, it cannot rot.
- Cloudflare Pages Git integration — pushing to main triggers a build (Vite produces `/frontend/dist/`), auto-deployed to `https://demo.glasinsight.com` (see `docs/superpowers/specs/2026-08-08-static-demo-hosting-design.md` for architecture).
- Playwright spec in `e2e/tests/demo-flow.spec.js` walking all six screens and asserting no error state. This is the regression guard that keeps the demo working while you keep developing the real product.
- README section: what's real, what's replayed, and a link.

---

## Sequencing

```
Phase 0 (golden run) ──► Phase 1 (recorder) ──► Phase 2 (replay) ──┬─► Phase 3 (public entry) ──┐
                                                                    └─► Phase 4 (pacing/step 5) ─┴─► Phase 5 (ship)
```

Phases 0→2 are strictly serial. 3 and 4 can be parallel.

**Rough sizing:** Phase 0 is the wildcard (a day if the stack is healthy, a week if it isn't). Phases 1–2 are the real engineering, ~2–3 days. Phases 3–5 ~2 days.

## Consequences worth accepting up front

- **The demo shows one scenario.** A second costs another Phase 0 + Phase 1 cycle. Accept one, do it well.
- **The tape must be re-recorded when API shapes change.** The Playwright spec in Phase 5 is what tells you it's gone stale.
- **Fixtures add repo weight.** Action logs and agent logs are the bulk. Trim to what the UI actually renders; if it exceeds ~10MB, store as gzipped JSONL and decompress on load.
