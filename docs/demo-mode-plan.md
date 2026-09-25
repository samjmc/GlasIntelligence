# Portfolio Demo Mode — Shipped

**Goal:** a visitor clicks one link and walks the entire Glas Intelligence pipeline — scenario → research → knowledge graph → agent population → live simulation → report → agent interview — start to finish, with no waiting, no signup, and no API spend.

---

## Status: ✅ Shipped

**Phases 0–5 are complete** (plan written 2026-08-07, first Pages deploy 2026-08-20 — ~2 weeks). The demo is live, keyless, and guarded by CI.

- **Live demo:** https://samjmc.github.io/GlasIntelligence/
- **CI gates:** `.github/workflows/demo-e2e.yml` runs two jobs — the synthetic-fixture replay (`e2e/tests/demo.spec.js`) and the real golden-tape replay (`e2e/tests/demo-real.spec.js`, Pharmacy First + Energy Caps, 240 s per-test timeout). Both build with `VITE_DEMO_MODE=1` and **no secrets, no .env, no backend** — if the build needs a credential, the demo has stopped being keyless and the job fails.
- **Deploy:** `.github/workflows/deploy-pages.yml` builds and deploys on every push to `main` (base-path-aware, `VITE_BASE=/GlasIntelligence/`, 404.html SPA fallback, `.nojekyll`).

### Pivot: Cloudflare Pages → GitHub Pages

The design spec (`docs/superpowers/specs/2026-08-08-static-demo-hosting-design.md`) planned a Cloudflare Pages build (`demo.glasinsight.com`). **What shipped is GitHub Pages.** Why:

- GitHub Pages deploys straight from GitHub Actions with no external account, no OAuth git integration, and no custom domain/DNS to manage — the Cloudflare path needed a Cloudflare dashboard connection and a domain.
- The frontend was made base-path-aware (`import.meta.env.BASE_URL`) so the same keyless bundle serves correctly at the subpath `/GlasIntelligence/`; the root build is unchanged.
- `demo-e2e.yml` comments still nominally say "ships to Cloudflare Pages"; the actual deploy target is GitHub Pages via `deploy-pages.yml`.

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

### 1.4 What blocked a click-through demo (and the fixes that shipped)

**A. Auth wall.** `router.beforeEach` (`router/index.js`) redirects any non-`public` route to `/login` when `authState.user` is null. `/process`, `/simulation`, `/report`, `/interaction` are all gated. A recruiter hits a login form. → *Resolved: `frontend/src/main.js` awaits `initAuth()`, and with no Supabase key it creates a local user, so `router.beforeEach` passes all routes.*

**B. Billing gates.** `/api/billing/can-research` and `/api/billing/can-simulate` sit in front of the two expensive stages, and `profiles.research_credits` is decremented per run. → *Resolved: the replayer short-circuits the capability checks to allowed.*

**C. Five external dependencies, any of which can be down or unfunded** — Zep Cloud, the LLM provider (DeepSeek/OpenAI/Anthropic), Tavily, Supabase, Redis+Celery. Recent commit history is largely firefighting exactly this. A live demo inherits every one of those failure modes on the day someone looks at it. → *Resolved by construction: the demo is a pure function of committed JSON. No LLM spend, no Zep quota, no Supabase, no Redis.*

**D. Wall-clock time.** Deep research is multi-round Tavily + LLM refinement. Graph build is a Celery task polled every 2s. Profile generation is per-agent LLM calls. The simulation is an OASIS subprocess running N rounds. Report generation is a tool-using agent streaming to `agent-log`. Realistically this is **tens of minutes**, not seconds. → *Resolved by the time-indexed replay clock (`elapsed = (now − start_ms) × DEMO_SPEEDUP`).*

**E. Step 5 cannot be replayed naively.** `/api/simulation/interview` calls `SimulationRunner.check_env_alive(simulation_id)` and 400s if the OASIS environment process isn't still resident in wait-for-command mode. → *Resolved for the live backend: it now answers interviews after the process has exited by rebuilding each agent from the recorded run (`backend/app/services/offline_interview.py`). **Still open in the static demo:** none of the committed tapes holds an `/interview`, `/interview/batch`, `/env-status` or `/report/chat` entry (checked 2026-09-25), so asking an agent a question in the demo returns `DEMO_NOT_RECORDED`. The frontend no longer asks `env-status` in demo mode. The backend `demo_interviews.py` (canned Q&A behind `Config.DEMO_MODE`) was removed: the static demo never reaches the backend, and nothing set `DEMO_MODE`.*

**F. Two real bugs / rot in the flow:**
- `MainView.vue` `handleNextStep` increments `currentStep` to 3, but the template only mounts `Step1GraphBuild` and `Step2EnvSetup` — `MAX_IMPLEMENTED_STEP = 2`. If Step 2 is ever reached *inside* `MainView` (rather than via `SimulationView`), advancing leaves a blank panel. → *Fixed: `handleNextStep` is capped at `MAX_IMPLEMENTED_STEP`; steps 3–5 are reached by routing, not by incrementing the local counter.*
- `frontend/src/views/Process.vue` (1,082 lines) was dead — the router imports `MainView.vue` under the name `Process`. → *Deleted (commit `9849885`); the orphaned `Process.scoped.css` was removed with it.*

**G. Schema drift.** `docs/schema/supabase_schema.sql` predated `backend/migrations/004`–`009` — no `scenario_sessions`, no `decision_bundles`, no `research_credits`. → *Regenerated from the migrations; the consolidated schema on main now contains all three.*

### 1.5 Honest unknown → resolved

Originally: **nobody had confirmed a green end-to-end run recently.** → *Resolved: the golden runs (Pharmacy First V11, Energy Caps) were recorded, the real-tape e2e passes 3/3 against the shipped subpath build, and the live deploy is green.*

---

## Part 2 — The approach (as shipped)

Three options were on the table:

1. **Live backend, cached rows** — keep the real stack up, point the demo at a pre-computed project. Rejected: inherits all five external dependencies, costs money monthly, and shared mutable state means visitor #2 sees whatever visitor #1 did.
2. **Hybrid** — fixtures for expensive stages, live for cheap reads. Rejected for now: most plumbing, and the "cheap reads" are exactly the Zep/Supabase reads that break when a key lapses.
3. **Record once, replay from static fixtures.** ✅

**Chosen: record one real run, freeze it, replay it.** The demo becomes a pure function of committed JSON. No LLM spend, no Zep quota, no Supabase dependency, no Redis. It cannot break because a vendor changed pricing eight months after you last touched it — which is precisely the property a portfolio piece needs.

Two design decisions make this cheap:

**Stateless demo identity.** `/demo` mints IDs that embed their own creation timestamp — `demo_<base64(start_ms)>_<nonce>` for project/simulation/report. Replay derives "how far into the run are we" from `now − start_ms` decoded straight out of the URL. No Redis, no server-side session table, and two simultaneous visitors are naturally isolated.

**Time-indexed fixtures.** The recorder stamps every captured response with its offset from run start. The replayer serves the response whose offset ≤ `(now − start) × SPEEDUP`. Polling endpoints then *animate on their own* — the graph fills in, agents post round by round, the report streams — with zero frontend changes, just a different `SPEEDUP` constant. Default target: **~2–4s per stage, ~90s for the full traverse.**

---

## Part 3 — The plan, retrospectively

### Phase 0 — Get one real run green (the golden run) ✅

Shipped by `426d71b` (Pharmacy First golden tape + manifest, 2026-08-14), `755df87` (V11 golden run — real agent behavior, 2026-08-15), `127d05c` (Energy Caps scenario tape, 2026-08-17), adopted to main in `9849885`.

1. Stand up a working local `.env` (Zep, LLM, Tavily, Supabase, Redis) and `make dev`.
2. Pick the demo scenario. **Pharmacy First funding cap** — a real report already existed (`docs/reports/pharmacy_first_caps_report_EN.md`), the domain is concrete, and the stakeholder set (NHS England, pharmacy multiples, independents, patients) is legible to a non-expert in five seconds.
3. Walk all six screens manually. Log every failure.
4. Fix blockers only.
5. **Exit criterion:** one traverse from `/` to `/interaction/:reportId` with no error screens, and `backend/uploads/simulations/<sim_id>/` fully populated.

*Risk note from the plan: "this is the phase that can blow up." It absorbed the variance — the stack needed recovery work to boot from a fresh checkout, and the V11 tape replaced an earlier zero-action run — but it landed.*

### Phase 1 — The recorder ✅

Shipped by `8bfca83` (`backend/app/middleware/demo_recorder.py`, an `after_request` hook active under `DEMO_RECORD=1`, flushed periodically so a crashed run leaves a usable partial tape), with hardening in `8802a32`/`fe92f27`.

- Captures method, path, normalised query/body signature, status, JSON body, and `offset_ms` from run start.
- Rewrites real UUIDs to stable demo IDs (consistent within a single recording so referential integrity survives); response bodies are scanned and Bearer tokens, API keys, and Stripe IDs are redacted **before** the tape is committed.
- `normalise_path` must stay byte-identical to `normalisePath()` in `frontend/src/demo/tape.js`.

Then re-run Phase 0's traverse with the recorder on. That produces the tape.

### Phase 2 — In-browser replay ✅

Shipped by `ff27f3e`/`2182a8f` (e2e asserting the static demo replays with no external requests). Replay runs entirely client-side. `frontend/src/demo/` contains:

- `tape.js` — loads `tape.json` for the chosen scenario, indexes entries by `METHOD normalised-path[?query]`, and resolves requests against the virtual clock via `resolve(index, method, path, elapsedMs)`. Query strings are stripped from index keys *except* where a recorded entry explicitly carries a query string — so cursor-based endpoints like `GET /api/report/:id/agent-log?from_line=N` are keyed separately per cursor value and fall back to the stripped key when no cursor-specific entry exists.
- `adapter.js` — replaces the axios adapter and `window.fetch` with the tape resolver. Any path not in the tape returns `{ error: "DEMO_NOT_RECORDED" }` (the `NOT_RECORDED` sentinel) and fires a `demo:not-recorded` event. The deliberate design choice is that a fixture gap must surface loudly — not silently return a plausible-looking stale answer.
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

### Phase 3 — Public entry ✅

Shipped by `a2a471a` (scenario picker, banner, watchdog, paid-UI suppression, 2026-08-09) and `68661ba` (landing page restored as the front door with a worked-examples section, 2026-08-18).

- A demo-scenario picker on the landing page (`DemoScenarioPicker.vue`) generating a demo session ID client-side (`demo_<base64(timestamp)>_<nonce>`) and routing into the walkthrough.
- A persistent, dismissible **"Demo — replaying a recorded simulation"** banner (`DemoBanner.vue`). Being straight about it is a credibility gain, not a loss.
- Signup/upgrade prompts and the credit counter are suppressed while in demo mode.

### Phase 4 — Pacing and Step 5 ✅

Shipped by `e5c658c` (skip-forward controls for the replay clock, 2026-08-18) and `9849885`.

- `DEMO_SPEEDUP` pacing + skip-forward controls; the replay clock is tunable per deployment.
- **Step 5 interviews are not in the tapes** (see §1.4 E). `9849885` also added a backend `demo_interviews.py` with canned Q&A behind `Config.DEMO_MODE`; the static demo never reaches the backend and nothing set the flag, so it was later removed.
- Items **F** and **G** from §1.4 were fixed while in here: `views/Process.vue` deleted, the `MainView` step-3 dead-end removed, and `docs/schema/supabase_schema.sql` regenerated from the migrations.

### Phase 5 — Ship it ✅

Shipped by `9849885` (adoption to main) and `ebd23fd` (base-path-aware GitHub Pages deploy, 2026-08-20).

- Static build with `VITE_DEMO_MODE=1` and **no** vendor keys — proves the demo is genuinely keyless. If the built frontend runs with an empty `.env`, it cannot rot.
- **GitHub Pages deploy** (see the pivot note above): `deploy-pages.yml` builds `VITE_DEMO_MODE=1` + `VITE_BASE=/GlasIntelligence/`, adds the 404.html SPA fallback + `.nojekyll`, and deploys to https://samjmc.github.io/GlasIntelligence/ on every push to `main`.
- Playwright specs in `e2e/tests/demo.spec.js` (synthetic fixture) and `e2e/tests/demo-real.spec.js` (real golden tapes) walk all six screens and assert no error state and no external requests. These are the regression guards that keep the demo working while the real product keeps developing.
- README section on what's real / what's replayed / the link — **not yet written** (the only item left open).

---

## Sequencing (as it actually happened)

```
Phase 0 (golden run, 08-07 → 08-15) ──► Phase 1 (recorder, 08-09) ──► Phase 2 (replay, 08-10/11) ──┬─► Phase 3 (public entry, 08-09/18) ──┐
                                                                                                      └─► Phase 4 (pacing/step 5, 08-18) ─┴─► Phase 5 (ship, 08-20)
```

Phases 0→2 were strictly serial. 3 and 4 ran in parallel.

**Rough sizing (as it played out):** the demo shipped in **~2 weeks** from plan (2026-08-07) to deploy (2026-08-20) — faster than the pessimistic end of the original estimate, which had budgeted "a day if the stack is healthy, a week if it isn't" for Phase 0 alone. Phase 0 did absorb the variance (fresh-checkout boot repair, the zero-action run that had to be re-recorded as V11), but once the tape existed Phases 1–5 compressed hard — roughly a week for the engineering, pacing, and ship.

## Consequences (confirmed in practice)

- **The demo shows one scenario (now two).** Each additional scenario costs another Phase 0 + Phase 1 cycle. Pharmacy First and Energy Caps shipped; the fixture inventory in Phase 2 is what a new tape must satisfy.
- **The tape must be re-recorded when API shapes change.** The `demo-real.spec.js` and `demo.spec.js` specs are what tell you it's gone stale — unmatched paths trigger the watchdog, and the e2e asserts no `DEMO_NOT_RECORDED` surfaces.
- **Fixtures add repo weight.** Action logs and agent logs are the bulk. The real tapes live under `frontend/public/demo/` (the pharmacy tape is ~35 MB); the synthetic fixture lives under `e2e/fixtures/demo/` so real recordings cannot clobber it.