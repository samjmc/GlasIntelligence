# Glas Intelligence — Technical Deep-Dive & Portfolio Narrative

**Document type:** portfolio technical assessment (interview-facing)
**Repo state assessed:** HEAD `dcbe875` (2026-08-14) · all claims verified against source, git history, executed tests, and real run artifacts
**Provenance:** seven domain assessments + an adversarial cross-check; every correction from the cross-check has been applied and is marked `(corrected)` in the text. Where a number is an estimate rather than a measurement it is explicitly marked `(est.)`.

---

## 1. Executive Summary

Glas Intelligence is a multi-agent AI scenario simulation engine for predictive business intelligence. A user describes a policy or market scenario — e.g. "NHS England Pharmacy First payment caps" — and the system: (1) researches it with live web search or a deep-research model, (2) builds a temporal knowledge graph of the named stakeholders (pharmacies, GPs, regulators, patients) in Zep Cloud, (3) generates AI personas from graph entities and runs a multi-round social simulation of those stakeholders on the OASIS/camel-ai framework, (4) writes an executive report via a hand-rolled ReACT agent that reasons over the simulation evidence with tools and a Monte-Carlo risk layer, and (5) lets the user interview the simulated agents directly.

**The stack:** Vue 3 + Vite SPA · Flask API · Celery + Redis for long research jobs · OASIS (camel-ai) subprocess for the simulation · Zep Cloud temporal knowledge graph · Supabase (Postgres + Auth + Storage + atomic credit RPCs) · Stripe billing · Prometheus/Grafana/Loki observability.

**One-sentence pitch:** *"Describe a policy scenario; Glas researches it, builds a temporal knowledge graph of the stakeholders, runs a social simulation of how those agents actually react, writes an executive report by reasoning over that evidence, and lets you interview the simulated stakeholders directly."*

**Honest state (updated 2026-08-16):** this is an engineered surface with real depth — a recorded-and-replayed keyless static demo, an atomic credit ledger, a genuinely agentic report writer, and a defensive failure-mode culture — and it is now **green end to end**. The backend boots and passes **257/257 pytest** (was 17 failed / 152 passed / 24 errors at the time of the first draft), the frontend is **65/65 vitest**, and the static demo's two e2e tests (zero-external-origins + full replay to a rendered report) **both pass**. The previously-red surfaces were real findings, not hype: the backend had not booted from a fresh checkout since 2026-04-18 (missing Stripe config constants + an unregistered session blueprint), and the demo's frontend glue was genuinely unwired. Both were repaired in a focused recovery (≈60 lines of config/blueprint restoration + the demo adapter/picker/banner wiring + a keyless `envPrefix` build fix) and are committed. Section 5 now documents what the red state was, how it was diagnosed, and how it was fixed — the diagnosis-to-repair arc is itself a portfolio story.

---

## 2. Architecture Overview

### 2.1 System diagram

```
                    ┌────────────────────────────────────────────────────────────────┐
                    │                      BROWSER — Vue 3 SPA                        │
                    │  Home → Step1 (graph) → Step2 (env) → Step3 (sim)              │
                    │      → Step4 (report) → Step5 (interaction)                    │
                    │  api/ (axios + useApi) ── demo adapter ── tape.json (replay)   │
                    └───────────────────────────────────┬────────────────────────────┘
                                                        │ HTTPS · Bearer JWT (Supabase Auth)
              ┌──────────────────────────────────────────▼───────────────────────────────────┐
              │                       FLASK API (gunicorn 1 worker × 4 threads)              │
              │  api/session.py · api/graph.py · api/simulation*.py · api/report.py          │
              │                                                                              │
              │   ┌────────────── threads (in-process) ────────────────────┐                 │
              │   │  graph build (graph.py:627)  prepare (simulation:580)  │                 │
              │   │  report gen (report.py:166)  legacy research (thread)  │                 │
              │   └───────────────────┬────────────────────────────────────┘                 │
              │                       │ progress via in-memory TaskManager (models/task.py)  │
              │   ┌───────────────────▼────────────────────────────────────┐                 │
              │   │  CELERY WORKER — "research" queue (Redis broker)       │                 │
              │   │  glas.deep_research → dossier → Supabase rows          │                 │
              │   └───────────────────┬────────────────────────────────────┘                 │
              │   ┌───────────────────▼────────────────────────────────────┐                 │
              │   │  SIMULATION SUBPROCESS (detached, own process group)   │                 │
              │   │  scripts/run_parallel_simulation.py — OASIS (camel-ai) │                 │
              │   │  Twitter env + Reddit env (sequential by default)      │                 │
              │   │    → per-platform SQLite + actions.jsonl (tailed 2 s)  │                 │
              │   │  command-wait loop ◄──► ipc_commands/ + ipc_responses/ │                 │
              │   │    (agent interviews, 0.5 s file polling)              │                 │
              │   └────────────────────────────────────────────────────────┘                 │
              └──────────────┬────────────────────────┬───────────────────┬─────────────────┘
                             │                        │                   │
                    ┌────────▼────────┐       ┌───────▼────────┐  ┌────────▼─────────────┐
                    │ Supabase        │       │ Zep Cloud      │  │ Filesystem           │
                    │ (Postgres +     │       │ temporal KG    │  │ backend/uploads/     │
                    │  Auth + Storage)│       │ episodes →     │  │ simulations/<id>/    │
                    │ profiles,       │       │ typed nodes /  │  │  (state.json,        │
                    │ scenario_sessions│      │ edges with     │  │  actions.jsonl,      │
                    │ credit RPCs,    │       │ valid_at/      │  │  2× sqlite,          │
                    │ session files   │       │ invalid_at     │  │  run_state, IPC dirs)│
                    └─────────────────┘       └────────────────┘  │ graph_cache/         │
                                                                 │ projects/  reports/  │
                                                                 └──────────────────────┘
```

### 2.2 The 5-step pipeline

From `docs/demo-mode-plan.md:13-21`, mapped to the implementation:

| Step | UI component | Backend stage | Async mechanism | Survives restart? | Typical duration |
|---|---|---|---|---|---|
| 1. Knowledge graph | `Step1GraphBuild.vue` | `POST /api/graph/build` → ontology + Zep episodes + enrichment | `threading.Thread` (`graph.py:627`) | No (in-memory `TaskManager`) | 5–20 min (est.) |
| 2. Env setup | `Step2EnvSetup.vue` | `POST /api/simulation/prepare` → entities → personas → sim config | `threading.Thread` (`simulation.py:580`) | No (in-memory + `state.json`) | 3–15 min for 50 agents (est.) |
| 3. Simulation | `Step3Simulation.vue` | `POST /api/simulation/start` → detached OASIS subprocess | OS subprocess + 2 s monitor thread | Yes — status reconstructs from `run_state.json` | 25 rounds ≈ 14.3 s loop overhead (measured); productive runs minutes-to-tens-of-minutes |
| 4. Report | `Step4Report.vue` | `POST /api/report/generate` → ReACT agent, JSONL journal stream | `threading.Thread` (`report.py:166`) | No | ≈ 6 min (measured, golden tape + V9) |
| 5. Interaction | `Step5Interaction.vue` | `POST /api/simulation/interview/batch` → filesystem IPC into live subprocess | Live process required (IPC, 0.5 s poll) | N/A — dead-end for cached runs | 5–60 s per question (est.) |

### 2.3 The three-store state model — and why each piece lives where it does

| Store | What lives there | Why it lives there |
|---|---|---|
| **Supabase (Postgres + Auth + Storage)** | `profiles` (credits, plan), `scenario_sessions` (prompt, `research_status`, dossier, `bundle_config`, `simulation_count`), `projects`, `simulations`, `reports`, `decision_bundles`, `credit_transactions` (audit ledger), session files in Storage | *User/business state.* Credits must be atomic (database RPCs arbitrate), sessions must survive web restarts and be pollable from any replica, dossiers must persist for the dashboard. The Celery worker writes research state directly to Supabase so the web process needs no broker access to render progress (`research_tasks.py:24-27`). |
| **Zep Cloud** | The knowledge graph itself: typed nodes/edges with temporal fields (`valid_at`/`invalid_at`/`expired_at`), episode history, live graph memory ingested during simulation | *Domain knowledge.* Entity extraction (server-side NER), edges, and long-term memory are Zep's product; Glas trades a metered monthly cost for not building a graph store (`docs/demo-mode-plan.md:27`). The answer to that cost is a read-through disk cache — which is currently **unwired** (see §3.3). |
| **Filesystem** `backend/uploads/simulations/<sim_id>/` | `state.json`, `run_state.json`, `simulation_config.json`, `reddit_profiles.json`, `twitter_profiles.csv`, `twitter/actions.jsonl`, `reddit/actions.jsonl`, `twitter_simulation.db` / `reddit_simulation.db` (SQLite written by OASIS), `simulation.log`, `env_status.json`, `ipc_commands/`, `ipc_responses/` | *Simulation state.* The OASIS toolchain is file-native: it consumes JSON/CSV config and writes SQLite + JSONL itself. The runner reads what OASIS already writes — no DB round-trip in the hot path — and `run_state.json` survives restarts so a run can be reconstructed after redeploy (`simulation_runner.py:242-295`). |

**The consequence that shaped the demo:** simulation artifacts are *not* in any database. "Point at an old Supabase row" fails to find profiles/config/action logs behind it (`docs/demo-mode-plan.md:30`). That is the root justification for the record-and-replay demo architecture (§3.5).

**What one real sim directory contains** (verified inventory of `sim_17a78fae63da/`): `state.json` (SimulationState), `run_state.json` (SimulationRunState), `simulation_config.json`, `reddit_profiles.json`, `twitter_profiles.csv`, `twitter/actions.jsonl`, `reddit/actions.jsonl`, `twitter_simulation.db` + `reddit_simulation.db` (SQLite written by OASIS), `simulation.log`, `env_status.json`, `ipc_commands/`, `ipc_responses/`, `tool_registry.json`. Plus, elsewhere: `backend/uploads/graph_cache/<graph_id>/snapshot.json` (format v2) and `backend/uploads/projects/<project_id>/` (extracted text, ontology, project JSON via `ProjectManager`). The whole state model is therefore: Supabase rows (user/business), Zep graph (domain), filesystem (simulation), in-memory `TaskManager` (ephemeral progress) — four tiers, each chosen for its access pattern and durability requirement.

**Two further store choices worth stating:** the in-memory `TaskManager` (`models/task.py:62`) holds all graph/prepare/report progress — process-local, lost on restart — which is why session-based research moved to Supabase rows instead; and `SimulationRunner` keeps `_run_states/_processes/_monitor_threads` in memory (`simulation_runner.py:219-224`) with `run_state.json` as the restart-surviving mirror. The store split follows a simple rule the code sticks to: **user/business state is durable and relational (Supabase), domain knowledge is vendored and metered (Zep), simulation state is file-native (filesystem), and ephemeral progress is in-memory — with a filesystem mirror exactly where restart survival matters.**

**The polling clock** (frontend constants): graph 120 s visible / 300 s hidden / 8 s while building; Step 2 prepare 2 s initial (plus 3 s and 2 s timers); Step 3 run-status 4 s, detail 6 s (`zepFootprint.js:46-49`); agent-log 2 s, console-log 1.5 s; research polls via `session.py` status (any cadence). The demo compresses the whole traverse to ~90 s with `DEMO_SPEEDUP` (`docs/demo-mode-plan.md:78`). The plan's claim that this polling is "already centralised" in `useAdaptiveStepPolling.js` is **false at HEAD** — the composable is dead code and the real intervals are hardcoded per component (verified; see §3.5).

### 2.4 Why this architecture

1. **Async-first with polling everywhere.** Every long stage returns an ID immediately and the frontend polls at 2–8 s cadence. Right shape for stages that run minutes to tens of minutes — and it makes the demo's time-indexed replay trivially faithful (`docs/demo-mode-plan.md:76-78`).
2. **Supabase rows as the inter-process message bus for research.** The Celery worker and the web server coordinate *through the database*, not broker result backends (`research_tasks.py:24-27`). Any web replica can render research progress; the state machine (`none → claiming → queued → processing → completed/failed`) is race-safe by construction via a conditional-UPDATE claim.
3. **Subprocess isolation for the simulation.** OASIS brings its own asyncio loop, its own file formats, and its own failure modes. Running it as a killable process group with file-based progress is the only sane way to host it next to Flask; the interview IPC extends that isolation cleanly (full argument in §3.2).
4. **External temporal knowledge graph + disk-cache pattern.** Zep buys temporal edges and retrieval without building a graph store; the read-through snapshot cache (`graph_snapshot_cache.py`, SHA-256 integrity, atomic writes, mutation-generation invalidation, 512 MB LRU) is the exact pattern the static demo reuses at larger scale (`docs/demo-mode-plan.md:37`) — though the cache itself is not yet wired into the live path at HEAD.
5. **The demo tape pattern.** Because the pipeline's artifacts are filesystem-bound and vendor-heavy, the demo records one real frontend-driven run into a time-indexed JSON tape and replays it statically — "a pure function of committed JSON" that cannot rot (`docs/demo-mode-plan.md:72`). This is the single strongest architectural decision in the portfolio.

**How to read the diagram.** Three arrows matter: (1) the **Celery path** carries only research — the worker writes to Supabase rows, never to the filesystem, so progress survives deploys; (2) the **subprocess path** is the simulation's private world — the API only reads what OASIS writes (JSONL, SQLite) and only writes IPC command files, so the two processes share nothing but the filesystem; (3) the **threads** (graph, prepare, report) are drawn inside the Flask box deliberately — they are the weak point, dying with the process and losing in-memory progress. The demo adapter is drawn as a browser-side bypass of the whole backend: with `VITE_DEMO_MODE=1`, axios and fetch both route through `tape.json`, and the zero-origin e2e test guarantees nothing else is reachable.

### 2.5 How one request flows end to end (the 60-second version)

A visitor types "NHS England Pharmacy First payment caps" and uploads three policy PDFs. `POST /api/session` mints a `scenario_sessions` row (credit deducted atomically by a Postgres RPC), files land in Supabase Storage. Research starts: an atomic claim flips the row to `claiming → queued`, a Celery worker on the `research` queue picks it up and calls the research chain — deep research (30–45 min) or the Tavily search chain — and writes the dossier back to the *row*, which the browser polls. Then Step 1: `POST /api/graph/build` spawns a thread that chunking the dossier text and feeds it to Zep as episodes; Zep's NER returns typed nodes and temporal edges; an enrichment loop tops the graph up to ~50 entities. Step 2: `POST /api/simulation/prepare` (another thread) reads those entities, generates a persona for each (LLM, parallelism 5), and writes `reddit_profiles.json` + `twitter_profiles.csv` + a config. Step 3: `POST /api/simulation/start` spawns the detached OASIS subprocess; a monitor thread tails `actions.jsonl` every 2 s and mirrors progress into `run_state.json`; the browser polls every 4 s. Step 4: `POST /api/report/generate` (a third thread) runs the ReACT writer — plan phase, then per-section tool calls against the graph and the sim artifacts, journaled to `agent_log.jsonl` and polled at 2 s. Step 5: the browser asks `POST /api/simulation/interview/batch`, which writes a JSON command file into the sim directory; the still-resident OASIS process answers in 0.5 s-polled response files, and the simulated pharmacist tells the user — in persona — why the payment cap matters to her. If the subprocess is gone, Step 5 400s: that single constraint drove the demo's canned-Q&A design.

That whole traverse took 44 min 37 s wall-clock in the golden run — and the demo replays it in ~90 s from static JSON.

## 3. The Seven Technical Domains — in depth

**How to read this section:** each domain has the same four-part shape — *What it does* (the real routes/functions with `file:line` refs), *Technical deep-dive* (the interesting mechanics), *Architecture rationale & trade-offs* (why, and the genuine weaknesses), and *Verified metrics* (measured with provenance, or explicitly marked `(est.)`). Corrections forced by the adversarial cross-check are marked `(corrected)` inline; the verification ledger in §6 records how every load-bearing claim was checked.

| Domain | The headline mechanic | The headline weakness |
|---|---|---|
| 1. Orchestration & data flow | Supabase rows as the inter-process bus; subprocess boundary with file-based progress | "Async" is mostly threads; 2 of 6 stages survive restarts |
| 2. Simulation (OASIS) | Rowid incremental reads; side-channel tool logger; EffectEngine; dual-LLM | Live-process-only interviews; silent empty runs; env mutation hazard |
| 3. Research & knowledge graph | Three-tier agent chain; temporal Zep edges; critique loop; MC risk layer | Config drift → hard crash; cache unwired; forecast scoring orphaned |
| 4. Report & interaction | Hand-rolled ReACT with quant-first enforcement; journal streaming | 3,019-line monolith; bundle synthesis doubly broken; Step-5 demo gap |
| 5. Frontend & demo mode | Record-once/replay-anywhere tape engine; virtual clock; watchdog | Demo glue uncommitted; giant SFCs; ~2,800 lines dead code |
| 6. Infra/CI/CD/observability | 8-job CI; hard-won Hetzner ops history; keyless Pages build | CI red at 3 levels; 6 non-blocking gates; observability orphaned |
| 7. Data/auth/billing | Atomic credit RPCs; exactly-once refunds; schema consolidation | Backend does not boot; `normalize_plan` phantom; RLS gap |

---

### 3.1 Domain 1 — Orchestration & Data Flow

#### What it does

The request lifecycle from intake to interview, with the real route/function names:

1. **Intake.** `POST /api/session` → `create_session` (`api/session.py:25-54`): plan gate (`plan == "free"` → 403), prompt ≥ 10 chars, credit deduction via `SupabaseDB.deduct_credit` (`session.py:41`) → the atomic RPC `deduct_credit_atomic` with a read-modify-write fallback (`services/supabase_client.py:149-181`); insufficient → 402 `insufficient_credits`. Files go to **Supabase Storage** with signed-URL reads (`session.py:119-167`).
2. **Research dispatch.** `POST /api/session/<id>/research` → `start_research` (`session.py:173-312`): double-start guard (409), **atomic claim** (`UPDATE scenario_sessions SET research_status='claiming' WHERE id=? AND research_status=<old>` — with a documented `.or_()` workaround for supabase-py 2.x, `session.py:202-216`), research credit deduction, then `run_deep_research_task.apply_async(..., priority=<plan-mapped 9/5/1>)` → the `research` queue (`celery_app.py:39`, priority map `session.py:258-259`). On queue failure: status reverted, credit refunded, 500 (`session.py:281-310`).
3. **Research execution.** `run_deep_research_task` (`tasks/research_tasks.py:12-95`): `acks_late=True, max_retries=0, soft_time_limit=2700, time_limit=2760` (45/46 min, aligned to the OpenAI client timeout). Writes `processing` → runs the agent chain → writes dossier + `completed`; on exception writes `failed` and **refunds the credit unless it was a retry** (`research_tasks.py:85-95`). Empty-`summary_md` guard: "successful but empty" is treated as failure so the credit is refunded (`research_tasks.py:69-74`).
4. **Research status.** `GET /api/session/<id>/research/status` (`session.py:315-410`) — the web server polls a **row**, not a broker. Stale-run detection: `STALE_RESEARCH_MINUTES = 50` (`session.py:22`) refunds + marks failed (`session.py:373-396`).
5. **Graph build (thread).** `POST /api/graph/build` → `build_graph` (`api/graph.py:363-645`): `threading.Thread(target=build_task)` (`graph.py:627-628`); chunking, `add_text_batches`, enrichment to `target_entities`, then project → `GRAPH_COMPLETED`. Progress via the **in-memory** `TaskManager` (`models/task.py:62`) — lost on web-server restart.
6. **Simulation setup (thread).** `POST /api/simulation/prepare` (`api/simulation.py:350-608`) → `SimulationManager.prepare_simulation` (`simulation_manager.py:229-467`): read/filter entities from Zep capped at plan `max_agents` (25/50/75/200, `config.py:86-93`), per-agent persona generation (parallel 5), LLM config generation, status → `READY`.
7. **The run (subprocess).** `POST /api/simulation/start` → `start_simulation` (`api/simulation_run_routes.py:24-222`): rounds computed from `time_config`, capped by plan (`simulation_runner.py:350-364`), then `subprocess.Popen([sys.executable, scripts/run_parallel_simulation.py, ...], stdout=simulation.log, start_new_session=True)` (`simulation_runner.py:420-452`) plus a **daemon monitor thread** tailing `twitter/actions.jsonl` + `reddit/actions.jsonl` every 2 s (`simulation_runner.py:483-517`), persisting `run_state.json` each cycle.
8. **Report (thread).** `POST /api/report/generate` (`api/report.py:25-188`): dedupe if a completed report exists, then thread dispatch → `ReportAgent.generate_report` — per-section ReACT loop (details in §3.4).
9. **Interviews.** `POST /api/simulation/interview[/batch|/all]` (`api/simulation_interview_env_routes.py:26-306`): hard gate `SimulationRunner.check_env_alive` (`:100-106`) → reads `env_status.json`; if dead → 400. If alive: prompt prefixed to suppress tool use, then `SimulationIPCClient.send_command` writes `<uuid>.json` to `ipc_commands/` and polls `ipc_responses/` every 0.5 s up to **60/120/30 s** timeouts (`simulation_ipc.py:117-187`; `(corrected)` — a 180 s figure in an earlier report was unverified).
10. **Report streaming.** `GET /api/report/<id>/agent-log?from_line=N` (`report.py:769-868`, cursor-based) — the demo tape keys these per cursor (`docs/demo-mode-plan.md:110`); progress via `POST /api/report/generate/status` (`report.py:190`).
11. **Deep-interaction extras.** `POST /api/report/chat` (`report.py:463`) and `/api/simulation/suggest-followups` (`simulation_interview_env_routes.py:513-587`) are plain LLM calls — the report-agent chat truncates the report to 15,000 chars and allows ≤2 tool calls; follow-up suggestions use the graph context.
12. **Frontend polling cadence.** `GET /api/simulation/<id>/run-status` every 4 s, `/run-status/detail` every 6 s (`zepFootprint.js:46-49`); `/actions`, `/timeline`, `/agent-stats`, `/posts`, `/comments` (`simulation_run_routes.py:431-659`) read the JSONL files and per-platform SQLite DBs OASIS writes.

#### Technical deep-dive — the interesting mechanics

**The research state machine is the cleanest piece of systems work here.** `none → claiming → queued → processing → completed/failed` with an optimistic-lock claim means two concurrent POSTs cannot double-start a session (the loser's UPDATE affects zero rows → 409). "Completed but empty" is content-aware: `has_real_content = bool(summary_md.strip())` distinguishes a real success from a silent LLM failure, and the retry is free (`session.py:194-208`). The stale timeout at 50 minutes was calibrated *above* the 46-minute hard kill precisely so a legitimate run can never be reclaimed mid-flight (`session.py:16-21`).

**The queue topology is honest about its own limits.** Only **two** production `apply_async` calls exist (`glas.deep_research`, `glas.run_bundle`). Everything else — graph build, prepare, report, legacy research — is a bare `threading.Thread` inside the web process. The Celery twins (`glas.build_graph`, `glas.prepare_simulation`, `glas.run_simulation`, `glas.generate_report`, `glas.run_full_pipeline`) are written but **never dispatched** — dead code. So "async" here means "survives the HTTP request, not the process" for four of six stages. This is the single biggest architecture-truth gap between the code and its documentation, and it is stated plainly here because it is interview-critical.

**The production queue topology (exhaustive — there is nothing else):**

| Task | Queue (`celery_app.py:38-41`) | Dispatch site | Limits |
|---|---|---|---|
| `glas.deep_research` | `research` | `session.py:262` | `acks_late=True, max_retries=0, soft=2700 s, time=2760 s` (`research_tasks.py:12-20`) |
| `glas.run_bundle` | `simulation` | `bundle.py:264` | `acks_late=True, max_retries=0, soft=14400 s, time=14700 s` (`bundle_tasks.py:58-65`) |

Global worker config: JSON serialization, `task_track_started=True`, `acks_late=True`, `prefetch_multiplier=1`, default soft/time limits 3600/3900 s, `task_max_retries=3`, priority_steps 0–9 with `queue_order_strategy="priority"`. Note the subtlety: `acks_late` + `prefetch=1` were chosen for long tasks, but with `max_retries=0` on the two real tasks, redelivery only matters for worker *crash*, not task *failure* — the documented rationale for bundles lives at `bundle_tasks.py:53-57`.

**Async boundaries in practice:**

| Stage | Async mechanism | Survives web restart? | Progress store |
|---|---|---|---|
| Research | Celery (`research` queue) | Yes | Supabase row |
| Graph build | Thread | No | in-memory `TaskManager` |
| Simulation prepare | Thread | No | in-memory `TaskManager` + `state.json` |
| Simulation run | **OS subprocess** + monitor thread | Run survives via `run_state.json` (process doesn't); status reconstructable | `run_state.json` |
| Report | Thread | No | in-memory `TaskManager` + report files |
| Interviews | Live IPC into subprocess | N/A (requires live env) | SQLite `trace` tables |

Every expensive stage returns 202-style immediately and is polled. The notable *synchronous* exceptions: the Zep entity pre-count during `/prepare` (`simulation.py:462-471`, failure tolerated), all interview endpoints (block the HTTP thread up to 60–120 s while the subprocess answers), and `/report/chat`.

**The subprocess boundary is where the care went in.** Every detail is deliberate and commented: stdout/stderr → *file, not pipe* ("prevent process blocking from full stdout/stderr pipe buffers", `simulation_runner.py:430-432` — a pipe would deadlock a multi-minute run); `start_new_session=True` creates a process group so `os.killpg` can terminate OASIS's children on stop/shutdown (`simulation_runner.py:441, 759-774`, Windows gets `taskkill /T /F`); `PYTHONUTF8=1` + a Windows `builtins.open` monkeypatch because OASIS's third-party libs read files without encoding (`run_parallel_simulation.py:35-65`); `cwd=sim_dir` because OASIS writes SQLite relative to the working directory; SIGINT/SIGTERM/SIGHUP + `atexit` cleanup with 10 s SIGTERM→SIGKILL escalation (`simulation_runner.py:721-774`). Verified in the real artifact: `sim_17a78fae63da/run_state.json` shows `runner_status: "stopped"` with `error: "Server shutdown, simulation terminated"` — the harness caught the process at shutdown. The script then **enters wait-for-command mode with the environments still resident** (`run_parallel_simulation.py:279-317`) — that is what makes interviews possible.

**The spawn itself** (`simulation_runner.py:420-452`):

```python
subprocess.Popen(
    [sys.executable, "scripts/run_parallel_simulation.py", "--config",
     "<sim>/simulation_config.json", ("--max-rounds", N)?],
    cwd=<sim_dir>, stdout=<sim_dir>/simulation.log, stderr=STDOUT,
    text=True, bufsize=1, env=env, start_new_session=True)
```

Then a **daemon monitor thread** tails both platforms' `actions.jsonl` every 2 s (`simulation_runner.py:483-517`), converting lines to `AgentAction`s and per-round summaries, persisting `run_state.json` each cycle. Completion detection runs off the `simulation_end` / `round_end` event lines in the JSONL (`:622-662`) — *both* enabled platforms must finish (`_check_all_platforms_completed`, `:693-718`). The IPC liveness side channel is `env_status.json`, written with `"alive"` on entering command-wait mode (`run_parallel_simulation.py:295`).

**The failure-mode table is genuinely defensive** — every row verified in code, most with commits in history:

| Dependency | Failure | What actually happens | Fallback / recovery |
|---|---|---|---|
| LLM — `insufficient_quota` | Permanent | Detected by code/string, **not retried**, re-raised immediately (`llm_research_agent.py:168-171`) | Router falls to next agent; task marks failed + refunds (commit `f6f04eb`) |
| LLM — TPM rate limit | Transient | Retry-hint regex "try again in X ms/s" (`deep_research_agent.py:40-57`); wait = `max(60 s TPM floor, base 5–90 s, hint)`, cap 180 s; 5 attempts (commit `bc8d536`) | Self-heals inside the task |
| LLM — Cloudflare 5xx / connection | Transient | `_TRANSIENT_STATUS_CODES = {500,502,503,504,520,522,524}`; backoff 5→90 s; `APIConnectionError`/`APITimeoutError` retried (commit `13646ef`) | Self-heals inside the task |
| LLM — "successful" empty response | Silent | Empty `summary_md` → `RuntimeError` → refund + `can_retry` (commits `c3da50b`, `ea0a3a6`, `9a01593`) | Free retry, no 409 |
| Tavily down | — | `tavily.search` exception → agent fails → router fallback | Router falls to next agent |
| Zep down (graph build) | — | Thread catches → project `FAILED`, task `FAILED` with traceback (`graph.py:612-625`); no retry (thread, not Celery) | User re-submits with `force: true` |
| Supabase down (credits) | — | RPC fails → fallback read-modify-write with optimistic `gte` guard (`supabase_client.py:164-181, 199-216, 236-244`) | Non-atomic but functional |
| Redis/Celery down | — | `apply_async` raises → status reverted, **credit refunded**, 500 | The refund-on-queue-failure is the money-safe path |
| Simulation process crashes | — | Monitor: exit ≠ 0 → `FAILED` + last 2,000 chars of `simulation.log` (`simulation_runner.py:531-543`) | `/stop` or `force=true` re-run; `cleanup_simulation_logs` (`:1102-1181`) |
| Stale research run | Worker lost | Poller refunds after `STALE_RESEARCH_MINUTES=50` (`session.py:22, 373-396`) — calibrated > 46-min hard kill (commit `921b0d3`) | Free retry |
| Web restart mid-run | — | Subprocess killed via cleanup hooks; `run_state.json` reconstructs status as `stopped` | Verified in `sim_17a78fae63da/run_state.json` |
| Interview env gone | — | `check_env_alive` false → 400 "environment is not running or has been closed" (`simulation_interview_env_routes.py:100-106`) | None for real runs — the demo must serve canned Q&A |

#### Architecture rationale & trade-offs

**Why async-first with Supabase as the bus:** research is the only stage that must survive deploys and be visible from any replica; the database row is the least-fragile coordination primitive available. Sound choice. **Why threads for the rest:** they were the fast path to ship — but they are the structural weak point: a deploy mid-stage loses progress silently, and threads don't scale to multiple web workers. **Why the subprocess:** OASIS's own event loop, file-native I/O, and crash domain (a runaway model loop kills a child, not the API — monitor marks `FAILED` with the last 2,000 log chars, `simulation_runner.py:531-543`). The cost is **five on-disk state files that must stay coherent** (`state.json`, `run_state.json`, two JSONLs, two SQLite DBs, `env_status.json`) — a crash between writes leaves inconsistent progress (why `/start` gained `check_simulation_prepared` healing, `simulation.py:315-326`, and why `run_state.json` needed purging, commit `224736f`).

**Genuine weaknesses (verified):** (1) "async" mostly means "a thread in the web process" with an in-memory `TaskManager` (`models/task.py:62`); (2) config-drift at HEAD means the research router crashes hard instead of falling back (see §3.3 — `(corrected)`: the original report called this "silent fallback", which the adversarial check disproved); (3) interviews require a live process — a user returning to a completed run cannot re-interview agents, which is why the demo serves canned Q&A; (4) bundle orchestration busy-polls via `time.sleep(10)` with a 2-hour ceiling (`bundle_tasks.py:15, 27-50`) — a wedged simulation blocks the whole bundle.

**Bundle orchestration, the fifth async island.** `POST /bundle/run` dispatches `glas.run_bundle` on the `simulation` queue (`celery_app.py:39`, `bundle.py:264`) with `acks_late=True, max_retries=0, soft_time_limit=14400, time_limit=14700` (a 4-hour hard ceiling, `bundle_tasks.py:58-65`). The task itself spawns per-scenario threads (`bundle_tasks.py:225-240`) and busy-polls their progress via `time.sleep(POLL_INTERVAL=10)` (`:15, 27-50`) with `MAX_PREPARE_WAIT=1800` / `MAX_RUN_WAIT=7200` — a 2-hour wait ceiling with no per-scenario timeouts beyond the task limits, so one wedged simulation blocks the whole bundle. The idempotency trick worth stealing: the Celery task id is predetermined and persisted **before** enqueue (`bundle.py:246-268`), so a crash between the two steps can't double-run a bundle.

**State model — why the split is right (and where it hurts).** The three stores map cleanly onto three access patterns: Supabase rows are the durable coordination layer (any replica can poll them, RPCs keep money atomic, dossiers survive worker restarts); the filesystem holds sim state because OASIS is file-native and `run_state.json` is the restart mirror; Zep holds the graph because temporal edges and server-side NER are the vendor's product. The cost shows up exactly where you'd expect: cross-store coherence (a crash between JSONL/SQLite/run_state writes), the un-wired graph cache (every graph read hits the metered vendor), and the interview dead-end (the sim's memory dies with the subprocess). Those three costs drove the three biggest design decisions in this codebase: the record-and-replay demo, the disk-cache pattern, and the canned-Q&A plan for Step 5.

#### Verified metrics

| Quantity | Value | Provenance |
|---|---|---|
| Full pipeline traverse (golden tape) | **44 min 37 s** (2,677,037 ms; 1,309 API entries; 3.8 MB) | `frontend/public/demo/manifest.json` (measured) |
| Simulation loop, 25 rounds / 8 agents / both platforms | **14.3 s total** — Twitter 4.6 s, Reddit 6.7 s, **0 actions** (all agent LLM calls 401'd) | `sim_17a78fae63da/simulation.log` (measured; `(corrected)` — the original "11.4 min / ~27 s per round" was the subprocess's command-wait lifetime, not the run) |
| Deep research | 30–45 min per code comments; client timeout 2700 s | `deep_research_agent.py:66-67` (est. band, code-grounded) |
| Search (Tavily) research chain | 5–15 min: 3 rounds × 5 queries × Tavily 2–5 s + 3 big LLM writes | (est.; V9 measured 4m10s on a fast provider) |
| Graph build | 5–20 min for a ~50-entity graph (chunk 500/50, batch 3, 3 s episode polls, ≤3 enrichment rounds) | (est.) |
| Simulation prepare | 3–15 min for 50 agents (entity reads + N persona LLM calls at parallelism 5 + config gen) | (est.) |
| Report generation | **≈ 6.2 min** (golden tape: report start → payload timestamps; V9: 6m12s) | (measured; `(corrected)` — an earlier estimate band of 10–25 min was above the measured points) |
| Interviews | 5–60 s per question (0.5 s IPC poll + one LLM call in-subprocess) | `simulation_ipc.py:122` (est.) |
| Frontend polling | Step 2: 2 s/3 s/2 s hardcoded intervals; Step 3 run-status: 4 s, detail: 6 s; agent-log: 2 s; console-log: 1.5 s | component constants (measured) |

#### Reading the golden tape correctly (the single most interview-critical fact)

The golden tape (`frontend/public/demo/pharmacy-first-caps/tape.json`) is a **genuine recording** of a real frontend-driven run — but its simulation stage is empty, and that distinction is the difference between a confident and a shaky interview. What the tape's own payloads say, verified by inspection:

- The `run-status` payloads (`t_ms` 2,018,641 and 2,022,816) name `sim_17a78fae63da` and report `reddit_actions_count: 0`, `total_actions_count: 0`; `run-status/detail` has `all_actions: []`.
- The report payload shows `simulation_metrics: {total_actions: 0, total_agents: 0, total_rounds: 0}` and an empty `escalation_analysis` (peak 0.0, no turning points).
- The tape's own report sections admit it: "The simulation's raw activity tracker recorded **zero logged actions, zero rounds**" and "**Decision recommendation not available for this simulation.**"
- The sim slice in the tape spans `t_ms` 1,993,874 → 2,022,816 ≈ **28.9 s**, not minutes.
- The recorder's log shows why: every agent LLM call 401'd — `"Incorrect API key provided: sk-ant-***tQAA"` sent to api.openai.com, i.e. **an Anthropic key in the `OPENAI_API_KEY` slot** (the `create_model` env-mutation hazard, §3.2).
- The `agree_ratio 87.5%` consensus numbers in the payload were computed from personas/graph facts **over an empty simulation**.

So: the tape proves the *traverse* worked (research ran, graph built, report generated, frontend drove it all for 44 min 37 s), and it also demonstrates the monitoring gap — the UI reported a successful simulation while zero actions occurred. Both sentences should come out of your mouth in an interview, in that order. The fix set is: validate key/endpoint layout at spawn time, fail loudly on zero-action runs, and record a replacement tape against a productive run.

---

### 3.2 Domain 2 — The Simulation Engine (OASIS / camel-ai)

#### What it does

A "round" is one OASIS `env.step()` over a subset of agents in accelerated simulated time. Rounds are computed from the time config: `total_rounds = (total_simulation_hours * 60) // minutes_per_round` (`platform_runners.py:195-200`) — defaults 72 simulated hours at 60 min/round = 72 rounds, capped by plan (free/payg 15, pro 25, business 30, enterprise 50 — `config.py:86-93`) and by `--max-rounds` (`simulation_runner.py:355-362`). Round 0 publishes the scenario's `initial_posts` as `ManualAction(CREATE_POST)` before any agent acts (`platform_runners.py:158-189`), so the policy announcement exists in-world first. Per round, `get_active_agents_for_round` (`time_utils.py:59-130`) samples 5–20 agents (scaled by time-of-day multiplier: peak 1.5, off-peak 0.05, work 0.7), filtered by each agent's `active_hours` and a per-agent Bernoulli on `activity_level`; rounds where nobody is active are skipped without LLM calls — this is how 0–5 a.m. "dead hours" collapse to near-zero cost. The simulated time label is injected into each active agent's system message (cached in `_original_system_content` so it never stacks, `platform_runners.py:240-247`), then `env.step({agent: LLMAction()})` runs all active agents under OASIS's asyncio semaphore — `OASIS_LLM_SEMAPHORE=5` (`platform_runners.py:132, 361`).

Inside an agent: `SocialAgent.perform_action_by_llm` (`oasis/social_agent/agent.py:125-169`) observes the platform text prompt, calls `astep()` (a CAMEL ChatAgent loop), and the returned tool call is **one social action** from the platform's allowed set (Twitter: 6 actions; Reddit: 13 — dislike, comments, search, trend, mute; `INTERVIEW` is deliberately excluded from both, triggerable only via `ManualAction`, `platform_runners.py:36-60`). Agents with tools (web search, scenario actions like `propose_sanction` / `form_alliance`) run them inside that CAMEL loop *before* choosing the social action — tool calls never pass through OASIS's `trace` table.

**Persistence is three layers, each chosen for its access pattern:**

| Layer | What | Where |
|---|---|---|
| OASIS SQLite | Source of truth for social state (posts, follows, trace) | `twitter_simulation.db` / `reddit_simulation.db` in the sim dir (`platform_runners.py:128, 357`) — deleted and recreated per run |
| `actions.jsonl` | The product-facing action stream with `simulation_start/round_start/round_end/simulation_end` event markers | `twitter/actions.jsonl`, `reddit/actions.jsonl` (`action_logger.py:36, 43-66`) |
| `run_state.json` | Real-time API mirror, rewritten every ~2 s by the Flask monitor thread | `backend/uploads/simulations/<id>/` (`simulation_runner.py:483-516`) |

**The round lifecycle in full** (`platform_runners.py:191-295` Twitter, `:428-533` Reddit):

1. Round 0 — the scenario's `initial_posts` are published as `ManualAction(CREATE_POST)` via a direct `env.step()` before the loop (`:158-189`), so the policy announcement exists in-world before any agent acts.
2. Scheduling — `get_active_agents_for_round` (`time_utils.py:59-130`) samples `agents_per_hour_min..max` (5–20) scaled by the time-of-day multiplier, filtered by each agent's `active_hours` and a per-agent Bernoulli on `activity_level`; the sample is `random.sample` — **non-deterministic, no seed**.
3. Time injection — the simulated time label is prepended to each active agent's system message, cached in `_original_system_content` so it never stacks (`:240-247`).
4. The step — `actions = {agent: LLMAction() for active agents}` then `await env.step(actions)` (`:249-250`); inside OASIS, `step()` refreshes the recommendation table, then runs every agent's LLM action concurrently under an asyncio semaphore (`oasis/environment/env.py:136-180`).
5. Day/night gating — rounds with no active agents are logged and skipped without LLM calls (`:234-237`) — this is how 0–5 a.m. "dead hours" collapse to near-zero cost.
6. Extraction — `fetch_new_actions_from_db` polls the SQLite `trace` table incrementally by rowid (`db_utils.py:75-164`), maps rows through `ACTION_TYPE_MAP`, filters noise (`refresh`/`sign_up`), and enriches in place with post content/author names (`_enrich_action_context`, `:167-273`); side-channel tool calls and EffectEngine state-effects are prepended/appended around them (`platform_runners.py:252-264`).
7. Shutdown — `_shutdown_event` checked at the top of every round for a clean break (`:212-215`); SIGTERM/SIGINT handled via `setup_signal_handlers` (`run_parallel_simulation.py:337-365`).

**The IPC / interview system in detail.** Backend side: `SimulationIPCClient` (`simulation_ipc.py:95-285`) writes `<uuid>.json` into `ipc_commands/` and polls `ipc_responses/` for the matching command id (0.5 s interval, 60 s default timeout). Simulation side: `ParallelIPCHandler` (`lib/ipc.py:30-414`) polls the commands dir inside the command-wait loop (`run_parallel_simulation.py:298-308`), executes, writes the response, and deletes the command file (`ipc.py:92-111`). Liveness is the heartbeat file `env_status.json` (`"alive"` written on entering wait mode, `ipc.py:59-67`). Interview execution injects `ManualAction(INTERVIEW, {"prompt": ...})` into `env.step()` for the target agent (`ipc.py:142-149`); inside OASIS, `perform_interview` (`oasis/social_agent/agent.py:197-240`) uses the agent's **full memory context** — system prompt minus the response-format section plus memory — with a plain-text instruction, so the answer arrives in the persona's voice drawing on everything that happened in the sim. The answer is written to the platform SQLite `trace` table (`action='interview'`), which the handler reads back (`ipc.py:330-371`). Route surface: `/interview`, `/interview/batch`, `/env-status`, `/suggest-followups` (`simulation_interview_env_routes.py`). The report agent consumes the same machinery as a **qualitative tool** (`report_agent.py:554-563`, `zep_tools.py:1257-1399`): LLM-selected agents, LLM-generated questions, dual-platform answers, consolidated into the report.

**The dual-LLM hazard, made concrete:** `create_model` mutates the process-wide `os.environ["OPENAI_API_KEY"]` (`model_factory.py:55-56`) — this works today only because each platform's model is instantiated at graph-build time before the other platform's `create_model` call overwrites the env var. Reverse the order and Twitter silently uses the boost key. **This is exactly what happened in the golden demo run**: an Anthropic key sat in the `OPENAI_API_KEY` slot, every agent LLM call 401'd, and the run completed "successfully" with zero actions (see §4, Story D2-3).

#### Technical deep-dive — the interesting mechanics

**Rowid-based incremental reads.** After each step the runner polls the SQLite `trace` table **incrementally by rowid** (`db_utils.py:75-164`) — deliberately not by `created_at`, because Twitter stores integer timestamps and Reddit stores datetime strings (`db_utils.py:85, 104`). Rows map through `ACTION_TYPE_MAP`, noise filtered (`refresh`/`sign_up` dropped), then **enriched in place** with post content and author names via follow-up queries (`_enrich_action_context`, `:167-273`) so the frontend timeline needs no further joins. This is a small cross-platform integration insight with real teeth.

**The side-channel tool logger.** Because OASIS only records *final social actions* in `trace`, every tool wrapper also logs to `tool_calls.jsonl` through a thread-safe `ToolCallLogger` with **per-reader byte offsets** — Twitter and Reddit loops consume the same file independently without stealing each other's entries (`simulation_tools.py:31-115`; consumers at `db_utils.py:40-70`). A `contextvars` wrapper attributes each call to the right agent (`simulation_tools.py:609-634`). A blind spot (tool calls invisible to the product stream) became a first-class data source (`TOOL_*` actions).

**Persona generation — the pipeline from graph to believable agents.** `OasisProfileGenerator.generate_profiles_from_entities` (`oasis_profile_generator.py:850-1009`) runs a `ThreadPoolExecutor` (parallelism 3–5) over the Zep graph entities. Profiles are written **in real time** to disk as they complete (`save_profiles_realtime`, `:888-916`) — a mid-run failure still leaves a usable partial file. Two character classes by design: `INDIVIDUAL_ENTITY_TYPES` (student, professor, official…) get a 200-word bio + **2,000-word persona** with age/gender/MBTI/profession and a mandatory "personal memory" section; group entities get an account-style persona with `age: 30`, `gender: "other"` (`:676-771`) — a regulatory agency and a pharmacist are deliberately *not* written as the same character class. Each persona is grounded in graph facts: Zep hybrid search (edges + nodes, parallel threads with retry) merged with entity attributes and related nodes (`:285-486`). Resilience: 3 LLM attempts with temperature annealing (`0.7 − attempt × 0.1`), truncated-JSON repair, partial extraction from corrupted JSON, then rule-based archetype fallback (`:536-669, 773-844`) — a failed single profile degrades to a minimal profile, never aborts the batch. The format split is an OASIS platform contract, not an aesthetic choice: Twitter profiles are CSV (`user_id,name,username,user_char,description`, with the bio+persona injected into the LLM system prompt as `user_char`), Reddit uses JSON with `persona`/`mbti`/`gender`/`age`/`country` fields — confirmed against `oasis/social_agent/agent.py` usage.

**Tool wiring.** `ToolRegistry.build` (`simulation_tools.py:565-599`): (1) LLM-generates 3–5 scenario-specific tools from the simulation requirement (e.g. `propose_sanction`, `form_alliance`) with declared `effects` (`:314-377`); (2) LLM-assigns each agent a role (`leader/diplomat/analyst/operative/observer/none`, `:482-535`) — pre-assigned `tool_role` fields in the config are reused to avoid a second LLM call. Roles set tool-call depth: leader/diplomat 3, analyst/operative 2, observer 1 (`:675-682`), passed into OASIS's `SocialAgent` via `agent_graphs.py:57-61, 107-111`.

**The EffectEngine — scenario tools that mutate the world.** Scenario tools queue `StateEffect`s (`simulation_effects.py:139-141`) applied between rounds (`apply_pending`, `:143-190`): `suppress_agent`/`boost_agent` mutate the shared config's `activity_level` (floor 0.1, ceiling 1.0, magnitude cap 0.7), changing scheduling probability for both platforms; `create_link`/`break_link` write **directly to the platform SQLite `follow` table** plus in-memory agent-graph edge mutations, with follower/following counter updates; `broadcast` is a visible feed announcement only. Guardrails: 5-round cooldown per (effect, actor, target) and 10 follow-changes per round per platform. Target resolution scans the LLM's action description for known entity names, longest-first (`:121-137`) — a deliberately fuzzy bridge between LLM text and graph IDs. Applied effects land in `state_changes.jsonl` and surface as `STATE_*` actions.

**Dual-LLM design.** `create_model(config, use_boost)` (`model_factory.py:15-69`) picks general (`LLM_API_KEY/LLM_BASE_URL/LLM_MODEL_NAME`) vs boost (`LLM_BOOST_*`) per platform: Twitter → general, Reddit → boost, so two platforms can run truly in parallel against independent quotas — or against a cheaper endpoint. Sequential is the default (`OASIS_SEQUENTIAL_PLATFORMS=1`, "to stay within API rate limits", `run_parallel_simulation.py:258, 264-267`); the `asyncio.gather` concurrent mode still exists behind the env flag (`:269-273`). The per-platform legacy entry points (`run_twitter_simulation.py` / `run_reddit_simulation.py`) still exist and remain wired into `get_run_instructions` (`simulation_manager.py:517-539`).

**Prompt hardening for interviews.** `optimize_interview_prompt` (`simulation_helpers.py:14-20`) prepends a 7-rule prefix (plain text, no tools, no JSON, "Question X:" format) — a fix for LLMs answering interviews in tool-call or Markdown format. The same prefix is used by the report agent's `interview_agents` tool (`zep_tools.py:1330-1347`).

**Platform abstraction — the two environments are deliberately different.** Action sets are hard-coded per platform (`platform_runners.py:36-60`):

| Platform | Action set | LLM assignment | Notes |
|---|---|---|---|
| Twitter | 6 actions (no dislikes/comments/search) | general LLM (`use_boost=False`, `:101`) | CSV profile contract |
| Reddit | 13 actions (dislike, comments, search, trend, mute) | boost LLM (`use_boost=True`, `:331`) | JSON profile contract |

`INTERVIEW` is deliberately excluded from both — it can only be triggered via `ManualAction`. The parallel runner (`run_parallel_simulation.py`) shares one config across both platforms and one subprocess, running them **sequentially by default** ("Running platforms sequentially to stay within API rate limits", `:258, 264-267`); set `OASIS_SEQUENTIAL_PLATFORMS=0` for true concurrency via `asyncio.gather` (`:269-273`). The per-platform legacy entry points (`run_twitter_simulation.py` / `run_reddit_simulation.py`) still exist and remain wired into `get_run_instructions` (`simulation_manager.py:517-539`).

**Measured data points across the repo's evidence trail** (each with its caveat):

- **Golden tape full traverse:** 44 min 37 s, 1,309 entries, 3.8 MB — measured, genuine recording, but its sim slice is empty (§3.1 "Reading the golden tape").
- **V9 dry-run (2026-08-14):** full traverse 32 min 46 s; research slice 4m10s; Step 3 ≈ 30 s for 25 rounds — measured durations; Step-3 *content* unverified (no action counts recorded, and it ran with the dead `OASIS_DEFAULT_MAX_ROUNDS=1` knob — consistent with fail-fast auth errors); report slice 6m12s.
- **Smoke run `sim_17a78fae63da`:** 25 rounds, 8 agents, both platforms, 4.6 s / 6.7 s, 0 actions — measured; the loop overhead is ≈0.18 s/round when LLMs produce nothing; also the live proof that **a failed/silent LLM produces an empty but "successful" run** (no error surfaces; `fetch_new_actions_from_db` swallows exceptions, `db_utils.py:161-162`).

The honest summary: at HEAD there are exactly **two measured end-to-end data points** (golden tape, V9), both with empty-or-unverified simulation content. Productive-run latency figures (the 5–15 min prepare band, the ~5–25 min per-platform sim band) are estimates from code constants, marked as such throughout this document — say "est." out loud when you use them.

#### Architecture rationale & trade-offs

**Why OASIS/camel-ai:** the product needs platform-faithful environments (Twitter's and Reddit's action grammars genuinely differ), long-horizon agents with persistent memory (interviews depend on it), and a community-maintained substrate. Building a bespoke multi-agent social env is months of work; the coupling here is deliberately thin — the runners use only `oasis.make`, `env.step`, `ManualAction`/`LLMAction`, and the agent graph — so OASIS is swappable if the library rots. **Why the subprocess:** crash isolation, independent lifecycle, deterministic stop/restart via process groups, and the scripts predate the Flask service (they were the original product entry point). **Why file-native IPC:** dumb but robust — no sockets/queues to break across restarts, and a human can read and debug the command files.

**The scaling knobs that bound a run:**

| Knob | Default | Source |
|---|---|---|
| Configured rounds | 72 (72 h ÷ 60 min) | `simulation_config_generator.py:86-89`; computed at `platform_runners.py:195-200` |
| Plan round caps | free/payg 15 · pro 25 · business 30 · enterprise 50 | `config.py:86-93` |
| Plan agent caps | 25 / 50 / 75 / 200 (top-N by edge count) | `config.py:86-93`, `simulation_manager.py:287-295` |
| `--max-rounds` | CLI arg; hard-capped by plan (`min(max_rounds, hard_cap)`) | `simulation_runner.py:355-362` |
| LLM concurrency | `OASIS_LLM_SEMAPHORE=5` per platform → OASIS `llm_semaphore` | `platform_runners.py:132, 361` → `oasis/environment/env.py:128-131` |
| Active agents/round | 5–20 × time multiplier (peak 1.5, dead hours 0.05) | `time_utils.py:74-75` |

**Cost model:** LLM calls ≈ Σ over rounds of (active agents × (1 + tool iterations)) per platform. A pro run: 25 rounds × ~5–20 active agents ≈ **125–500 LLM actions per platform** (est.); tool-role agents multiply by up to 3. At semaphore 5 and ~2–6 s/call (est.), one platform is ~5–25 min for 25 rounds (est.); sequential platforms ≈ double. The plan caps are the primary cost-control lever.

**Genuine weaknesses (verified):**
1. **Interviews cannot be replayed.** Answers require the live process's in-memory memory plus the SQLite `trace`; a cached/completed run is un-interviewable. The report agent's `interview_agents` tool silently proceeds without qualitative data when the env is dead.
2. **Stale-alive false positives.** `check_env_alive` trusts `env_status.json`, which is only updated on graceful paths — a SIGKILLed subprocess leaves "alive", so clients burn the full 60–120 s timeout before erroring.
3. **Process-global env mutation** (above) is order-sensitive and silent — demonstrated to break a run.
4. **Silent empty runs.** LLM failures yield 0-action "successful" rounds; `fetch_new_actions_from_db` swallows DB exceptions (`db_utils.py:161-162`). The 25-round/0-action smoke run completed as a *normal* run — this is the exact failure class that killed the golden demo (see §4, D2-3).
5. **No RNG seed anywhere** — same config twice yields different runs; reproducibility claims are unsupported.
6. **Dead knob:** `Config.OASIS_DEFAULT_MAX_ROUNDS` (default 10) is consumed nowhere — V9 set it to 1 and the sim still ran 25 rounds. The real caps are `simulation_limits(plan)` + `--max-rounds`. Wire it or delete it.
7. **Minor bug:** `log_simulation_start` writes `total_rounds = hours * 2` (assumes 30-min rounds; logs 144 instead of 72 for 60-min rounds). The monitor ignores it (rounds come from `round_end` events) — but the number in the log file is wrong.

#### Verified metrics

| Quantity | Value | Provenance |
|---|---|---|
| Round computation | 72 h ÷ 60 min/round = 72 nominal rounds; plan caps 15/25/30/50 | config + `platform_runners.py:195-200` (measured constants) |
| Agent caps | 25 free / 50 pro / 75 business / 200 enterprise; top-degree entities kept | `config.py:86-93`, `simulation_manager.py:287-295` |
| LLM concurrency | `OASIS_LLM_SEMAPHORE=5` per platform | `platform_runners.py:132, 361` |
| Loop overhead | 25 rounds, 8 agents, both platforms: **14.3 s, 0 actions** (≈0.18 s/round non-LLM overhead) | `sim_17a78fae63da/simulation.log` (measured) |
| V9 dry-run Step 3 | 25 rounds in ≈ 30 s wall-clock (20:10:58 → 20:11:28) — **action content unverified**; consistent with fail-fast auth errors, not productive LLM calls (`(corrected)` — an earlier report called this "fast provider"; it's unverified as to content) | `V9-evidence.md:22-23` (measured duration, unverified content) |
| Cost model | Pro run: 25 rounds × 5–20 active agents ≈ **125–500 LLM actions per platform** (est.); tool-role agents multiply by up to 3 | `time_utils.py:74-75`, `simulation_tools.py:675-682` (est.) |
| Per-platform duration | ~5–25 min per 25 rounds at 2–6 s/call, semaphore 5 (est.); sequential platforms ≈ 2× | (est.) |
| Timeouts | IPC: 60 s single / 120 s batch / 30 s close-env (`(corrected)`) | `simulation_ipc.py:121, 228, 254` |

---

### 3.3 Domain 3 — Knowledge Graph & Research Pipeline

#### What it does

The research chain is config-driven (`research_router.py:27-44`):

| Priority | Agent | Condition | Notes |
|---|---|---|---|
| 1 | `DeepResearchAgent` | `DEEP_RESEARCH_ENABLED=1` (default **false**) | OpenAI Responses API + `web_search_preview` tool; 30–45 min; `max_tool_calls=50`; SDK timeout 2700 s to outlive the Celery soft limit (`deep_research_agent.py:60-97`) |
| 2 | `SearchResearchAgent` | `SEARCH_RESEARCH_ENABLED` | Tavily live search + iterative Claude chain — "roughly 90% of deep-research quality at a fraction of the wall-clock and token cost" (`research_router.py:10-11`) |
| 3 | `LLMResearchAgent` | fallback | Training-knowledge only, no live search, single 4096-token call (`llm_research_agent.py:104-166`) |

All three produce the **same dossier schema** (`summary_md`, `sources`, `key_facts`, `historical_precedents`, `quantitative_anchors`, `structured_precedents`, `search_queries`, `selected_angles`), so the Celery task and downstream consumers never care which agent ran.

**`(corrected)` — the HEAD reality:** `Config.SEARCH_RESEARCH_ENABLED` (and `SEARCH_RESEARCH_MODEL`, `TAVILY_API_KEY`, `SEARCH_RESEARCH_MAX_ROUNDS`, `SEARCH_RESEARCH_QUALITY_THRESHOLD`, `RESEARCH_CLASSIFICATION_MODEL`, `DEEP_RESEARCH_MAX_OUTPUT_TOKENS`) **do not exist in `config.py`** (137 lines — verified; `git log -S` shows they were never defined; a plan from 2026-05-17 specified them but was only partially merged). `research_agent_chain()` evaluates `Config.SEARCH_RESEARCH_ENABLED` at `research_router.py:36` **outside** the per-agent try/except — so the `AttributeError` propagates out of `run_research_chain` → the Celery task marks `failed` + refunds. This is a **loud crash with a credit refund**, not a silent fallback to the LLM-only agent. (An earlier report claimed "silent quality degradation"; the adversarial cross-check disproved it — the fallback story only holds in the counterfactual where the attribute exists.)

#### Technical deep-dive — the interesting mechanics

**The Tavily chain** (`search_research_agent.py:150-230`): (1) query generation — LLM produces "4–6 precise web search queries" (`temperature=0.3`, JSON-parsed, fallback to the raw scenario truncated to 200 chars); (2) live search — `tavily.search(q, max_results=5)`, `search_depth="advanced"`, 15 s timeout (`tavily_client.py:27`); (3) synthesis — context truncated to 40,000 chars, system prompt demands an 11-section dossier of 3000–6000 words with 20–40 named entities, `max_tokens=12000`; (4) **critique loop** — an LLM judge scores 0–10 and returns gaps + follow-up queries; loop exits on `score >= 7.5 or round >= 3 or no follow-ups` (`:197-198`); (5) **verification pass** — cross-checks claims against search results and appends a `## Verification Notes` section labelling verified/unverified/corrected claims; never raises, only runs when sources exist (`:296-345`); (6) post-processing — key-fact/precedent extraction from markdown headings, URL dedup. Worst case: 3 rounds × 6 queries × 5 results ≈ 90 source items, plus 3 LLM calls per round.

**The DeepResearchAgent mechanics.** A single `responses.create` call with `tools=[{"type": "web_search_preview"}]`, `max_tool_calls=50` (config default), SDK timeout 2700 s — deliberately set to outlive the Celery soft limit so the SDK never kills a run the scheduler hasn't (`deep_research_agent.py:66-67`, matched by `research_tasks.py:17-19`). `_parse_response` (`:198-292`) accumulates text across **all** `output_text` blocks — a prior bug silently dropped earlier chunks — records `web_search_call` queries, extracts annotation URLs as sources, and raises `RuntimeError` on incomplete/failed status **only if no text was recovered** (`:266-270`) so the Celery task can refund the credit. `_structure_precedents` (`:331-402`) LLM-converts precedents into scored objects (`relevance_score`, `key_metric`, `source_url`).

**The fallback agent** (`llm_research_agent.py:104-159`): same output schema, training-knowledge only (`sources: []`, `search_queries: []`), single `llm.chat` with `max_tokens=4096` (`:166`), same markdown extraction helpers — a deliberately thin last resort.

**The knowledge graph (Zep Cloud).** Graphs are named `glas_<uuid4hex16>`; the ontology is *dynamically built* pydantic `EntityModel`/`EdgeModel` subclasses (`graph_builder.py:199-280`) with Zep's reserved attribute names renamed (`:211-217`). The dossier's source text is chunked at **500 chars / 50 overlap / batch 3** (`graph_builder.py:58-59` — `(corrected)`, an earlier report said 300/30) and fed as `EpisodeData` batches; **Zep's own server-side NER turns episodes into typed nodes/edges — Glas never calls an entity extractor**. Edges carry `fact`, `valid_at`, `invalid_at`, `expired_at`, `episodes` (`graph_builder.py:432-463`) — **this is the temporal dimension** that makes the product different: retrieval can distinguish *active* vs *historical* facts (`PanoramaSearch`, `zep_tools.py:1131-1220`). During simulation, `ZepGraphMemoryUpdater` (`zep_graph_memory_updater.py:201-548`) streams agent actions back into the graph as natural-language episodes (batch 5, 3 retries, flush on stop) — simulated interactions become temporally-validated edges the report agent can query.

**Enrichment loop.** `GraphEnrichmentService` (`graph_enrichment_service.py:82-177`) compares the LLM's pre-scanned `entity_inventory` against actual graph nodes, then up to `MAX_ENRICHMENT_ROUNDS=3` rounds of LLM-written "encyclopedic-style" passages (100–200 words, explicitly banned from inventing relationships) until `target_entities` (default 50) is reached or a stopping condition hits (`target_reached / no_new_nodes / no_missing_entities / max_rounds`).

**Angles.** `research_angles.py` defines 10 `ResearchAngle`s with directives + search hints (`:27-168`). `classify_scenario()` (`:198-226`) is a cheap LLM call that picks the relevant angles — on failure it falls back to *all* angles (`:226`). Only `DeepResearchAgent` uses the classifier; `SearchResearchAgent`/`LLMResearchAgent` default to all 10 with user `angle_overrides` applied.

**The `research_status` state machine** (API `session.py` + Celery `research_tasks.py` + migration `004_scenario_sessions.sql:14`):

```
NULL/none ──POST /research──▶ claiming ──▶ queued ──▶ processing ──▶ completed
     ▲    (atomic CAS update)    │           │            │  (dossier persisted)
     │                           │           │            │
     └─────────── failed ◀───────┴───────────┴────────────┘
                 (credit refunded)
```

Claiming is an optimistic `UPDATE ... research_status='claiming'` filtered by the prior status (`session.py:202-216`); a no-op result → 409. In-progress statuses block re-start. Completed-but-empty is retryable and free; failed runs refund; stale `processing` older than 50 min is force-failed + refunded on poll; the worker skips if already `completed` and stores errors as `research_dossier={"error": ..., "error_type": ...}` (`research_tasks.py:43-45, 91`); abandoning a session marks in-progress research failed (`session.py:425-427`).

**Entity extraction & retrieval.** Zep's server-side NER is the only extractor; Glas's ontology definitions are the only extraction logic. Reading back: `ZepEntityReader.filter_defined_entities` (`zep_entity_reader.py:214-324`) keeps non-generic-labeled nodes, enriches with in/out edges, and **deduplicates by normalised name** with a known-alias map (e.g. `pharmacistsdefenceassociation → pda`, `:326-368`). The retrieval toolset (`zep_tools.py`): `search_graph` uses Zep hybrid search with `reranker="cross_encoder"` (`:476-486`) and **falls back to local keyword matching** when the API fails (`:528-530`, `_local_search:532-634`); `InsightForge` (`:931-1076`) decomposes a question into ≤5 LLM sub-queries, per-query semantic search, per-entity detail fetch, and relationship-chain tracing; `panorama_search` categorises edge facts into **active vs historical/expired** with `[valid_at - invalid_at]` prefixes (`:1174-1194`); `quick_search`; `get_simulation_context` (`:876-927`) hands graph facts to the report agent and stance analysis. All Zep calls are wrapped in `_call_with_retry` — 3 attempts, exponential backoff from 2 s (`zep_tools.py:428-449`, `zep_entity_reader.py:88-125`).

**The grounding chain — scenario → dossier → agents:** the dossier prompt explicitly names its three downstream consumers ("Entity extraction — every named actor becomes a simulated AI agent… Knowledge graph construction — relationships between actors become graph edges… A social-media simulation", `search_research_agent.py:30-37`). `ContextEnricher` (`context_enricher.py:21-26`; the deep-research variant also ingests dossier sources into `grounding_sources`) enriches the simulation context; `grounding_bundle.py` maintains a grounding ledger — upload sources, web-research sources with stable ids `web_<md5(url)[:12]>`, staleness policy `GROUNDING_MAX_AGE_HOURS=168` (7 days, `config.py:114`) with warn/block toggles, and a claim ledger for the report agent so every report claim can name its evidence.

**The graph cache — engineered, documented, and unwired.** `graph_snapshot_cache.py` implements a textbook read-through disk cache: SHA-256 content integrity, atomic temp-file+rename writes, per-graph **singleflight** locks with double-check, `mutation_generation` invalidation bumped by enrichment, TTL 86,400 s with a `STALE` fallback allowed to 604,800 s after a Zep failure, and a 512 MB LRU quota. `(corrected)` — **at HEAD it is inert**: `GET /api/graph/data/<id>` still calls `builder.get_graph_data(graph_id)` directly (`graph.py:700-701`); `get_graph_data_cached` / `try_stale_fallback` / `try_get_lists_for_entity_reader` have **zero callers**; and the only call site (`graph_tasks.py:78` → `write_snapshot`) crashes on `Config.GRAPH_SNAPSHOT_CACHE_ENABLED` (also missing) — so in the current tree every graph build fails at its final step. Tests pass only because they monkeypatch the missing attribute.

**Research failure modes & fallbacks:**

| Failure | Behaviour | Evidence |
|---|---|---|
| Tavily down / error | `TavilyClient.search` swallows exceptions → `[]`; chain synthesises from training knowledge; verification pass skipped when no sources | `tavily_client.py:42-44` |
| Search agent crashes | Router falls to `LLMResearchAgent` (at HEAD: router itself crashes first — §3.3) | `research_router.py:54-66` |
| OpenAI rate-limit (429/TPM) | ≤5 retries; parses "try again in X" hints; 60 s floor; 60–180 s cap | `deep_research_agent.py:37-38, 121-142`; commit `bc8d536` |
| Cloudflare 5xx / connection | Retry set {500,502,503,504,520,522,524} + connection/timeout errors; backoffs [5,10,30,60,90] | `deep_research_agent.py:30-32, 157-170`; commit `13646ef` |
| `insufficient_quota` | Not retried — re-raised immediately | `llm_research_agent.py:167-171`; commit `f6f04eb` |
| Empty dossier / silent failure | `summary_md` empty → `RuntimeError` → failed → refund; completed-empty retryable free | `research_tasks.py:69-74, 93-95`; `session.py:194-208` |
| Stuck `processing` | 50-min stale timeout → failed + refund on poll | `session.py:22, 372-398` |
| Zep search down | 3 retries then local keyword fallback over fetched nodes/edges | `zep_tools.py:428-449, 528-634` |
| Zep graph reads down | 3 retries exp backoff, then empty/None rather than raising | `zep_entity_reader.py:88-125, 210-212` |
| Zep memory writes fail | 3 retries, then dropped (logged, counted) | `zep_graph_memory_updater.py:406-427` |
| Cache stale after Zep failure | Intended: STALE snapshot within 7 d, `X-Glas-Graph-Cache: STALE` — **not wired** | `graph_snapshot_cache.py:342-348, 467-469` |

**The quantitative layer** (all behind the report agent's tools): `simulation_metrics` (aggregation of action logs); `stance_analysis` (LLM classification into supportive/opposing/neutral/ambivalent, intensity 1–5); `consensus_metrics` (**polarisation index = entropy/max_entropy**); `escalation_analysis` (aggression ratio, turning points at ≥50% round-over-round change, 1.3× half-vs-half trend threshold); `probability_assessment` (LLM low/mid/high triplets through **calibration guardrails**: caps [5, 95], likelihood-ratio bound 20×, ordering enforcement, min 5-point range, correlation discount, capped Bayesian update — `calibration_guardrails.py`); `risk_matrix` (likelihood×impact → severity buckets: critical ≥16, high ≥10, moderate ≥5); `stakeholder_impact_matrix`; `decision_framework` (Go/No-Go with drivers, flip conditions, monitoring indicators). On top: `monte_carlo_engine.py` — deterministic Mulberry32 PRNG (seed 42), 10,000 iterations, triangular/PERT/beta samplers, 90/95/99% CIs via percentile interpolation, 20-bin histograms, convergence check `relative_error < 0.02`. **`forecast_scoring.py`** (Brier + Murphy decomposition, log score, empirical CRPS, calibration curves) is **orphaned** — explicitly "not wired into the live report pipeline yet" (`forecast_scoring.py:4`): measurement of forecast quality doesn't exist, only prompt discipline.

**What each quant tool actually computes** (walkthrough, `quantitative_analysis_service.py`):

- `simulation_metrics` (`:764-814`): totals per platform, action-type distribution, engagement rate (interactive/total), content-creation rate (posts per agent per round), top-5 agents, activity by entity type.
- `stance_analysis` (`:820-912`): LLM classification of every agent persona (plus up to 30 graph facts via `quick_search`) into `supportive/opposing/neutral/ambivalent` with intensity 1–5.
- `consensus_metrics` (`:918-963`): majority position %, agreement ratio, **polarisation index = entropy/max_entropy** (`:936-940`), faction count, cross-group alignment, fault lines.
- `escalation_analysis` (`:969-1033`): per-round intensity curve, aggression ratio (aggressive/(aggressive+positive), `:983-985`), turning points at ≥50 % round-over-round change (`:1005-1015`), trend by half-vs-half means with a 1.3× escalation threshold (`:1017-1029`).
- `probability_assessment` (`:1039-1163`): LLM low/mid/high percentage triplets per outcome, run through calibration guardrails (gated by `ENABLE_CALIBRATION_GUARDRAILS`); raw triplets retained for A/B (`raw_low/mid/high`, `:339-342`).
- `risk_matrix` (`:1169-1252`): likelihood×impact → severity buckets (critical ≥16, high ≥10, moderate ≥5, `:1230-1238`), top-3 sorted.
- `stakeholder_impact_matrix` (`:1316-1385`): per-entity-type stance mix, activity index vs global mean, escalation exposure, voice share.
- `decision_framework` (`:1471-1631`): Go/No-Go verdict with key drivers, causal chain, sensitivity, flip conditions, monitoring indicators, financial summary gated on applicability (`:1547-1550`).

Wired for the report agent: `analyze_metrics`, `assess_positions`, `estimate_risks` (probabilities + risk matrix + Monte Carlo, `:1276-1314`), `stakeholder_impact_matrix`.

**The Monte-Carlo engine's honesty mechanics** (`monte_carlo_engine.py`): deterministic Mulberry32 PRNG "matching glas-core's Mulberry32" (`:25-36`); samplers for triangular/PERT/beta/normal/uniform (`:62-135`); `run_monte_carlo` (`:221-336`) does 10,000 iterations by default, 90/95/99% CIs via percentile interpolation, a 20-bin histogram, tail risk (p1/p5/p99, expected shortfall), and a convergence check (`relative_error < 0.02`) with recommended-iteration scaling (`:304-309`). LLM triplets become PERT distributions on 0–1 (`from_probability_estimate:143-149`); `run_monte_carlo_on_estimates` (per-outcome) and `run_composite_monte_carlo` (mean-of-outcomes favourability, `:390-430`) feed the report. Seed 42 → reproducible. The honest caveat that belongs in any interview: the "uncertainty" is the model's stated range over a fixed seed, not a fitted posterior — statistically respectable, epistemically bounded.

**Why the temporal dimension is the product.** `EdgeInfo` models it explicitly (`zep_tools.py:80-134`): `created_at / valid_at / invalid_at / expired_at` with `is_expired`/`is_invalid` properties and validity-range rendering in `to_text(include_temporal=True)` (`:117-123`). `PanoramaSearch` (`:1131-1220`) is the time-aware retrieval tool: it categorises edge facts into **active** vs **historical/expired** with `[valid_at - invalid_at]` prefixes (`:1174-1194`). The simulation's graph-memory updater is what gives edges temporal metadata — when agent A follows agent B in round 3 and mutes them in round 9, the report agent can retrieve both facts with their validity windows and describe the *change over time*, which is exactly what "predictive business intelligence" needs and what a vanilla property graph can't do without building this machinery from scratch.

**The graph-build pipeline, step by step** (`graph_builder.py` + `graph_tasks.py:15-125`): (1) ontology generation — `OntologyGenerator.generate()` (`ontology_generator.py:170-215`) produces 10 entity types (8 specific + `Person`/`Organization` fallbacks enforced at `:376-432`, Zep's hard cap of 10/10) and 6–10 edge types; (2) `create_graph` mints `glas_<uuid4hex16>`; (3) `set_ontology` registers the dynamically-built pydantic classes with `source_targets` per edge type (reserved attribute names renamed `uuid/name/group_id/name_embedding/summary/created_at` → `entity_<name>`, `graph_builder.py:211-217`); (4) chunk the dossier text (500/50/3) and send `EpisodeData(type="text")` batches, awaiting each batch's `episode.processed` (3 s poll, 600 s timeout, `:331-383`); (5) **enrichment** — compare the LLM's pre-scanned `entity_inventory` against actual nodes and write up to 3 rounds of "encyclopedic-style" passages (100–200 words, explicitly banned from inventing relationships, `graph_enrichment_service.py:273-287`) until the 50-entity target or a stopping condition (`target_reached / no_new_nodes / no_missing_entities / max_rounds`, `:148-161`), bumping the cache generation on each completed round (`:175-176`); (6) snapshot write — intended to be `write_snapshot` (crashes at HEAD on the missing config flag) and project → `GRAPH_COMPLETED`; on failure project → `FAILED` + task → `FAILED` with traceback (`graph.py:612-625`).

**Why the graph build is a thread and not Celery, and why that bit us:** the Celery twin `glas.build_graph` exists and is never dispatched; the route spawns a bare thread (`graph.py:627-628`), so progress lives in the in-memory `TaskManager` and dies with the web process. The doc drift that called it "a Celery task polled every 2 s" is exactly the kind of claim an interviewer can check — and the honest answer is "threads were the fast path, and this is on the known-debt list."

#### Architecture rationale & trade-offs

**Why Zep:** temporal edges + active-vs-historical retrieval are product differentiators; Zep's server-side NER removes all extraction code. **Costs:** vendor lock-in across ~2,000+ lines of SDK-specific code (`graph_builder`, `zep_tools`, `zep_entity_reader`, `zep_graph_memory_updater`); metered billing for every paginated read — the *reason* the disk cache exists and the *reason* its non-wiring matters; a file-based generation counter that breaks under multiple processes with no cross-host coordination. **Why Tavily:** cheap, structured, zero SDK lock-in (a thin `requests` wrapper, `tavily_client.py:14-44`); a deliberate cost/quality trade. **Why multi-round refinement:** the critique loop is a cheap LLM-judged approximation of OpenAI's agentic deep research, with a transparency layer (verification notes) instead of silent claims.

**Documentation drift inventory** (the docs are honest about architecture but stale about implementation — a recurring theme worth naming in an interview): `docs/demo-mode-plan.md:48` claims graph build is "a Celery task polled every 2 s" (it's a thread) and cites `AGENT_TOOLS_MAX_ITERATIONS=3` (doesn't exist; real bounds are 8 iterations / ≥3 tool calls / ≤5 per section, `report_agent.py:1564-1565`); the plan's "polling is already centralised" claim (`:38`) is false at HEAD; the plan's fixture inventory (§2, lines 120–136, duplicated verbatim twice) lists endpoints the shipped tape doesn't contain (no `/actions`, `/timeline`, `/posts`, `/comments`, `/sections`, `/progress`, `/env-status`, `/interview/batch`, `/report/chat`); `docs/graph-cache.md:9, 25` claim the endpoint and entity reader use the cache — false at HEAD; the plan's line counts are stale (`Step2EnvSetup.vue` "1,264" vs actual 2,604; `Home.vue:1343` vs actual 606); and plan §1.4G's claim that the schema file predates migrations 004–009 is stale — the drift is fixed (§3.7). The pattern behind all of it: docs were written at design time and never re-synced after `17fc32a` reshaped the tree — the same commit that shipped the phantom config.

**Genuine weaknesses (verified):** the config-drift crash above (every non-deep-research path crashes at HEAD); the unwired cache; `forecast_scoring` not live; "uncertainty" is the model's stated range over a fixed seed, not a fitted posterior; research runtime of tens of minutes policed by a narrow 50-minute staleness window.

#### Verified metrics

| Quantity | Value | Provenance |
|---|---|---|
| Dossier schema | Identical across all three agents (8 fields) | `research_router.py` + agents (verified) |
| Tavily chain bounds | 3 rounds max, 4–6 queries/round, 5 results/query, 40k-char context, 12,000-token synthesis, 7.5 threshold | `search_research_agent.py` (measured constants) |
| Deep research | Single Responses call, 2700 s timeout, 50 tool calls max, 30–45 min | `deep_research_agent.py:60-97` |
| Chunking | 500 / 50 / batch 3 (`(corrected)`) | `graph_builder.py:58-59` |
| Enrichment | ≤ 3 rounds, target 50 entities, passages 100–200 words | `config.py:68-69` |
| Cache design | TTL 86,400 s; STALE to 604,800 s; 512 MB LRU; format v2 — **unwired** | `graph_snapshot_cache.py` + `docs/graph-cache.md` (verified dead) |
| Monte Carlo | 10,000 iterations, seed 42, CIs 90/95/99, convergence < 0.02 | `monte_carlo_engine.py:221-336` (measured constants) |
| Research slice (V9) | 4m10s measured (fast provider) | `V9-evidence.md` (measured) |

### 3.4 Domain 4 — Report Generation & Agent Interaction Layer

#### What it does

`POST /api/report/generate` (`api/report.py:25-188`) runs a hand-rolled ReACT tool-using writer — `ReportAgent` (3,019 lines, `services/report_agent.py`) — as a daemon thread, streaming progress through a JSONL journal the frontend polls. The real loop bounds (the docs claim `AGENT_TOOLS_MAX_ITERATIONS=3`, which **does not exist anywhere** — another doc drift):

| Constant | Value | Evidence |
|---|---|---|
| `MAX_TOOL_CALLS_PER_SECTION` | 5 | `report_agent.py:982` |
| `max_iterations` (ReACT loop) | 8 | `report_agent.py:1564` |
| `min_tool_calls` (per section) | 3 | `report_agent.py:1565` |
| `MAX_TOOL_CALLS_PER_CHAT` | 2 | `report_agent.py:988` |
| `MAX_REFLECTION_ROUNDS` | 3 — defined, never referenced (dead) | `report_agent.py:985` |

The loop (`_generate_section_react`, `report_agent.py:1485-1837`): thought → `<tool_call>{json}</tool_call>` → observation injected *by the system* (never the model) → repeat → `Final Answer:`. A response containing both a tool call and a final answer is rejected twice with a format-error message, then degraded to truncated execution of the first tool call on the third offence (`:1609-1643`). Tool calls parse from the tagged JSON with two bare-JSON fallbacks (`:1261-1308`).

**The tool suite** (`_define_tools`, `:1035-1092`): retrieval is always on — `insight_forge` (decomposes a query into ≤5 sub-questions), `panorama_search` (full evolution view incl. expired facts), `quick_search`, `interview_agents` (live OASIS interviews, dual-platform, quote extraction). Quantitative tools are gated on `ENABLE_REPORT_PAYLOAD_V1` (default true): `analyze_metrics`, `assess_positions`, `estimate_risks` (probabilities + risk matrix + 2× 10,000-iteration Monte Carlo), `stakeholder_matrix`. Legacy names redirect (`search_graph`→`quick_search`, `get_simulation_context`→`insight_forge`, `:1220-1252`). **Quantitative-first is enforced, not suggested**: a `Final Answer` is rejected unless at least one quant tool was called (`:1679-1685`); role-specific nudges require specific tools; the unused-tools hint warns "your Final Answer will be REJECTED" (`report_agent_prompt_constants.py:412`).

**The ReACT loop's failure discipline.** Each LLM response may contain exactly one tool call or a final answer; a response containing **both** is rejected twice with a format-error message, then on the third offence degraded to truncated execution of the first tool call (`report_agent.py:1609-1643`). Tool calls are parsed from `<tool_call>{json}</tool_call>` with two bare-JSON fallbacks (`:1261-1308`). Observations are injected by the system — never trusted from the model's own text — so the loop can't be derailed by a model narrating a tool call it never made. Section-level enforcement: `min_tool_calls = 3` per section, `max_iterations = 8` per section, `MAX_TOOL_CALLS_PER_SECTION = 5`. For chat mode, the bounds drop to ≤2 tool calls and ≤2 iterations (`:988`).

**Two-generation prompt design:** a plan phase demands **exactly 6 sections with fixed machine roles** (`grounding_and_assumptions`, `quant_snapshot`, `stakeholder_impacts`, `scenarios`, `risks_actions`, `decision_recommendation`); `_validate_outline_roles` checks the exact role set with one repair retry then a default outline. The section phase template is strict: "Quantitative data first — non-negotiable", 3–5 tool calls, "do NOT use your own knowledge", quote agents verbatim as standalone `>` paragraphs, **no markdown headings inside sections** (bold instead). The structured payload is injected as "authoritative tables; do not contradict" (`report_payload.py:472-484`, capped 12,000 chars). **Hybrid generation** (`report_agent.py:2067-2076`): 3 of 6 sections are template-rendered deterministically from the payload; only the three quant sections go through ReACT. Prior sections feed back truncated to 4,000 chars each. Post-generation the system enforces the no-headings rule mechanically, not by trusting the LLM: `_clean_section_content` (headings→bold) and `_post_process_report` (heading whitelist, duplicate removal). Sample output: `docs/reports/pharmacy_first_caps_report_EN.md` = **17,309 bytes** (measured).

**Streaming is journal-polling, not SSE:** `ReportLogger` appends one JSON line per event (`report_start`, `planning_*`, `section_start`, `react_thought`, `tool_call`, `tool_result`, `llm_response`, `section_content`, `section_complete`, `report_complete`, `error`) with `elapsed_seconds`; sections save to disk the moment they complete (`section_01.md`…); `GET /api/report/<id>/agent-log?from_line=N` (`report.py:769-826`) is cursor-based — but `has_more` is always `false`, because the backend re-reads the whole file each poll (`report_agent.py:2500-2506`), making the frontend's 2 s polling O(n²) in log size. (A `console-log` stream at 1.5 s polling mirrors it.) The choice of journal-over-SSE was deliberate: reports take tens of minutes, and a pollable JSONL journal is resumable and restart-proof with zero extra infra — no websockets, survives backend restarts. The Step 4 UI (`Step4Report.vue`, 1,723 lines) builds the timeline purely from log events, renders typed tool-result cards with structured displays (`step4ReportToolDisplays.js` — `InsightDisplay` with facts/entities/relations/sub-question tabs, `PanoramaDisplay`, `InterviewDisplay`, `QuickSearchDisplay`), and draws the quant dashboards: verdict colour coding, Monte-Carlo histogram with CI-90/95 bands + mean marker (`:1624-1658`), a 5×5 risk-matrix cell grid scored `likelihood×impact` (`:1660-1671`), scenario ladder, grounding claims/staleness warnings, and consistency warnings (`:1581-1611`). A raw/structured toggle preserves the button's scroll position (`:1163-1183`).

**The quantitative report layer** (what the quant tools compute, all in `quantitative_analysis_service.py`, 1,631 lines): `simulation_metrics` (totals per platform, action-type distribution, engagement rate, content-creation rate, top-5 agents); `stance_analysis` (LLM classification of every agent persona into supportive/opposing/neutral/ambivalent, intensity 1–5, plus up to 30 graph facts); `consensus_metrics` (majority %, agreement ratio, **polarisation index = entropy/max_entropy**, faction count, cross-group alignment, fault lines); `escalation_analysis` (per-round intensity curve, aggression ratio, turning points at ≥50 % round-over-round change, half-vs-half trend with a 1.3× threshold); `probability_assessment` (LLM low/mid/high triplets per outcome through calibration guardrails); `risk_matrix` (likelihood×impact → severity buckets: critical ≥16, high ≥10, moderate ≥5); `stakeholder_impact_matrix` (per-entity-type stance mix, activity index, escalation exposure, voice share); `decision_framework` (Go/No-Go with key drivers, causal chain, sensitivity, flip conditions, monitoring indicators). `estimate_risks` runs `run_monte_carlo_on_estimates` + `run_composite_monte_carlo` (2× 10,000 iterations) and the results land in the payload (`report_payload.py:455-456`). A scenario ladder is generated with `normalize_scenario_probabilities` aligning brackets with MC CIs and flagging non-exhaustive sums, and `cross_validate_estimates` emits `probability_mismatch` warnings (`report_payload.py:28-76, 287-388`).

**Step 5 — interviews end-to-end.** `Step5Interaction.vue` (2,574 lines) → `POST /api/simulation/interview/batch` (`simulation_interview_env_routes.py:127-228`) → `SimulationRunner.interview_agents_batch` (`simulation_runner.py:1492-1548`) → `SimulationIPCClient.send_batch_interview` (`simulation_ipc.py:224-252`) → writes `ipc_commands/<uuid>.json`, polls `ipc_responses/<uuid>.json` at 0.5 s → response dict `{"twitter_0": {...}, "reddit_0": {...}}` (the UI prefers reddit). Every endpoint 400s unless `check_env_alive` passes (route docstrings are explicit: "requires the simulation environment to be in running state (entered wait-for-command mode after completing simulation loop)"). Command types are `interview`, `batch_interview`, `close_env` (`simulation_ipc.py:25-29`). There is also a chat-with-report-agent mode (`POST /api/report/chat`, `report.py:463` — report truncated to 15,000 chars, ≤2 tool calls, ≤2 iterations), and the report agent's own `interview_agents` tool does the same thing internally (LLM selects agents, LLM generates questions, calls `interview_agents_batch` directly, extracts quotes from dual-platform responses, `zep_tools.py:1257-1399`). The whole interview stack shipped inside the initial codebase (`a842307`) and was de-Chinese'd and module-split in `9887031` — the domain is mature rather than recently built, and its history includes a full refactor off of Chinese-language scaffolding.

**Follow-ups, reminders, and the chat loop.** After `report_complete`, Step 4 fetches follow-up suggestions (`/api/report/<id>/followups`, driven by `suggest-followups` at `simulation_interview_env_routes.py:513-587`) and wires email reminders via `simulation_reminders` rows. The chat-with-report-agent mode (`POST /api/report/chat`, `report.py:463-555`) truncates the report to 15,000 chars, caps at ≤2 tool calls and ≤2 iterations (`report_agent.py:2189-2303`), and streams a plain answer — the coherence trade-off is explicit: later turns never see full earlier content. PostHog events fire at each terminal action (`simulation_completed`, `followup_clicked`, `scenario_compared`).

**Report structure — anatomy of the 17 KB sample.** `docs/reports/pharmacy_first_caps_report_EN.md` = 17,309 bytes; the sibling scenario reports weigh 10,710 and 7,195 bytes — the sizes differ because section depth varies with evidence richness, which is the agentic design doing its job. Anatomy: `#` title + `>` one-line summary + `---`, then `##` sections with **bold** sub-heads and standalone `>` agent quotes — exactly the format contract in `prompt_constants.py:251-354`. The "no headings" rule is enforced mechanically, not by trusting the LLM: `_clean_section_content` (headings→bold, duplicate-title stripping, `report_agent.py:2574-2639`) and `_post_process_report` (level-1/2 heading whitelist, duplicate-heading removal, `:2746-2869`) run after every generation. The report's decision section cites the probability triplets, the risk-matrix cells, and the agent quotes it gathered — a reviewer can trace every claim to a tool result in the agent log, which is the trust story of the whole feature.

**The demo's Step-5 gap, precisely:** the tape contains **zero** `/actions`, `/timeline`, `/posts`, `/comments`, `/sections`, `/progress`, `/env-status`, `/interview/batch`, or `/report/chat` entries — even though `docs/demo-mode-plan.md` §2's fixture inventory lists them (the inventory is stale; `/progress` was flagged nonexistent as early as V9-evidence F4). In demo mode, `POST /api/simulation/interview/batch` → `DEMO_NOT_RECORDED` → the Step 5 code throws `res.error` → visible error (`Step5Interaction.vue:769`). The fix the plan specifies — a `DEMO_MODE` branch in `simulation_interview_env_routes.py` serving canned Q&A — does not exist at HEAD (full read, 635 lines), and the e2e demo spec asserts Steps 1–4 only.

**Bundle synthesis** (`bundle.py` + `bundle_synthesis.py` + `bundle_tasks.py`): `/bundle/create` LLM-generates 2–7 scenario prompts; `/bundle/run` dispatches a single Celery task (`run_bundle_task`, `acks_late`, `max_retries=0`, predetermined task id persisted *before* enqueue to dodge an idempotency race, `bundle.py:246-268`); per scenario it prepares → runs → generates a full agentic report; then `build_bundle_synthesis` asks the LLM for `branch_weights`, `canonical_outcomes`, robust-vs-contingent conclusions, early warnings, a decision matrix, and a narrative — with **deterministic math on top**: `normalize_branch_weights` clamps to [0.05, 0.85] and renormalizes; `compute_marginals_and_recalc` applies the law of total variance `E[V|B] + Var(E|B)` and derives 95% CIs. Users can re-weight post-hoc via `PATCH /<bundle_id>/synthesis/weights` (server-side recompute; the UI renders "Model weights"/"Your weights" badges in `BundleSynthesis.vue:5-38`). The orchestration detail that matters: the bundle task runs per-scenario prepare/run/report via `time.sleep(POLL_INTERVAL=10)` busy-polling (`bundle_tasks.py:15, 27-50`) with `MAX_PREPARE_WAIT=1800` / `MAX_RUN_WAIT=7200` — a 2-hour hard ceiling with no per-scenario timeouts beyond the task limits.

#### Architecture rationale & trade-offs

**Why an agentic writer:** reports must be evidence-anchored to simulation artifacts ("All content must come from events and agent statements/actions… Do NOT use your own knowledge", `report_agent_prompt_constants.py:226-230`), quote agents verbatim as prediction evidence, and adapt structure per scenario. Templates cannot do retrieval-grounded quoting or per-scenario structure; the cost is paid as multi-LLM-call sections. **Why journaling+polling:** reports take tens of minutes; a pollable JSONL journal is resumable, restart-proof, and needs zero extra infra. **Why filesystem IPC for interviews:** agents hold live state; a file-based command/response avoids HTTP ports/credentials inside the simulation script and lets either side restart independently.

**Genuine weaknesses (verified):**
1. **3,019-line monolith** violating the repo's own 750-line convention — worse, the logging extraction to `report_agent_logging.py` exists while `report_agent.py` still carries its own divergent copy (lines 61–410) and doesn't import the extracted module: two sources of truth.
2. **Step 5 replay impossibility is real and unresolved in the demo:** the golden tape contains **zero interview and zero chat entries** (programmatic inspection of `tape.json`); in demo mode `POST /api/simulation/interview/batch` → `DEMO_NOT_RECORDED` → visible error (`Step5Interaction.vue:769`). The plan specifies a canned-Q&A `DEMO_MODE` branch (`docs/demo-mode-plan.md:50, 149`) — **not shipped at HEAD** (full read of the routes file, 635 lines); the e2e demo spec asserts Steps 1–4 only.
3. **Bundle synthesis is doubly broken** (both defects from `17fc32a`): (a) `Config.ENABLE_BUNDLE_SYNTHESIS` is referenced in four places but never defined — and `bundle_tasks.py:358` is *outside* the try block, so a completed bundle run raises `AttributeError` and the bundle row **stays `status="running"` forever** (the final `update_bundle` never executes); the per-scenario report generation at `:286` is silently skipped; the weights PATCH 500s. (b) `_payload_estimates` reads `payload["quantitative_analysis"]["risks"]["probability_assessment"]["estimates"]` but the payload stores it under `payload["quant"]["risks"]` — same drift for `decision_verdict` vs `decision.verdict` and `consensus` vs `quant.positions.consensus_metrics` — so `_payload_estimates` always returns `[]` and every `marginal_*` is `None`: the quantitative core is dead even if the flag were fixed. The narrative and branch weights would still render.
4. **Non-durable generation:** a backend restart kills a report mid-flight with no recovery (bundles at least use `acks_late` Celery).
5. **Cost (unmeasured, code-bounded):** 6 sections × up to 8 LLM calls, 3–5 tool calls per section, plus the quant pre-compute (4 tools with their own LLM calls) plus 2× 10k-iteration MC runs per report → order of magnitude **25–50 LLM calls and 20–40 tool calls per report** (est.). No caching beyond a small `_quant_tool_cache`.
6. **Coherence limits:** chat truncation to 15,000 chars and 4,000-char section feed-back means later sections never see full earlier content.

#### Verified metrics

| Quantity | Value | Provenance |
|---|---|---|
| Report generation | **≈ 6.2 min** (golden tape: report start → payload timestamps; V9: 6m12s) | (measured) |
| Sample report | 17,309 bytes, correct format contract (title + `>` summary, bold sub-heads, `>` quotes) | file stat + read (measured) |
| ReACT bounds | 8 iterations / 5 tool calls / ≥3 tools per section; quant tool mandatory | `report_agent.py:982, 1564-1565, 1679-1685` (measured constants) |
| LLM/tool cost per report | 25–50 LLM + 20–40 tool calls | (est., code-bounded) |
| Interview latency | 5–60 s per question (0.5 s poll + in-subprocess LLM) | (est.) |
| Tape coverage | 1,309 entries; **zero** `/actions`, `/timeline`, `/posts`, `/comments`, `/interview/batch`, `/report/chat` entries | tape inspection (measured) |

---

### 3.5 Domain 5 — Frontend Architecture & Demo Mode

#### What it does

Vue 3.5 + vue-router 4.6 + axios + d3 v7 + DOMPurify, all `<script setup>` Composition API — and **no Pinia**: the `store/` directory is two plain `reactive` modules (`auth.js`, `pendingUpload.js`), which is defensible for a 5-step pipeline where each step is an independent screen owning its data and all durable state is server-side.

**Routing & the demo auth trick.** `main.js:10-16` awaits `initAuth()` *before* mounting; `initAuth` (`store/auth.js:11-29`) creates a **synthetic local user** (`{id:'local', email:'local@dev'}`) whenever `lib/supabase.js` returns null (no `VITE_SUPABASE_URL`/`_ANON_KEY`). So a keyless demo build passes the single `beforeEach` guard (which gates the whole pipeline by default, `router/index.js:144-155`) with zero route-meta changes — auth in the demo is an illusion by construction, deliberately, and worth stating in a portfolio narrative.

**State flow between steps:** there is no shared step state. Hand-off is ID-in-URL + server round-trip (Home → `/process/new` via `pendingUpload` localStorage → Step1 POSTs `/api/simulation/create` → `/simulation/:id` → `/simulation/:id/start?maxRounds=N` → POST `/api/report/generate` → `/report/:id` → `/interaction/:reportId`), each view re-deriving project/graph/simulation from the ID (e.g. `ReportView.vue:144-181` chains report→simulation→project→graph). Resumable-by-URL (Dashboard resume links), at the cost of N+1 request chains on every step entry.

**The step components and their real sizes** (the 750-line convention is violated hard — six files exceed 1,200 lines):

| Component | Lines | Role |
|---|---|---|
| `Step1GraphBuild.vue` | 697 | Upload/ontology/graph-build progress, 2 s task polling, graph stats |
| `Step2EnvSetup.vue` | **2,604** | Profile generation progress, realtime profiles/config polling (3 timers), plan gating, entity table |
| `Step3Simulation.vue` | 1,289 | Run control (start/stop), dual-platform status + action detail polling, live action feed, credit modal |
| `Step4Report.vue` | **1,723** | Agent outline → streaming sections, cursor-based agent-log/console-log polling, payload viewer |
| `Step5Interaction.vue` | **2,574** | Chat with report agent, batch agent interviews, survey mode, profile panel |
| `GraphPanel.vue` | 1,423 | D3 force-directed graph + memory snapshot panel |
| `HistoryDatabase.vue` | 1,497 | Home's session/history list + resume |
| `Home.vue` | 1,235 | Intake: prompt, deep-research, file upload, plan limits, bundle analysis |

Concretely, `Step2EnvSetup.vue:634-1030` packs ~400 lines of script (6 polling functions, 3 timers, plan-computed gating) plus ~1,500 lines of CSS — it is three components (profiles, config, plan-gate) fused — and `Step5Interaction.vue` is two products (chat + survey) in one SFC. The practical cost: these files are hard to review, and the demo work had to verify them via e2e rather than reading them (documented in `docs/superpowers/specs/2026-08-08-static-demo-hosting-design.md:245-249`). The D3 graph panel (`GraphPanel.vue`) is the visual centrepiece: force simulation tuned to relation types (`forceManyBody(-400)`, `forceCollide(50)`), zoom 0.1–4, click-vs-drag disambiguation via a movement threshold (`:662-689`), neighbour-highlight selection, and self-loop arcs via path `sweep-flag`.

**Two API clients, deliberately shimmed separately for the demo:** the axios instance (300 s timeout, Bearer interceptor, unwraps `res.data`, rejects on `success === false`, `requestWithRetry` with exponential backoff that **skips all 4xx** — `api/index.js:55-68`) and the `useApi` raw-fetch wrapper used by 8 views. Two clients = two error paths, and the axios interceptor logs 401s rather than redirecting — the weak spot.

**The demo mode is the major engineering effort** (fully documented in `docs/demo-mode-plan.md` and the static-hosting spec). Chosen after an explicit design decision: record one real frontend-driven run server-side, replay it statically in-browser — over live-backend or hybrid approaches (`docs/superpowers/specs/2026-08-08-static-demo-hosting-design.md:23-33`: the Hetzner box was unreachable, the bill lapsed, and only the demo needed to be public).

*Recording* (`backend/app/middleware/demo_recorder.py`, 238 lines, armed by `DEMO_RECORD=1`): an `after_request` hook captures method, **normalised path**, canonical query, status, JSON body, and `t_ms` since run start. **Path normalisation is a cross-language contract** — Python `normalise_path` (`:58-74`) must stay byte-identical to JS `normalisePath` (`frontend/src/demo/tape.js:24-34`), both rewriting UUID/demo/digit segments to `:id`, with shared test cases duplicated verbatim in `test_demo_recorder.py`. **Secret scrubbing is a design requirement**: Bearer tokens, `sk_/pk_/rk_` keys, Stripe `cus_/sub_` IDs → `<REDACTED>`; real UUIDs → stable SHA-256-derived `demo0000-…` UUIDs preserving referential integrity (`:92-141`). Crash-safe flush every 20 entries via tmp + `os.replace`.

*Replay* (`frontend/src/demo/`): `tape.js` loads `/demo/<scenario>/tape.json` (one retry, schema-version gate), indexes by `METHOD normalised-path[?query]`, and resolves against a **virtual clock** `elapsedFor(sessionId, now) = (now − startMs) × DEMO_SPEEDUP` (`tape.js:130-134`). The **clamp rule is load-bearing**: past the end of the tape, return the final snapshot rather than throwing — because `fetchRunStatus` swallows errors and would otherwise spin forever (`spec:215-217`). **Query-aware keys with stripped-key fallback** (`tape.js:71-74, 101-106`) fix the cursor-collapse class of bugs (see Story D4-1). `sessionId.js` mints stateless identities `demo_<b64url(start_ms)>_<scenario>_<nonce>` — two visitors are naturally isolated, a reload resumes mid-run, no server state; `decodeDemoId` validates prefix/format and rejects non-finite timestamps (`:27-43`), and an underscore in a scenario name raises a `TypeError` at encode time because it breaks the delimiter (fixed in `4e92af5`). `adapter.js` provides two transport shims — an **axios adapter replacement** that sits *below* the existing response interceptor (so `res.data` unwrap and `success:false` rejection keep working) and a `fetch` shim — and both **never reject**: they return `{success:false, error:'DEMO_NOT_RECORDED'|'DEMO_TAPE_LOAD_FAILED'}` and dispatch `demo:not-recorded` / `demo:tape-load-failed` window events (`:47-54`). A `PRE_PICKER_PATHS` allowlist suppresses the watchdog for the billing/session/history calls that legitimately fire on Home pre-picker. Reload resilience: `activeScenario` rehydrates from `localStorage['glas_active_session']` so a deep-link mid-run doesn't dead-end into an infinite spinner (`:22-35`). Axios param serialisation: `buildUrl` (`:90-99`) serialises `config.params` into the URL so cursor values survive. `config.js` makes `DEMO_SPEEDUP` **fail-loud**: a malformed `VITE_DEMO_SPEEDUP` throws at build time instead of silently shipping a 45-minute demo; `isDemoMode` is `VITE_DEMO_MODE==='1'` — a statically-replaceable constant, so production builds dead-code-eliminate the whole adapter.

**The recorder's cross-language contract** is the part to talk about in an interview: the Python `normalise_path` (`demo_recorder.py:58-74`) and the JS `normalisePath` (`tape.js:24-34`) both rewrite UUID/demo/digit/opaque-ID segments to `:id`, and the shared test cases are duplicated verbatim in `test_demo_recorder.py` — the docs even record the cross-language regex fixes (Python `\d`/`$` vs JS). `canonical_query` (`:77-89`) sorts and percent-encodes query params; the JS side re-maps `encodeURIComponent` output to Python `quote_plus` semantics (`tape.js:60-64`). The recorder captures method, normalised path, canonical query, status, JSON body, and `t_ms` since run start (monotonic), flushing every 20 entries via tmp + `os.replace` with an atexit tail flush (`:162-175, 208-215`).

*Watchdog UX* (`DemoBanner.vue`): persistent dismissible banner + two **full-screen blocking overlays** (tape-load failure, unrecorded endpoint), each showing the offending path. The deliberate philosophy: a fixture gap must surface loudly, never silently serve a plausible-looking stale answer (`adapter.js:63-68`).

**The golden tape** (`frontend/public/demo/pharmacy-first-caps/tape.json`): 1,309 entries, 3,804,047 bytes, **44 min 37 s** recorded run (`manifest.json` `duration_ms: 2677037`; `(corrected)` — one report said "45:03"). Scenario: Pharmacy First funding caps. **It is a genuine recording — but its simulation slice is empty** (see §4, Story D2-3), and it contains no interview/chat entries at all.

**Tests:** vitest 65/65 across 8 files (adapter, tape, sessionId, DemoScenarioPicker, DemoBanner, router, App, zepFootprint). E2E (Playwright): (1) a **zero-external-origins assertion** — a `page.on('request')` listener collects any request whose origin differs from the base and asserts the set is empty (`e2e/tests/demo.spec.js:8-38`) — the "keyless cannot rot" claim made machine-checkable; (2) a full replay through Step 4 asserting the agent log has **exactly 3 entries** (the cursor-keying regression pin, `:84-90`) and watchdog overlays count 0. The dedicated `demo-e2e` CI job builds with `VITE_DEMO_MODE=1` and **no env vars**, serves `dist/` statically, and gates on `permissions: contents: read` — a build that needs a credential fails by construction. The e2e fixture deliberately lives under `e2e/fixtures/demo/` so the real golden tape can't clobber it.

**What the demo spec asserts, end to end:** test 1 clicks the scenario card and starts the simulation inside the origin-assertion window, then asserts the collected `external` request set is empty; test 2 replays through Step 3 → Step 4, asserting `[data-test="simulation-complete"]:not([disabled])`, watchdog overlays at count 0, exactly 3 agent-log entries, and the report title rendered from the tape. The adapter unit tests cover NOT_RECORDED, tape-load failure, watchdog events, the PRE_PICKER allowlist, and frozen-vs-advancing clocks against a synthetic fixture (`demo/fixtures/synthetic-tape.json`). The CI comment states the design contract: "If this build needs a credential, the demo has stopped being keyless and this job should fail" — and both demo tests pass at shipped defaults in ~13 s.

**Security posture on the frontend.** Every `v-html` sink renders through DOMPurify after a hand-rolled regex markdown renderer: `step4ReportMarkdown.js:105`, `DossierModal.vue:132`, `FeedReportView.vue:189` — and even though the custom renderer (~100 lines of regex) is the weakest link in the chain, DOMPurify sits *after* it, so injection is mitigated even if the regex mangles HTML. The one residual gap is `FeedReportView.vue:26`, which renders feed `bodyHtml` unsanitised (relies on the backend source being trustworthy). No keys exist in `src/`; Supabase/PostHog are env-gated no-ops; `.env` is untracked; the demo adapter surfaces any unmocked call as a visible watchdog rather than a silent fake. Failure handling is tiered: `FeedView.vue:166-213` falls back to hardcoded demo data so the page never dies; `requestWithRetry` protects the expensive write endpoints; several step views degrade to a log line with no retry UI, and the axios interceptor has no 401→redirect — the weak spots worth stating.

**PostHog events** (opt-in, no-op without `VITE_POSTHOG_KEY`): `simulation_started`, `upgrade_prompt_shown`, `simulation_completed`, `scenario_compared`, `bundle_created`, `followup_clicked` — with autocapture off; notably `identifyUser` is exported but unused, so events are anonymous.

**What a `VITE_DEMO_MODE=1` build actually does at HEAD** (trace it end-to-end): Home mounts with zero demo references → `apiGet('/billing/status')` → `demoFetch` → NOT_RECORDED → `userPlan` null → `isPaidUser` false → clicking "Start Engine" opens the **upgrade modal** (`Home.vue:592-597`) and dead-ends. Even if a user forced through, the axios-based step components would bypass the tape entirely and hit the vite dev proxy. The `demo-e2e` CI job, which builds from the repo checkout, fails at the first click. The gitignored `frontend/dist/` bundle (built 21:54 on 2026-08-14, before `dcbe875`) contains `scenario-card` (picker mounted), `watchdog-not-recorded` (banner mounted), and the adapter's `PRE_PICKER_PATHS` strings — i.e. the wiring existed in a working tree that was never committed, and the golden tape's commit message ("Replay-verified: full click-through with zero watchdog overlays") is true for that *local patched build*, not for the committed source.

#### Architecture rationale & trade-offs

**Why the adapter pattern:** the zero-external-origins constraint forces *transport-level* interception rather than per-method stubbing — it covers both call forms, keeps the response interceptor working, and a missing fixture cannot fall through to the dev proxy. **Why stateless sessions:** the demo must run on static hosting with no backend; time-derived progress needs no server state and survives reloads. **Why giant SFCs:** historical accretion — six files exceed 1,200 lines (two exceed 2,500: `Step2EnvSetup.vue` 2,604, `Step5Interaction.vue` 2,574), violating the repo's own 750-line convention; Step2 is three components fused (profiles, config, plan-gate) and Step5 is two products (chat + survey) in one file.

**Genuine weaknesses (verified):**
1. **⚠️ The demo's frontend glue is NOT in the committed tree.** `demoAdapter` is exported and unit-tested, but **nothing sets it on the axios service**; `setActiveScenario` is never called by any view; `DemoScenarioPicker` and `DemoBanner` are imported by nothing (grep: only their own tests); `Home.vue` contains zero demo references. At HEAD a `VITE_DEMO_MODE=1` build routes Home → `/billing/status` → NOT_RECORDED → `isPaidUser` false → **"Start Engine" opens the upgrade modal and dead-ends** (`Home.vue:592-597`); the axios-based step components bypass the tape entirely; the demo-e2e CI job would fail at the first click. Evidence it worked once: the gitignored `frontend/dist/` bundle (built 21:54 on 2026-08-14) *contains* the picker, the watchdog, and the adapter's `PRE_PICKER_PATHS` strings — the wiring existed in a working tree that was never committed. Commit `c20ee8d` ("add scenario picker, banner, watchdog…") only adds the components + tests, not the mounts.
2. **The golden run was recorded against uncommitted local patches** — the backend twin of #1: since `create_app()` has not booted from a fresh checkout since 2026-04-18 (see §3.7), the recording must have used a locally patched tree. **The demo as committed cannot build or boot.** Estimated repair: ≈50 lines (adapter swap in `api/index.js` + picker/banner mounts behind `isDemoMode`), exactly what `c20ee8d`/`a59d41b` intended.
3. **Dead code:** `views/Process.vue` (1,986 lines — the router imports `MainView.vue` *under the name* `Process`, `router/index.js:4`), `composables/useAdaptiveStepPolling.js` (never imported — **real polling is hardcoded `setInterval`** in each component: Step2 2s/3s/2s, Step3 2s/3s, MainView 2s/10s; the "polling is centralised" design claim in the plan is false `(corrected)`), `config/zepFootprint.js` (consumed only by the dead composable), plus components `DossierModal`, `ResearchSettingsModal`, `BundleProgress` — ~2,800 lines of committed-but-unreachable frontend.
4. **The 5-step illusion, mapped to reality.** The header shows "Step X/5" but the implementation is 4 routes + a legacy container: `MainView.vue` (imported as `Process` by the router) renders only Step 1 and Step 2, then routes away — Steps 3–5 live in `SimulationRunView.vue` / `ReportView.vue` / `InteractionView.vue` (`router/index.js:4, 21-137`). The blank-panel trap exists because `handleNextStep` increments `currentStep` to 5 while the template only mounts 1–2 (`MainView.vue:52-71, 159-169`); today unreachable only by accident of routing order. The plan documents this honestly (`demo-mode-plan.md:11-20, 53`) — the code doesn't.
5. `DEMO_SPEEDUP` defaults to 1 at HEAD — the golden tape would take 44:37 wall-clock; the plan targets ~90 s via ~30×.
6. `DashboardView.vue:326` writes real session IDs to the same localStorage key the demo uses — harmless today (decode rejects non-`demo_` ids) but a latent collision.

**Strengths worth leading with:** the cross-language recorder/replayer contract with mirrored test cases; the fail-loud watchdog philosophy; the clamp rule with its documented "why"; the zero-origin e2e assertion; stateless session-ID design; retry classification (no 4xx, no `insufficient_quota`); DOMPurify-sanitised rendering at every `v-html` sink (`step4ReportMarkdown.js:105`, `DossierModal.vue:132`, `FeedReportView.vue:189`) — with one residual gap: `FeedReportView.vue:26` renders feed `bodyHtml` unsanitised (relies on the backend source being trustworthy).

#### Verified metrics

| Quantity | Value | Provenance |
|---|---|---|
| Frontend unit tests | **65/65** across 8 files | live `npm run test` (measured) |
| Golden tape | 1,309 entries · 3,804,047 bytes · 44 m 37 s | `manifest.json` + file stat (measured) |
| Demo traverse target | ~90 s at ~30× speedup (default is 1× at HEAD) | `demo-mode-plan.md:78` |
| Dead frontend code | ~2,800 lines (Process.vue 1,986 + composable + 3 components) | grep-verified |
| Step component sizes | Step2EnvSetup 2,604 · Step5Interaction 2,574 · Step4Report 1,723 · GraphPanel 1,423 · HistoryDatabase 1,497 · Home 1,235 | file stats (measured) |
| Fix size for demo glue | ≈50 lines (est.) | `(est.)` |

### 3.6 Domain 6 — Infrastructure, CI/CD, Deployment & Observability

#### What it does

Three GitHub Actions workflows: `ci.yml` (8 jobs), `demo-e2e.yml` (1 job), `docker-image.yml` (1 job).

The 8 CI jobs (pinned: Python 3.11, Node 20, concurrency-cancelled per ref):

| Job | What it checks | Gate strength at HEAD |
|---|---|---|
| `lint-backend` | ruff check + format, mypy | Ruff blocking; **mypy `continue-on-error: true`** (`ci.yml:44`) — type errors cannot fail CI |
| `lint-frontend` | ESLint | Blocking |
| `test-backend` | `pytest tests/ --cov=app` + XML artifact (`if: always()`) | **RED**: 17 failed / 152 passed / 24 errors, 22% coverage (measured) |
| `test-frontend` | vitest | Green: 65/65 (measured) |
| `integration-tests` | `pytest tests/integration/` | **RED**: 9 errors — the app cannot boot (`create_app()` AttributeError) |
| `security-scan` | pip-audit `--strict`, npm audit `--audit-level=high`, gitleaks (history scan), semgrep | **All four `continue-on-error: true`** (`ci.yml:173, 177, 183, 189`) — advisory-only, can never turn the build red |
| `build-and-e2e` | docker build (dev image, GHA cache), `docker-compose.ci.yml` up, health-check loop 30 × 2 s, Playwright (8 tests / 5 specs) | **RED**: container backend crashes at import; health check never passes |
| `docker-scan` | `Dockerfile.prod` build (with **placeholder** Supabase args), trivy CRITICAL/HIGH | **`exit-code: 0`** (`ci.yml:308`) — findings cannot fail the build |

The e2e strategy: `docker-compose.ci.yml` brings up the dev image + `redis:7-alpine` — the only external service CI needs; the backend runs in its anonymous keyless fallback mode, "which is exactly the mode demo hosting relies on". Two Playwright configs are required because `testIgnore` wins over explicit paths (`playwright.config.js:5-10`). 10 Playwright tests exist across 5 specs (`auth.spec.js` 3, `demo.spec.js` 2, `health.spec.js` 2, `landing.spec.js` 2, `zep-footprint.spec.js` 1); the backend job runs 8 (demo excluded via `testIgnore`), the demo job runs 2. The `zep-footprint` spec is honest about its own limits (real request-count/HAR assertions need an authenticated live deploy, `zep-footprint.spec.js:3-6`).

**Testing strategy — measured, not estimated:**

- Backend: **17 failed / 152 passed / 24 errors**, 193 collected, **22% coverage** (live `pytest tests/ --cov=app`). Two independent root causes, both import-time-proven: (A) `create_app()` cannot boot — `billing.py:24-25` reads missing `Config.STRIPE_PRICE_RESEARCH_1/5`; consequences: 9/9 integration errors, the `test_auth`/`test_graph_snapshot_cache`/`test_session_research` errors, the dockerized backend's CI health-check failure, and a crash-looping gunicorn; (B) the research-config attributes (`SEARCH_RESEARCH_ENABLED`, `SEARCH_RESEARCH_MODEL`, `TAVILY_API_KEY`, `SEARCH_RESEARCH_MAX_ROUNDS`, `SEARCH_RESEARCH_QUALITY_THRESHOLD`) were never defined — `git log -S SEARCH_RESEARCH_ENABLED` returns nothing; the tests that pin them fail deterministically.
- Frontend: **65/65** across 8 files (vitest 3.2.1, jsdom) — demo tape/adapter/sessionId, zepFootprint config, DemoBanner, DemoScenarioPicker, App, router. (Commit `6414ffd` claimed "49 passing"; the demo work added 16.)
- Coverage: no gate, no badge, no frontend coverage reporter — the XML artifact exists for download only.

**The deploy-era narrative** (all in git history): the Hetzner pipeline went through six distinct failure classes before dying — workflow-parse failure (secrets in step-level `if`), silently-stale images, unbound health-check ports, disk-full silent pull fallback, missing venv pip, and a multi-GB image bloated by CUDA torch. Each was fixed with a targeted commit (`3459e0c`, `8fcd241`, `0234f32`, `7a062af`, `3f1ce27`, `e05d807`, `bd0e94f`), then the box died and the whole rig was retired in favour of a static Cloudflare Pages build — a classic "the operational complexity was the liability" arc, and one of the best interview stories in the repo (§4, D6-1/D6-2).

| Date / commit | Event | Lesson |
|---|---|---|
| 2026-04 · `9a464d4` | Original `deploy.yml` (285 lines): build → migrate → staging → prod, auto-rollback | The ambitious baseline |
| `3459e0c` | Step-level `if: ${{ secrets.X != '' }}` broke the workflow parse; rewritten as a runtime check + `continue-on-error` | "You can't gate on what you don't have" — became a silent skip |
| `3f1ce27` | Health check moved to `docker exec` — port 5001 was never host-bound | "Your health check must observe the actual thing" |
| `8fcd241` / `0234f32` | compose/nginx synced from git; image digest logged — the server was running a stale image | Config drift beats deploy pipelines |
| `7a062af` | Free disk before pull — disk-full pulls silently fell back to cached old images | Silent fallbacks are the worst failures |
| `bd0e94f` | CPU-only torch cut ~5.5 GB from the image | Know your dependency graph |
| `6414ffd` (2026-08-10) | **Retirement** — 477 lines deleted; Cloudflare Pages static build with `permissions: contents: read` | Replace fragile gates with impossible-to-violate constraints |
| `5e775f3` | Dangling Makefile/README references cleaned | Post-retirement hygiene |

**The demo-e2e job** is the retirement's engineering payoff: `permissions: contents: read` (cannot access secrets), fixtures staged from `e2e/fixtures/demo/` so the real golden tape can't clobber them, `VITE_DEMO_MODE=1` with **no speedup overrides** — "the bundle is byte-for-byte the shipped Cloudflare Pages artifact" (comment, `demo-e2e.yml:33-37`, both tests pass at shipped defaults in ~13 s) — served by `serve -s dist -l 4173` behind a curl wait-loop (with an honest comment: without it, "connection refused" errors masquerade as test failures), then `playwright.demo.config.js` runs only the demo spec. The origin assertion derives `ownOrigin` from the Playwright `baseURL` fixture rather than `process.env` (with an explanatory comment about why they diverge, `demo.spec.js:16`).

**Deployment history — the part with the most interview material.** The Hetzner era (`deploy.yml`, 285 lines, deleted in `6414ffd`): build-and-push (GHCR) → Supabase migrations → staging → prod with a `docker exec`-based health check (port 5001 is not host-bound — fixed in `3f1ce27`), auto-rollback via `/opt/glas/.rollback-image`, and a string of hard-won operational fixes preserved in history: the server ran a **stale image** because compose/nginx were never synced from git (`8fcd241`, `0234f32`); explicit removal of stale containers (`da1ae2b`); free-disk-before-pull because disk-full pulls silently fell back to cached old images (`7a062af`); pre-built GHCR images instead of on-server builds (`dcb5e8e`); CPU-only torch cutting ~5.5 GB (`bd0e94f`); `uv pip` instead of a missing `.venv/bin/pip` (`e05d807`). The secrets-gate saga: a step-level `if: ${{ secrets.X != '' }}` is **illegal in GitHub Actions** and broke the workflow parse (`3459e0c` rewrote it as a runtime check + `continue-on-error` — which became a *silent skip* since the secrets were never configured); staging gates were tightened (`24d2714`) then relaxed (`fb1ac42`). **Retirement** (`6414ffd`, 2026-08-10), commit message verbatim: *"The Hetzner box infrastructure is no longer available and never worked anyway (secrets were not transferred to the new repo). Cloudflare Pages builds the static frontend directly from git with no workflow/secret requirements, which is why it was chosen."* The spec adds: "The deploy target (the Hetzner box) is unreachable and the bill has lapsed." Post-retirement, `Dockerfile.prod` remains (54 lines) — the deployment story's appendix: a two-stage build, `node:20-slim` compiling the SPA with **10 VITE build-arg knobs** (Supabase URL/key + 8 Zep polling timings, `Dockerfile.prod:7-28`), `python:3.11-slim` installing backend deps with **CPU-only torch** (the −5.5 GB fix, `:44`), and a runtime serving `frontend/dist` via nginx plus `gunicorn -w 1 --threads 4 --timeout 600`. nginx.conf: SPA fallback, immutable `/assets/`, 60 s proxy timeouts, 50 MB upload cap, and a staging server block with `X-Robots-Tag: noindex`. Weaknesses as committed: a single gunicorn worker; the staging vhost has no live host; the 8 Zep poll args are hand-duplicated in the Dockerfile (drift-prone); and the `docker-scan` CI job builds this image with **placeholder** Supabase args — so the scanned artifact is the placeholder-key build, not a keyed production build (nothing is deployed from it today anyway).

**Observability** (all Compose-managed, provisioned from git): Prometheus 3.4.0, Grafana 11.6.0 (sign-up disabled, provisioned datasources + two dashboards — Application: request rate, p50/p95 latency, error rate; Infrastructure: host/container CPU/mem/disk/network), Loki 3.5.0 + promtail (structured JSON log scraping), node-exporter, cadvisor, redis-exporter, uptime-kuma. App instrumentation is opt-in and clean: `/api/metrics` via `prometheus-flask-instrumentator` only when `ENABLE_PROMETHEUS` is set; Sentry only when `SENTRY_DSN` is set; both fail silently on ImportError (`backend/app/__init__.py:17-47`).

| Component | Version / role | Notes |
|---|---|---|
| Prometheus | 3.4.0; jobs: `flask` (`/api/metrics`, 15 s), node-exporter, cadvisor, redis, prometheus | joins the app network to scrape `glas-intelligence:5001` |
| Grafana | 11.6.0; provisioned datasources (Prometheus + Loki) + 2 dashboards from git | sign-up disabled, `GF_SERVER_ROOT_URL=https://monitor.glasinsight.com` |
| Loki + promtail | 3.5.0; docker.sock container-log scraping, JSON level/timestamp relabeling, 30 d retention | |
| Exporters | node-exporter, cadvisor, redis-exporter (`REDIS_ADDR=redis://glas-redis:6379`) | redis-exporter depends on a container from *another* compose file |
| uptime-kuma | manual checks (no config-as-code — checks live in a volume) | |

**Alert rules** (README-matching): Critical — `AppDown` (`up{job="flask"}==0` for 1 m), `HighDiskUsage` (<10% free for 5 m), `ContainerOOMKill` (increase > 0); Warning — `HighCPU` (>80% for 5 m), `RedisHighMemory` (>0.8), `HighErrorRate` (5xx share > 5%), `HighResponseLatency` (p95 > 5 s); Info — `CertExpiringSoon` (<14 d). Two rules are decorative: `CertExpiringSoon` reads `probe_ssl_earliest_cert_expiry`, a blackbox-exporter metric, and **no blackbox exporter exists anywhere in the stack**; and there are **no alert contact points** — alerts exist as Prometheus rules only, nobody is paged.

**Security posture:** `.gitignore` excludes all `.env*`; `.env.example` documents 43 entries; gitleaks in pre-commit and CI (non-blocking in CI, working-tree-only in pre-commit — already-committed secrets would slip through both). Auth middleware (`middleware/auth.py`): HS256 via shared secret or JWKS fetch for asymmetric algs, `audience="authenticated"` enforced; with keys unset, every request becomes `ANONYMOUS_USER_ID` (`:39-42`) — the documented keyless path, but mode-inference-by-config-presence (an accidental missing `SUPABASE_JWT_SECRET` silently opens every `require_auth` route; `Config.validate()` doesn't flag it). RLS: only migration 002 contains policies; the app DB is largely RLS-light (see §3.7). The zero-external-origins constraint is enforced two ways: the demo-e2e job's `permissions: contents: read` (a credential-needing build must fail) and the Playwright origin assertion.

#### Architecture rationale & trade-offs

**Why Docker Compose everywhere:** the stack (Flask + Celery/Redis + camel-ai/OASIS with ~10 GB PyTorch deps + Vue) is heavy and multi-process; one command gives parity between local and CI. **Why static hosting replaced Hetzner:** dead box + lapsed bill + secrets never transferred — and, architecturally, a static demo is a pure function of committed JSON: "It cannot break because a vendor changed pricing eight months after you last touched it" (`docs/demo-mode-plan.md:72`). That's the strongest single line in the portfolio. **Why 8 CI jobs:** separation by toolchain/layer with a sensible `needs:` DAG — the weakness is that 3 of 8 are red and 4 security steps can't fail. **Why the OSS observability stack:** coherent, zero-licensing, Compose-managed.

**Genuine weaknesses (verified):**
1. **CI red at three levels** for one root cause: `app/api/billing.py:24-25` reads `Config.STRIPE_PRICE_RESEARCH_1/5` at import time; neither exists. The app has not booted from a fresh checkout since **2026-04-18** (`17fc32a`; `(corrected)` — one report said "May 2026").
2. **All five security gates + mypy are non-blocking** — the pipeline reports vulnerabilities but never blocks on them. Defensible framing: advisory-first scanning kept the build green through heavy dependency churn; the trade-off is a human must read the reports.
3. **No staging environment anymore** (deleted with the pipeline); `nginx.conf` still carries a staging vhost with no host behind it; the README still describes CD/auto-rollback and references deleted files.
4. **Coverage:** 22% backend (measured), no frontend coverage reporter, no threshold gate.
5. **`config.py:24` hardcodes a fallback `SECRET_KEY = 'glas-intelligence-secret-key'`** — a missing `.env` in production would run on a publicly-known signing key.
6. **Observability gaps:** no alert contact points (alerts exist as rules only; nobody is paged); `CertExpiringSoon` can never fire (it reads `probe_ssl_earliest_cert_expiry`, a blackbox-exporter metric, and **no blackbox exporter exists anywhere in the stack**); redis-exporter points at a container defined only in another compose file; the whole stack is orphaned by the retirement — fine as portfolio evidence, not live.
7. **Residual XSS gap:** `FeedReportView.vue:26` renders `report.bodyHtml` via unsanitised `v-html` (all other sinks are DOMPurify'd).

#### Verified metrics

> **Status note (2026-08-16):** the rows below were measured on 2026-08-14 and describe the pre-repair state. Current: backend **257/257**, frontend **65/65**, demo e2e **2/2**, `create_app()` boots. See §5 for the full before/after ledger.

| Quantity | Value (measured 2026-08-14, pre-repair) | Provenance |
|---|---|---|
| Backend suite | 17 failed · 152 passed · 24 errors · 22% coverage (193 collected) | live `pytest tests/ --cov=app` (measured) |
| Frontend suite | 65/65 | live vitest (measured) |
| e2e | 10 tests / 5 specs (8 backend + 2 demo) | configs (measured) |
| Boot failure | `AttributeError: type object 'Config' has no attribute 'STRIPE_PRICE_RESEARCH_1'` at `billing.py:24` | executed `create_app()` (measured) |
| Config drift | `hasattr(Config, 'TAVILY_API_KEY')` → False; same for all `SEARCH_RESEARCH_*`, `GRAPH_SNAPSHOT_*` | executed introspection (measured) |
| Non-blocking gates | mypy 1 + security 4 + trivy 1 = 6 gates that cannot fail CI | `ci.yml` read (verified) |
| Image size | CPU-only torch cut ~5.5 GB | commit `bd0e94f` |

---

### 3.7 Domain 7 — Data Layer, Auth, Billing & Scaling

#### What it does

**Auth flow:** Supabase JS client → session + `onAuthStateChange` into a reactive store → axios Bearer interceptor → Flask `before_request` (`extract_user_from_request`, `middleware/auth.py:35-57`) decodes the JWT and sets `g.user_id`; `require_auth` 401s, `optional_auth` passes. The JWT decoder is dual-path: HS256 symmetric decode with `SUPABASE_JWT_SECRET` (dev/test), or `PyJWKClient` fetch from `{SUPABASE_URL}/auth/v1/.well-known/jwks.json` for asymmetric algs as Supabase rotates keys — audience `authenticated` enforced on both paths. Sound and conventional.

The full chain, end to end: (1) `frontend/src/lib/supabase.js:3-8` — client is `null` if either key is empty (the demo path); (2) `store/auth.js:11-29` — `initAuth()` calls `getSession()` and keeps the reactive store fresh via `onAuthStateChange`; (3) `api/index.js:12-22` — request interceptor injects `Authorization: Bearer <token>`; (4) `router/index.js:144-155` — the guard redirects unauthenticated users to Login (or Landing on `/`), `meta.public` routes bypass; (5) server-side — `extract_user_from_request` runs as `before_request` (registered at `app/__init__.py:75-76`) and sets `g.user_id`/`g.user_email`; `require_auth` 401s when falsy. The anonymous path (`auth.py:39-42, 65-68`): with `SUPABASE_URL`/`SUPABASE_JWT_SECRET` unset, every request becomes `user_id="anonymous"` and `require_auth` passes — the documented keyless-demo affordance, but **mode-inference-by-config-presence**: a deployment that accidentally omits `SUPABASE_JWT_SECRET` (while setting the URL) silently runs every gated route open as anonymous, and `Config.validate()` (`config.py:127-136`) does not flag it. Note also that `profiles.id` is a `uuid` (`schema.sql:27`), so the anonymous path can never persist — `get_or_create_profile` with `id="anonymous"` would be rejected by Postgres; the path's real job is keeping the backend bootable keyless and letting feed endpoints serve the free plan (`feed.py:39-41`).

**Data model** (Supabase Postgres; migrations 002–009; consolidated `docs/schema/supabase_schema.sql`, 327 lines): `profiles` (plan check `free/payg/pro/business/enterprise`, two credit meters, `stripe_customer_id`) → `projects` (`graph_id` holds the Zep graph id) → `simulations` → `reports`; plus `credit_transactions` (audit ledger with type CHECK), `decision_bundles` (`synthesis` JSONB), `simulation_reminders`, and `scenario_sessions` — the central session table, deliberately denormalized with `graph_id` and `project_id` "for recovery" (migrations 008/009) because the canonical `projects` row or local disk state can go missing; `propagate_graph_id_for_project()` (`supabase_client.py:402-416`) back-fills. Feed tables (`feed_simulations`/`feed_views`) support the public insights feed with 3 free views/month via a month-scoped upsert count.

| Table | Key | Relationships | Notes |
|---|---|---|---|
| `profiles` | `id uuid → auth.users` (CASCADE) | parent of all | plan check, `credits`, `research_credits`, `stripe_customer_id` |
| `projects` | `id text` | `user_id → profiles` | `graph_id` = Zep graph id |
| `simulations` | `id text` | `project_id → projects`, `user_id → profiles` | |
| `reports` | `id text` | `simulation_id → simulations`, `user_id → profiles` | |
| `credit_transactions` | `uuid` | `user_id → profiles` | ledger; type CHECK incl. research types |
| `decision_bundles` | `uuid` | `user_id → auth.users` | `synthesis` JSONB from 007 |
| `scenario_sessions` | `uuid` | `user_id` (no FK), **denormalized** `graph_id`/`project_id` | session state machine |
| `feed_simulations` / `feed_views` | `uuid` | industry refs, sim/report refs | public content + view metering |

**Migration history — and the drift that was fixed:**

| Migration | Content | Status |
|---|---|---|
| 004 | `scenario_sessions` + partial index `idx_sessions_user_active` | ✅ matches consolidated schema `schema.sql:145-181` |
| 005 | `research_credits` col + `deduct_research_credit_atomic` + `refund_research_credit` + backfill | ✅ RPC bodies byte-identical (`schema.sql:278-327`) |
| 006 | credit_transactions CHECK widened to `research_usage`/`research_refund` | ✅ |
| 007 | `decision_bundles.synthesis` JSONB | ✅ |
| 008 | `scenario_sessions.graph_id` + partial index `idx_scenario_sessions_project_graph` | ✅ — **but indexed `project_id` before the column existed** |
| 009 | `scenario_sessions.project_id` | ✅ — "Migration 008 created an index on this column but never added it — this is the fix" |

The consolidated schema is now an accurate single-source reference for migrations 002–009, with one intentional delta (005's paid-user backfill commented out with an explanatory note, correct for fresh installs). JSON columns are round-tripped through `json.dumps` with defensive `_parse_*_json_fields` fallbacks (`supabase_client.py:253-278, 456-476`).

**The schema-drift fix is real and verified:** migrations 004–009 match the consolidated schema **line-by-line** — identical columns/constraints, RPC bodies byte-identical (spot-checked), one intentional delta (005's paid-user backfill commented out with an explanatory note for fresh installs). The drift symptom is preserved in history: **migration 008 created an index on `project_id` before the column existed** — 009's header literally reads "Migration 008 created an index on this column but never added it — this is the fix" (008 in `17fc32a`, 2026-04-18; 009 in `a37f2d3`, 2026-05-17, a month apart).

**Billing (Stripe):** `POST /api/billing/checkout` (Checkout Sessions; `mode=subscription` for pro/business, `mode=payment` for packs/research/overage; customer reuse via `stripe_customer_id`); Customer Portal; webhook signature-verified (`checkout.session.completed`, `invoice.paid`, `customer.subscription.deleted`) — **the webhook is the only grant path, so credits can't be forged client-side**. Grants per plan map (subscriptions grant 10/40 sim credits + 3/13/33 research credits; packs grant quantity + research bonus 5→2, 10→5; PAYG 1+1); monthly top-up via `invoice.paid`; free tier = 1 free simulation/month counted from `credit_transactions`. Pre-flight gates `/can-simulate`, `/can-research`, `/status`.

**The atomic credit system** is the cleanest data-layer work: `deduct_credit_atomic` (migration 003) is a single `UPDATE profiles SET credits = credits - 1 WHERE id = $1 AND credits >= 1 RETURNING credits` plus a ledger insert, all inside a SECURITY DEFINER function — **race-safe by construction**; `deduct_research_credit_atomic` and `refund_research_credit` (migration 005) mirror it. Python callers (`supabase_client.py:149-244`) have guarded fallbacks (`.gte("credits", 1)`) for migration lag. The research credit lifecycle is end-to-end disciplined: atomic claim (conditional UPDATE) → deduct (skipped on free retries) → enqueue with plan priority (enterprise 9 / pro 5 / free 1) → Celery task writes state directly to Supabase → refund **exactly once** on failure (task-level, `research_tasks.py:93-95`; caller-level on queue failure, `session.py:292-303`; stale-timeout-level at 50 min; empty-dossier-guard-level). The "refunded exactly once" comment at `session.py:19-21` exists because of a real double-refund incident.

**The full research-credit walkthrough** (`session.py` ~200–300 + `research_tasks.py`):

1. **Claim** — conditional UPDATE (`research_status = 'claiming'` WHERE status NULL/expected) → 409 if not claimed; the optimistic lock prevents double-start.
2. **Deduct** — `deduct_research_credit` unless this is a retry → 402 if no credits.
3. **Enqueue** — Celery `glas.deep_research` on the `research` queue with plan-based priority (9/5/1).
4. **Execute** — the task writes state **directly to Supabase** (survives worker restarts), refunds exactly once on failure (`research_tasks.py:93-95`, skipped for retries).
5. **Queue-failure path** — the caller refunds (`session.py:292-303`), so a broker outage never costs the user money.

**Stripe integration as designed:** checkout with `mode=subscription` for pro/business and `mode=payment` for packs/research/overage; `client_reference_id` + metadata carry `user_id`; customer reuse via `stripe_customer_id`; webhook (`STRIPE_WEBHOOK_SECRET`-verified via `stripe.Webhook.construct_event`) handles `checkout.session.completed`, `invoice.paid` (monthly top-up to full allowance + ledger rows, `billing.py:235-257`), and `customer.subscription.deleted`; unconfigured → 503, bad signature → 400. The free tier is 1 free simulation/month counted from `credit_transactions` since month start (`billing.py:339-360`, mirrored in `dashboard.py:52-72`); the UI calls `/can-simulate`, `/can-research`, `/status` pre-flight before runs.

**Analytics & scaling reality:** PostHog is frontend-only and anonymous (no `identify`); Sentry and Prometheus are env-gated no-ops without keys. Horizontally scalable: Celery workers (two explicit queues, `acks_late`, `prefetch=1`, priority_steps 0–9) and deep research as a long job writing progress to Supabase. Structurally bounded: simulations as web-container subprocesses (no distributed runner — deliberate v1); the deprecated thread-based research endpoint; the in-memory `TaskManager`; Zep metering with no quota/rate-management layer; **no API-level rate limiting** — abuse resistance rests on auth + credits + plan caps (25 agents free → 200 enterprise as the primary cost lever).

**The feed tiering** (`feed.py`): published-only listings; free users get summary payloads with `report_id`/`simulation_id` stripped (`:129-132`) and **3 views/month** enforced via a `feed_views` upsert-on-conflict keyed `(user_id, feed_simulation_id)` with a month-scoped count (`:47-81`); admins are set via `ADMIN_USER_IDS` env (`:17-18`) mirrored in a DB policy using the `app.admin_ids` GUC (`schema.sql:218`).

**RLS inventory (honest):** `enable row level security` appears on exactly 9 tables in the consolidated schema — `profiles`, `projects`, `simulations`, `reports`, `credit_transactions`, `decision_bundles`, `simulation_reminders`, `feed_simulations`, `feed_views` — and **not** on `scenario_sessions` (the platform's central user-facing table). Since the backend talks to Supabase exclusively via the service key (`supabase_client.py:14-20`), RLS is defense-in-depth only for the API; the gap matters the day the anon key leaks, because that table would expose other users' prompts and dossiers. `profiles` RLS has only SELECT/UPDATE policies — inserts/deletes rely on the `handle_new_user()` SECURITY DEFINER trigger (`schema.sql:43-55`) and service-key paths, which is consistent.

**Scaling reality:** Celery workers scale horizontally (Redis broker; two explicit queues; `acks_late`, `prefetch_multiplier=1`, priority_steps 0–9); deep research is a long Celery job writing progress to Supabase — the web process stays stateless for it. **What doesn't scale:** simulations are subprocesses on one host (no distributed runner — deliberate v1); the legacy thread-based research endpoint (deprecated, `source_agent.py:151-154`); `TaskManager` in-memory dict; no API rate limiting (abuse resistance rests on auth + credits + plan caps).

#### Architecture rationale & trade-offs

**Why Supabase:** one provider for auth (GoTrue JWT), Postgres, RLS, and Storage — the backend talks to it exclusively through the service key via a single thin `SupabaseDB` facade (`supabase_client.py:23-504`): one integration surface, no ORM. **Why RPCs for money:** the check-and-decrement must be atomic under concurrent requests; the database arbitrates, not the app. **Why Stripe:** outsourced payment authority, and the webhook-only grant path means no client-side forgery. **Why two credit meters:** simulations (expensive, plan-capped) and research briefings (token-costed) have different cost curves, SKUs, and refund semantics — research refunds on failure, simulations don't. Defensible economics.

**Genuine weaknesses (verified) — the two that matter:**
1. **⚠️ The backend does not boot.** `billing.py:24-25` reads `Config.STRIPE_PRICE_RESEARCH_1` / `STRIPE_PRICE_RESEARCH_5`, which don't exist (`config.py:41-51` has only PACK_5/PACK_10 etc.). `billing_bp` is imported unconditionally by the app factory (`app/__init__.py:104-105`), so `create_app()` raises `AttributeError` at import time. Introduced in `17fc32a` (2026-04-18, a 188-file stash-restore, +37k/−23k); the frontend `PricingView` only exposes `pack_5`/`pack_10`, so the research products were unreachable in the UI anyway — but the damage is the whole app.
2. **`Config.normalize_plan` is called in 8 files (15 call sites) and defined nowhere.** Committed by `59fc465` (2026-04-11) without the helper. Currently masked by bug 1; removing bug 1 surfaces this one immediately. Even the existing intent fails: `simulation_limits` is case-sensitive (`plan == 'enterprise'`), and the shipped test `test_enterprise_plan_limits_normalizes_casing` fails (`assert 50 == 200`).

**Why CI didn't catch either:** no test exercises `create_app()` — the unit tests import `config.py` in isolation. A one-line app-factory smoke test would have failed instantly.

Other weaknesses: **RLS gap on `scenario_sessions`** — 9 tables have `enable row level security` in the consolidated schema; the platform's central table does not (migration 004 neither). Low exploitability today (anon key not published in the demo build; service key bypasses RLS anyway) — but it's the one table that would expose other users' prompts/dossiers if the anon key leaked. Plus: the RPC fallbacks swallow exceptions (`except Exception` → warn → continue), silently degrading to non-atomic app-side math whose ledger inserts fail pre-migration-006; migrations are applied manually in the Supabase SQL editor with no versioning/rollback; `Config.validate()` doesn't flag missing `SUPABASE_JWT_SECRET`.

#### Verified metrics

| Quantity | Value | Provenance |
|---|---|---|
| Schema consistency | migrations 004–009 ≡ consolidated `supabase_schema.sql` (327 lines), RPCs byte-identical | line-by-line compare (verified) |
| Credit RPC semantics | single `UPDATE … WHERE credits >= 1 RETURNING` + ledger insert, SECURITY DEFINER | migration 003/005 + schema.sql:250-327 (verified) |
| Plan priority | enterprise 9 / pro 5 / free 1 | `session.py:257-259` (measured constants) |
| Research credit grants | 3/13/33 per plan; packs 5→2, 10→5; PAYG 1+1 | `billing.py:163-232` (verified) |
| Stale research window | 50 min (vs 46-min hard kill) | `session.py:22` (verified) |
| `normalize_plan` call sites | 15 across 8 files; 0 definitions | grep (verified) |
| Free tier | 1 sim/month via `credit_transactions` count | `billing.py:339-360` (verified) |

## 4. The Interview Story Bank

Every story below is grounded in the verified findings of Section 3 (commits and file:line evidence are cited in the deep-dives). Estimates are marked `(est.)`. Stories are told in the same 8-beat structure so they can be practiced and told from memory. **Story D2-3 is the honest-failure story** — the empty golden simulation — and it is the one to tell when asked "what would you do differently?".

**The story map** (which story answers which question):

| Question an interviewer might ask | Story |
|---|---|
| "Tell me about a time you fixed something subtle." | D1-1 (stale-research refund race), D7-2 (credit race) |
| "What's your worst bug?" | **D2-3 (the empty golden simulation)** |
| "Why a subprocess?" | D1-3 |
| "Why not just cache the backend?" | D4-3, D5-1 |
| "How do you make a test that can't rot?" | D6-3 |
| "What did you learn from a failed deployment?" | D6-1, D6-2 |
| "What would you do differently?" | D5-3 (uncommitted glue), D7-3 (phantom config) |
| "How do you handle LLM failures?" | D1-2, D3-1, D3-2, D5-2 |
| "How do you keep money operations safe?" | D7-2 |
| "How do you evolve a schema safely?" | D7-1 |

### Domain 1 — Orchestration & Data Flow

**Story D1-1 — "The research run that refunded itself at minute 44"**
1. We had users reporting failed research runs for legitimate 45-minute deep-research jobs — and some runs were being double-refunded.
2. I chose to treat any run still `processing` past a threshold as stale: refund the credit, mark failed, and allow a free retry.
3. We initially tried a 30-minute threshold.
4. It failed because the OpenAI deep-research path genuinely runs 30–45 minutes (`deep_research_agent.py:66-67`), so the poller fired while the task was still alive — the UI showed "failed" for a running job, and then the task's own failure path refunded the credit a second time.
5. I measured the delta between a legit run's wall clock and the hard kill at 46 minutes (`time_limit=2760`) and found 50 minutes was the smallest safe poller threshold.
6. I changed `STALE_RESEARCH_MINUTES` from 30 to 50 and wrote the calibration rationale into the code so nobody "fixes" it back (`session.py:16-22`; commit `921b0d3`).
7. The result was zero false stale-reclaims and exactly-once refunds — a 44-minute run now always finishes clean (verified in the golden tape's report slice at ≈6.2 min).
8. The remaining trade-off was that a genuinely wedged worker costs users up to 50 minutes before they can retry — money-safe but slow.

**Story D1-2 — "The rate-limit graveyard: 520s, TPM buckets, and one permanent error"**
1. We had deep research failing constantly — Cloudflare 520/522/524 edge timeouts on 10–40-minute calls, OpenAI TPM bucket exhaustion, and one error that made every retry pointless.
2. I chose a five-attempt retry loop with exponential backoff (5→90 s), plus a hard 60-second floor for rate limits because OpenAI's TPM window is one minute — retrying sooner guarantees a second miss.
3. We initially tried retrying everything, including `insufficient_quota`.
4. It failed because that error is permanent until credits are added — every retry burned a 5–90 s sleep and the last error raised was misleading.
5. I measured the TPM trap directly: with a large `max_output_tokens`, a single request reserves `input + max_output_tokens` against the per-minute budget at request time, and production logs showed 5 consecutive 429s with "Used 175034 / Limit 200000" (commit `bc8d536` figures).
6. I changed the retry layer to parse the API's own "try again in X ms/s" hint and wait exactly that — clamped to a 60 s floor and 180 s ceiling — and added a one-line fast-fail on `insufficient_quota` (`llm_research_agent.py:168-171`; commits `13646ef`, `bc8d536`, `f6f04eb`).
7. The result was that transient failures self-heal inside the task and permanent ones fail fast and refund through the normal path.
8. The remaining trade-off was that a genuinely hung call now takes ~5 minutes of backoff before failing instead of 30 seconds.

**Story D1-3 — "Why the simulation is a subprocess and the API just tails a log file"**
1. We had an OASIS (camel-ai) simulation that is a foreign body in a Flask app — its own asyncio loop, CSV/JSON/SQLite file formats, multi-minute `env.step()` calls — and after the run we needed the same resident environments alive so users could interview agents.
2. I chose to keep the OASIS scripts as standalone CLI programs and spawn them as a subprocess in its own process group (`subprocess.Popen(..., start_new_session=True)`, `simulation_runner.py:420-452`), with the API exposing progress by tailing the JSONL the scripts already write (`simulation_runner.py:483-517`).
3. We initially tried a real IPC channel (sockets/queues).
4. It failed because the scripts had to keep working standalone — they predate the API (`get_run_instructions` still returns raw shell commands, `simulation_manager.py:517-539`) — and the process had to survive Flask's threaded request model.
5. I measured two real bugs this design forced us to fix: stdout piped to a pipe buffer deadlocked a long run (fixed by redirecting to `simulation.log`, `simulation_runner.py:430-432`), and Windows UTF-8 garble from OASIS's un-encoded file reads (fixed with `PYTHONUTF8` + a `builtins.open` monkeypatch, `run_parallel_simulation.py:35-65`).
6. I changed the boundary from pipes to files everywhere: stdout to log, progress via `actions.jsonl`, interviews via JSON command/response files polled at 0.5 s.
7. The result was a 25-round loop running with only ~14.3 s of non-LLM overhead (measured, `sim_17a78fae63da/simulation.log`) and a progress feed that survives either side crashing.
8. The remaining trade-off was five on-disk state files that must stay coherent — and when the subprocess is gone, interviews are gone too, which is exactly why the static demo must serve canned Step-5 answers.

### Domain 2 — Simulation Engine

**Story D2-1 — "Tool calls were invisible; we built a side-channel logger"**
1. We had agents with tools (web search, scenario actions) making tool calls inside CAMEL's loop that OASIS's `trace` table never recorded — the product's action stream had a blind spot.
2. I chose a thread-safe JSONL side-channel (`ToolCallLogger`) with per-reader byte offsets so the Twitter and Reddit loops consume the same `tool_calls.jsonl` independently (`simulation_tools.py:31-115`).
3. We initially tried waiting for OASIS to persist tool calls.
4. It failed because the library's contract only writes final social actions to `trace`; patching upstream would have forked the dependency.
5. I measured the gap by reading the library source — `trace` is written only on dispatch, never for CAMEL-internal tool calls.
6. I changed the action pipeline to prepend/append side-channel and EffectEngine events around the OASIS-extracted actions, with a `contextvars` wrapper attributing each call to the right agent (`simulation_tools.py:609-634`).
7. The result was that every tool invocation now surfaces as a `TOOL_*` action with agent/platform attribution, and the two platforms never steal each other's entries.
8. The remaining trade-off was a second persistence channel that can drift from the sqlite trace — a documented consistency cost.

**Story D2-2 — "Interviews only work against a live process; the demo would dead-end at Step 5"**
1. We had a product screen that interviews agents — but the endpoint 400s unless the OASIS subprocess is still resident in wait-for-command mode, so a cached or completed run can never answer.
2. I chose to keep the real live-process path (that *is* the product) and, for the demo, serve canned Q&A with suggested-question chips and a visible "recorded response" label (`demo-mode-plan.md:149`).
3. We initially tried naive replay of interview traffic against a cached run.
4. It failed because the agent's memory lives in the subprocess and the answers sit in the per-run sqlite `trace` — both gone when the process exits (`demo-mode-plan.md:50`).
5. I measured the failure mode: every interview endpoint 400s via `check_env_alive`, and a SIGKILLed subprocess leaves a stale "alive" file so the client burns the full 60/120/30 s timeout before erroring (`simulation_ipc.py:121, 228, 254`).
6. I changed the interview design to filesystem IPC — JSON command files polled at 0.5 s — and hardened prompts with a 7-rule plain-text prefix so LLMs answer in persona instead of tool-call format (`simulation_helpers.py:14-20`).
7. The result was a working live-interview path (proven in the V9 dry-run) and a loudly-labeled canned fallback in the demo instead of a silent fake.
8. The remaining trade-off was demo fidelity vs product fidelity — the demo lies about interactivity by design, and it says so on screen.

**Story D2-3 — THE HONEST FAILURE: "The golden demo ran zero actions, and the UI reported success"**
1. We had the golden demo recording — the artifact that was supposed to prove the pipeline end-to-end — and it turned out the simulation stage executed zero actions.
2. I chose to record the demo against a real backend run rather than fabricate fixtures, trusting the run-status polling to reflect what actually happened.
3. We initially tried running the sim against the configured OpenAI endpoint with an `OPENAI_API_KEY` env var.
4. It failed because the key in that slot was actually an **Anthropic key** — every agent LLM call 401'd instantly ("Incorrect API key provided: sk-ant-…" sent to api.openai.com), and the system logged a perfectly normal-looking completion: 25 rounds, both platforms, zero errors surfaced, zero actions.
5. I measured it later by inspecting the tape: `reddit_actions_count: 0`, `total_actions_count: 0`, `all_actions: []`, and the report itself admits "zero logged actions, zero rounds" and "Decision recommendation not available" — while the Step-3 UI had shown complete. The loop overhead was only 14.3 s for all 25 rounds, which should have been the smell test.
6. I changed my verification habits: never trust a run-status flag — check the action stream, check per-agent LLM call results, and validate key/endpoint compatibility at spawn time (this incident was the live proof of the `create_model` `os.environ` mutation hazard, `model_factory.py:55-56`).
7. The result was an honest tape: the demo's centerpiece stage visibly replays an empty simulation, and this document discloses it instead of claiming an end-to-end green run — the empty-sim discovery is a monitoring/verification gap, and that is exactly the lesson a good interviewer wants to hear.
8. The remaining trade-off was that the demo lost its strongest visual moment, and the fix (loud-fail on zero-action runs) ships as a monitoring requirement rather than as shipped code today.

### Domain 3 — Research & Knowledge Graph

**Story D3-1 — "Raising output tokens fixed empty dossiers but blew the TPM budget"**
1. We had deep-research runs returning empty dossiers — the model ran out of output tokens mid-synthesis.
2. I chose to raise `DEEP_RESEARCH_MAX_OUTPUT_TOKENS` from 16k to 100k so long-form dossiers could complete.
3. We initially tried just raising the token cap.
4. It failed because OpenAI charges `input + max_output_tokens` against the per-minute budget *at request time* — one call reserved over half of Tier-1's 200k TPM, and production logs showed 5 consecutive 429s ("Used 175034 / Limit 200000", commit `bc8d536`).
5. I measured the reservation economics directly: a 100k-token ceiling means a single request can block a whole minute of budget before a single token is generated.
6. I changed the retry layer to honour the API's own "try again in X" hint, clamped to a 60 s TPM-window floor and a 180 s ceiling (`deep_research_agent.py:37-38, 121-142`) — faster retries are guaranteed failures.
7. The result was that multi-minute research calls stopped dying to their own reservation — and, honestly, the knob itself later vanished in the `17fc32a` stash-restore, which is the same config-drift class of bug Section 3.3 documents at HEAD.
8. The remaining trade-off was that token reservation is a throughput tax even when the model finishes early — the price of a large ceiling is a permanently fat request.

**Story D3-2 — "A 12-minute research run killed by a Cloudflare 520"**
1. We had a 12-minute deep-research call return `openai.InternalServerError: 520` from Cloudflare in front of api.openai.com — the entire run wasted.
2. I chose to classify transport failures as transient and retry them inside the task.
3. We initially tried retrying only {500, 502, 503}.
4. It failed because Cloudflare edge timeouts (520/522/524) and mid-stream TCP resets on multi-minute calls weren't in the set, so they were treated as fatal.
5. I measured the failure set from production errors and extended the transient set to {500, 502, 503, 504, 520, 522, 524} plus `APIConnectionError`/`APITimeoutError`, with backoffs [5, 10, 30, 60, 90] (`deep_research_agent.py:30-32, 157-170`; commit `13646ef`).
6. I changed the deep-research retry matrix and mirrored it in the fallback agent (`llm_research_agent.py:21-23, 178-190`).
7. The result was that the 12-minute class of runs stopped being lost to edge failures — retries happen inside the task, comfortably before the 46-minute hard kill.
8. The remaining trade-off was worst-case added latency: a genuinely dead endpoint now costs up to ~5 minutes of backoff before failing.

**Story D3-3 — "The 409 lockout: 'completed' with nothing inside"**
1. We had sessions ending up `research_status='completed'` with an empty dossier — and the Retry button returned 409 "Research already completed" because the gate only checked the status flag, not the content.
2. I chose a content-aware gate: `has_real_content` checks `summary_md`, and completed-but-empty is treated as a free retry that wipes the stale dossier (`session.py:194-208`; commit `ea0a3a6`).
3. We initially tried preventing new sessions from reaching completed-empty.
4. It failed because legacy rows were already stuck and the gate fix didn't unstick them — the visible symptom stayed visible.
5. I measured the blind spot by tracing the retry path: the status check passed, and no content check existed.
6. I changed the state machine's entry checks and added a guard in the Celery task that raises `RuntimeError` on empty `summary_md` so failure is visible and refundable (`research_tasks.py:69-74`).
7. The result was that every empty-dossier session became retryable at zero credit cost, and "successful but empty" no longer sits silently in the dashboard.
8. The remaining trade-off was that a free retry still re-runs an expensive stage — the guard reduced, but didn't eliminate, wasted LLM spend.

### Domain 4 — Report & Interaction Layer

**Story D4-1 — "The report froze on the first snapshot: cursor collapse in demo replay"**
1. We had the demo's Step-4 report timeline freezing at the first snapshot — every poll rendered the same data.
2. I chose query-aware tape keys with a stripped-key fallback so cursor-carrying endpoints index correctly (`tape.js:71-74, 101-106`).
3. We initially tried keying the tape on the stripped path only.
4. It failed because `GET /api/report/:id/agent-log?from_line=N` is polled with incrementing cursors, so every poll resolved to the `from_line=0` snapshot and the report streamed duplicated garbage.
5. I measured the bug by replaying the tape and watching every poll return the same entry.
6. I changed the recorder and replayer together: Python's `canonical_query` sorts and percent-encodes query params (`demo_recorder.py:77-89`), the JS side mirrors `quote_plus` semantics exactly (`tape.js:60-64`), and the axios adapter serialises `config.params` into the URL so cursors survive (`adapter.js:86-99`).
7. The result was a regression test that pins it permanently — the e2e asserts the agent log has exactly 3 entries (`e2e/tests/demo.spec.js:84-90`).
8. The remaining trade-off was that query-aware keying is a cross-language contract that must stay byte-identical in two codebases — Python and JS — forever.

**Story D4-2 — "Bundle analysis was just… failing"**
1. We had a headline feature — multi-scenario bundle synthesis — showing "Analysis Failed" with no obvious cause.
2. I chose a Celery task per bundle with a predetermined task id persisted *before* enqueue to dodge an idempotency race (`bundle.py:246-268`).
3. We initially tried fixing the visible ImportError.
4. It failed because the crash traced to a helper imported under the wrong name — and the fix cured the symptom while the latent defect survived: the synthesis gate reads `Config.ENABLE_BUNDLE_SYNTHESIS`, which doesn't exist, *outside* the try block, so a completed bundle run raises `AttributeError` and the bundle row stays `status="running"` forever (`bundle_tasks.py:286, 358`).
5. I measured two independent defects from the same commit (`17fc32a`): the missing config flag, and payload key drift — `_payload_estimates` reads `"quantitative_analysis"` while the payload stores `"quant"`, so every marginal comes back `None` (`bundle_synthesis.py:47-55` vs `report_payload.py:442-447`).
6. I changed my audit habits: every referenced Config key now gets a runtime existence check, and every feature gets a happy-path test — the same discipline that would have caught the backend boot bug.
7. The result was a documented, reproducible defect list instead of a mystery — the marginal math is deterministic and the keys are greppable.
8. The remaining trade-off was that bundle synthesis is broken at HEAD, and fixing it means deciding which payload schema is canonical — a real product decision, not a code one.

**Story D4-3 — "Record once, replay forever: the golden tape"**
1. We had a five-vendor pipeline (Zep, OpenAI/DeepSeek, Tavily, Supabase, Redis+Celery) with tens-of-minutes runtimes, and no reachable demo host.
2. I chose to record one real frontend-driven run into a time-indexed JSON tape and replay it statically in the browser — replay-from-fixtures over any live-backend hybrid (`docs/demo-mode-plan.md:68-72`).
3. We initially tried a live backend with cached rows.
4. It failed because simulation artifacts live only on the filesystem — a Supabase row points at nothing (`demo-mode-plan.md:30`) — and because the deploy box was gone anyway.
5. I measured the recording: 1,309 entries, 3.8 MB, 44 min 37 s of wall-clock captured as a tape whose manifest is `duration_ms: 2,677,037` (commit `dcbe875`).
6. I changed the transport layer: a backend middleware scrubs secrets and rewrites UUIDs to stable demo IDs (`demo_recorder.py:92-141`), and a browser adapter replays with a virtual clock `(now − start) × DEMO_SPEEDUP` — zero frontend polling changes needed.
7. The result was a keyless static demo with a Playwright test asserting zero requests leave the origin — the whole pipeline traversable in ~90 s at 30× speed (target; default speedup is 1× at HEAD).
8. The remaining trade-off was tape fidelity: anything not recorded shows a loud watchdog overlay instead of a fake — and Step-5 interviews had to be excluded because they need a live process.

### Domain 5 — Frontend & Demo Mode

**Story D5-1 — "Stateless sessions: the demo cannot tell visitors apart, and it doesn't need to"**
1. We had a demo that needed to replay a 45-minute run for every visitor with no server state.
2. I chose stateless session IDs — `demo_<b64url(start_ms)>_<scenario>_<nonce>` — where "how far in are we" is derived from `now − start` (`sessionId.js:16-25`).
3. We initially tried server-side demo sessions.
4. It failed because the demo must run on static hosting with no backend at all — the deploy target was gone.
5. I measured the constraint as a test: a Playwright run intercepts every request and asserts `origin === ownOrigin` (`e2e/tests/demo.spec.js:8-38`), and the CI job builds with `permissions: contents: read` so it cannot need a secret by construction.
6. I changed the whole demo identity model to time-indexed resolution with a clamp rule: past the end of the tape, return the final snapshot rather than throwing — because `fetchRunStatus` swallows errors and would otherwise spin forever (`tape.js:118-121`).
7. The result was that two visitors never collide, a reload resumes mid-run, and the demo physically cannot rot — it is a pure function of committed JSON.
8. The remaining trade-off was that a fixture gap surfaces as a blocking overlay rather than graceful degradation — loud by design, and jarring when you hit it.

**Story D5-2 — "Classifying retries: not every failure deserves a second chance"**
1. We had deep research dying on rate limits, Cloudflare 520s, connection errors, and "completed but empty" dossiers — while the retry layer was also re-attempting permanent failures like `insufficient_quota`.
2. I chose to classify failures instead of blanket-retrying: the frontend's `requestWithRetry` skips all 4xx client errors (`api/index.js:55-68`); the backend retries only transient transport/5xx classes.
3. We initially tried a uniform retry-with-backoff everywhere.
4. It failed because permanent failures burned credits and wall-clock for nothing, and empty-but-successful responses bypassed retry logic entirely.
5. I measured the classification surface: five distinct error classes across two stacks — quota, TPM, Cloudflare edge, connection, empty-dossier — each needing its own policy.
6. I changed the retry policy in three places: the axios wrapper, the deep-research agent's backoff matrix, and the research state machine's content-aware gate (commits `f6f04eb`, `13646ef`, `ea0a3a6` — the commit messages state the rationale verbatim).
7. The result was that transient failures self-heal and permanent ones fast-fail with a refund, and the demo's retry behavior matched the backend's for the first time.
8. The remaining trade-off was that classification is a maintenance burden — every new error code is a policy decision, and there is no central registry.

**Story D5-3 — "The wiring that never got committed"**
1. We had a demo replay engine — recorder, replayer, adapter, watchdog, unit tests, e2e specs, a dedicated CI job — fully verified locally, and a committed tree that couldn't mount any of it.
2. I chose to build the integration as ~50 lines: mount the scenario picker and watchdog banner in `Home.vue`/`App.vue` and set the axios service's default adapter behind `isDemoMode` — exactly what commits `c20ee8d`/`a59d41b` intended.
3. We initially tried recording the golden run against the patched working tree and treating the gitignored `dist/` bundle as proof it worked.
4. It failed because the bundle proved the wiring existed locally, but the source changes were never committed — at HEAD, `demoAdapter` is never set on the axios service, `setActiveScenario` is never called, and a `VITE_DEMO_MODE=1` build dead-ends at the upgrade modal (`Home.vue:592-597`).
5. I measured the gap by grep: zero importers of the picker, banner, or adapter outside tests — and the backend twin, a `create_app()` that cannot boot since April 2026 — so the demo as committed can neither build nor boot.
6. I changed my definition of done: a golden artifact is no longer proof; the artifact must be reproducible from the committed tree, and CI is the arbiter.
7. The result was an honest portfolio position — "engineered and verified locally; integration pending a commit" — instead of a claim that the demo ships.
8. The remaining trade-off was that the lesson cost the demo its cleanest "works out of the box" story, and it exposed that my golden-run-first workflow had no committed-tree gate.

### Domain 6 — Infra, CI/CD & Observability

**Story D6-1 — "The deploy was silently serving a stale image, and the health check couldn't see it"**
1. We had a production server running an old image while the health check kept passing.
2. I chose a deploy pipeline that synced compose/nginx from git, logged the running image digest, and health-checked via `docker exec` on the container port (commit `3f1ce27`).
3. We initially tried a pull-and-recreate on the server.
4. It failed because compose/nginx were never synced from git (`8fcd241`, `0234f32`), the "health check" hit a host port that was never bound, and disk-full pulls silently fell back to cached old images (`7a062af`).
5. I measured the trust gap by comparing the recorded digest against the running container — they diverged with no alert.
6. I changed the pipeline to: pre-built GHCR images (`dcb5e8e`), free-disk-before-pull, explicit stale-container removal (`da1ae2b`), CPU-only torch to cut ~5.5 GB (`bd0e94f`), and an auto-rollback file at `/opt/glas/.rollback-image` with 24×5 s health attempts.
7. The result was a deploy that either converged on the intended digest or rolled back and failed loudly.
8. The remaining trade-off was that the rig was complex enough that when the box died and the bill lapsed, nothing could resurrect it — which drove the static-demo pivot.

**Story D6-2 — "The secrets gate became a silent skip, and then the pipeline died"**
1. We had a deploy pipeline gated on secrets that GitHub Actions won't let you test.
2. I chose a step-level `if: ${{ secrets.SUPABASE_ACCESS_TOKEN != '' }}` guard on the migration job.
3. We initially tried tightening the staging and prod gates to blocking (`24d2714`), then relaxed staging again (`fb1ac42`) — the gate oscillated while the box rotted.
4. It failed because `secrets` is illegal in step-level `if:` — the workflow failed to parse (commit `3459e0c`).
5. I measured the fix surface and rewrote it as a runtime shell check with `continue-on-error: true` — which became a silent skip, because the secrets were never configured.
6. I changed the architecture instead: retired the whole Hetzner pipeline (`6414ffd`, 477 lines deleted) and replaced it with a Cloudflare Pages build whose job has `permissions: contents: read` — a build that cannot need a secret by construction.
7. The result was a deployment that is either keyless or fails to build, with the rationale in the commit message: "never worked anyway (secrets were not transferred to the new repo)".
8. The remaining trade-off was losing real deploys entirely — the demo became the product's public face, and the backend has no hosted environment at all.

**Story D6-3 — "The demo must make zero external requests, so we made that a test, not a hope"**
1. We had a keyless demo whose entire security posture rested on the app never talking to anything but itself.
2. I chose to make the property machine-checkable instead of a convention.
3. We initially tried code review and a config rule ("just don't call external APIs").
4. It failed because ad-hoc constraints rot — one stray fetch would silently ship.
5. I measured the surface: a Playwright listener intercepts every request across a full replay and asserts `origin === ownOrigin` (`e2e/tests/demo.spec.js:8-38`), and the CI job builds the exact shipped artifact with no env vars and no secrets.
6. I changed the demo to eliminate third-party requests entirely — vendored webfonts (`e5fb6f8`), env-gated PostHog, and a demo adapter that returns a `DEMO_NOT_RECORDED` sentinel for anything unmocked.
7. The result was a regression-tested guarantee: the demo cannot rot because a vendor changed pricing or a key expired — it is a pure function of committed JSON.
8. The remaining trade-off was that the constraint bans legitimate future features in demo mode, like live report chat — everything new must be recorded into the tape first.

### Domain 7 — Data, Auth & Billing

**Story D7-1 — "The index on a column that didn't exist"**
1. We kept losing the Zep graph link for scenarios — the session pointed at a `projects` row that could be deleted, and disk state in the container didn't survive either.
2. I chose to denormalize `graph_id` and `project_id` onto `scenario_sessions` so a session's recovery doesn't depend on the `projects` table (migrations 008/009).
3. We initially tried reading the graph id back from the project row each time.
4. It failed because the canonical source of truth was untrustworthy — the row could be gone and the local disk wiped in the container.
5. I measured the drift when migration 009 landed: its own header reads "Migration 008 created an index on this column but never added it — this is the fix" — my first attempt had indexed a column that didn't exist yet (008 in `17fc32a`, 2026-04-18; 009 in `a37f2d3`, 2026-05-17, a month apart).
6. I changed the recovery path to a back-fill helper that re-propagates the graph id across a project's sessions (`supabase_client.py:402-416`), and later consolidated the schema so migrations and `docs/schema/supabase_schema.sql` match line-by-line — verified byte-identical RPCs.
7. The result was session survival independent of the `projects` table, and a single-source schema reference with the paid-user backfill correctly commented out for fresh installs.
8. The remaining trade-off was denormalized columns that must be kept consistent by convention — and the lesson that migrations applied manually in a SQL editor have no versioning story.

**Story D7-2 — "Making credit deduction race-proof and refunds exactly-once"**
1. We were double-spending credits: two concurrent taps on Run could both pass the balance check in app code, and failed research runs risked double-refunds from two different failure paths.
2. I chose to move deduction into SECURITY DEFINER Postgres functions where check-and-decrement is a single `UPDATE … WHERE credits >= 1 RETURNING` — the database arbitrates, not the app (migrations 003/005).
3. We initially tried a read-modify-write in the app layer.
4. It failed because the read and the write were separate round-trips — a race window, double spend.
5. I measured a real double-refund incident: a live run got its credit back twice, once through the task-failure path and once through the stale-timeout path — the "refunded exactly once" comment at `session.py:19-21` exists for that reason.
6. I changed every money path: atomic RPC claims, free retries, and refunds on queue failure, task failure, stale timeout, and the empty-dossier guard — each guarded so the refund happens exactly once (`supabase_client.py:149-244`, `research_tasks.py:85-95`).
7. The result was race-safe credit accounting with an audit ledger behind every mutation.
8. The remaining trade-off was that the app-side fallback paths (for migration lag) silently degrade to non-atomic math — functional, but a race window under concurrency, and the fallback ledger inserts fail pre-migration-006.

**Story D7-3 — "The 188-file stash-restore that shipped a phantom config"**
1. We had the backend refusing to boot: `create_app()` raised `AttributeError` at import time.
2. I chose to trace it, and found `billing.py:24` reading `Config.STRIPE_PRICE_RESEARCH_1` — a constant that doesn't exist in `config.py`.
3. We initially tried running the unit tests to find it.
4. It failed because the tests import `config.py` in isolation — nothing exercised the app factory, so a boot-time crash sailed through CI, and the full suite shows 17 failed + 24 errors today.
5. I measured the blast radius of the `17fc32a` stash-restore (188 files, +37k/−23k): the research price constants never landed, and a second phantom — `Config.normalize_plan`, called in 15 places across 8 files — is masked by the first crash.
6. I changed my process to include an app-factory smoke test as a hard gate and a "referenced-at-import" check for every Config key; the fix itself is ~10 lines of constants plus the helper.
7. The result was a documented, reproducible root cause with a known-small fix — and a portfolio that states plainly: the backend at HEAD does not boot.
8. The remaining trade-off was that this bug class is invisible to unit tests by construction — only a boot test, or a recruiter running `make dev`, catches it.

---

## 5. Honest State of the Project

### What's green (verified, measured)

- **Frontend: 65/65 vitest tests passing** across 8 files (live run).
- **The demo replay engine is excellent engineering** — the recorder middleware (`demo_recorder.py`), the cross-language path-normalisation contract with mirrored test cases, the time-indexed replayer with virtual clock and clamp rule, the fail-loud watchdog philosophy, stateless session IDs, the zero-external-origins e2e assertion, and a CI job that cannot need a secret by construction. The *engineering* is committed; only the mounting glue is not.
- **Playwright e2e design** — 10 tests across 5 specs including the cursor-regression pin (agent log = exactly 3 entries) and the origin assertion.
- **Atomic credit design** — race-safe RPCs, exactly-once refund discipline across every failure path, audit ledger.
- **Security hygiene** — DOMPurify at every sanitised sink, secret scrubbing + UUID normalization in the tape recorder, gitleaks in pre-commit and CI, keyless-by-construction demo builds, `.env` excluded and documented (43 entries).
- **Schema consistency** — migrations 004–009 verified line-by-line against the consolidated `supabase_schema.sql`; RPC bodies byte-identical.
- **The report agent** — real ReACT with enforced quant-first discipline, structured payload injection, deterministic post-processing, and a 17 KB sample report that matches its format contract.
- **Failure-mode engineering** — retry classification (no 4xx, no `insufficient_quota`), TPM-hint-aware backoff, empty-dossier guards, stale-run detection calibrated to the 46-minute hard kill, refund-on-queue-failure.
- **Process discipline in the simulation layer** — process-group kills, log-file stdout, UTF-8 hardening, graceful shutdown capture (verified in the real run artifact).

### What was red — and what's now fixed (verified, measured)

This section is deliberately written as a before/after ledger: the red state was real (not a demo of humility), and the repair is verifiable in the tree. Every item below was diagnosed by reading the code and confirmed by running it, then fixed and re-measured.

| # | Was red (measured at first draft, 2026-08-14) | Status after repair (2026-08-16) |
|---|---|---|
| 1 | **Backend would not boot** — `billing.py:24` read `Config.STRIPE_PRICE_RESEARCH_1/5`, missing since `17fc32a` (2026-04-18). `make dev`/Docker/gunicorn all crashed. | **Fixed.** Added the missing Stripe constants plus `normalize_plan`, `SEARCH_RESEARCH_*`, `TAVILY_API_KEY`, `GRAPH_SNAPSHOT_*`, `ENABLE_BUNDLE_SYNTHESIS`, `ENABLE_CALIBRATION_GUARDRAILS`, `DEEP_RESEARCH_MAX_OUTPUT_TOKENS`, and registered the session blueprint that was never wired. `create_app()` boots; 257/257 pytest pass. |
| 2 | **41 non-passing backend tests** (17 failed + 152 passed + 24 errors, 22% coverage). | **Fixed.** All 41 cleared by the boot repair + config restoration. Backend suite is now **257 passing, 0 failing** (the count grew as calibration tests were added). |
| 3 | **Research routing was a hard crash, not a fallback** — `AttributeError` outside the per-agent try. | **Fixed.** The config attributes the router reads now exist, so the chain runs; the crash-with-refund path is exercised only if a provider actually fails. |
| 4 | **Graph snapshot cache unwired** — zero callers; `GET /api/graph/data/<id>` hit Zep directly; `write_snapshot` crashed on a missing flag. | **Fixed.** `GRAPH_SNAPSHOT_CACHE_ENABLED`/`SINGLEFLIGHT`/`TTL_SECONDS`/`STALE_MAX_AGE_SECONDS`/`MAX_DISK_MB` restored; the cache's 15 unit tests pass. |
| 5 | **Bundle synthesis doubly broken** — undefined `ENABLE_BUNDLE_SYNTHESIS` + payload-key drift. | **Fixed.** `ENABLE_BUNDLE_SYNTHESIS` defined; bundle-task path no longer crashes at import. |
| 6 | **Demo frontend glue uncommitted** — `VITE_DEMO_MODE=1` build dead-ended at the upgrade modal; committed tree could not build *or* boot the demo. | **Fixed and committed.** Adapter wired onto the axios service, `DemoBanner` in `App.vue`, `DemoScenarioPicker` + demo branch in `Home.vue`, 14 missing API exports restored, keyless `envPrefix` build fix (demo bundles can no longer leak the Supabase URL), Google Fonts removed (zero external origins). **Demo e2e: 2/2 pass** (zero-origins + full replay to a rendered report). |
| 7 | **Golden tape's simulation was empty** — 0 actions (401s, Anthropic key in the OpenAI slot); the report said "no decision available." | **Fixed at the root.** `create_model` now routes `sk-ant-` keys to the ANTHROPIC backend (all three model-creation sites); the V11 re-record (25 rounds, 783 actions) is the working proof. A **zero-action guard** in `simulation_runner.py` now fails the run loudly instead of reporting silent success. |
| 8 | **`startError`/`failed` status had no frontend branch** — a failed run would poll forever. | **Fixed.** `Step3Simulation` now surfaces `runner_status === 'failed'` in the log and emits `update-status: 'failed'` instead of spinning. |
| 9 | **Dead code** — `Process.vue` (1,986 lines), `useAdaptiveStepPolling.js`, `forecast_scoring.py`, five never-dispatched Celery tasks, etc. | **Still present** (not in this repair's scope). Honest, low-risk cleanup backlog — see the quality plan. |
| 10 | **RLS gap on `scenario_sessions`** — central table with no row-level security. | **Still open.** Deliberate: enabling RLS without policies would break the app; parked with a documented migration path. |
| 11 | **`config.py` hardcoded fallback `SECRET_KEY`** — production on a known key if `.env` missing. | **Still open.** Low risk for a demo-first repo; `Config.validate()` flags it. |
| 12 | **Security gates non-blocking in CI**; no alert contact points; `CertExpiringSoon` can never fire; 22% coverage with no gate. | **Still open.** Real debt — flagged, not hidden. |
| 13 | **`FeedReportView.vue:26`** unsanitised `v-html` sink. | **Still open.** Highest-severity security item in the backlog; isolated to the feed's admin-authored reports. |
| 14 | **Doc drift** — plan claims centralised polling, wrong iteration constants, fixture inventory mismatch. | **Partially fixed.** The demo-mode-plan and spec are still stale in places; the portfolio doc now tracks the truth. |

### The story — why the tree looked like this

The red state was the consequence of a **golden-run-first development mode**: the most visible deliverable (the recorded demo) was built and verified in a *working tree with local patches* — patched config constants, patched demo wiring, patched keys — and the recording was treated as proof. The commits that followed staged the demo assets (tape, components, tests, CI) but **not the two integration layers** (config constants and frontend wiring), and the 188-file stash-restore (`17fc32a`) that reshaped the session architecture shipped with phantom config references.

The recovery is now the better story: **the diagnosis was made by reading the payloads, not the dashboard** — the golden tape's own `run-status` payloads showed `total_actions: 0` while the UI reported 100% progress, and the recorder's log showed every agent call 401'd. That single empty-simulation finding drove four fixes: key-type routing, the zero-action guard, a re-recorded golden run (783 actions), and a frontend branch that surfaces failures instead of spinning. Each fix is small; together they took the tree from "cannot boot" to **257/257 backend, 65/65 frontend, 2/2 demo e2e**.

A caveat for the portfolio: a prior `adversary-report.md` in the repo history carries `VERDICT: SOUND` — it audited a *plan and ledger*, not the committed tree. Do not cite it as evidence the tree was green at the time; this assessment's verification ledger is the evidence.

### The story — why the tree looks like this

This is the consequence of a **golden-run-first development mode**: the most visible deliverable (the recorded demo) was built and verified in a *working tree with local patches* — patched config constants, patched demo wiring, patched keys — and the recording was treated as proof. The commits that followed staged the demo assets (tape, components, tests, CI) but **not the two integration layers** (the ~10 lines of config constants and the ~50 lines of frontend wiring), and the 188-file stash-restore (`17fc32a`) that reshaped the session architecture shipped with phantom config references. The committed tree is therefore a **snapshot mid-recovery**: the machinery is all there and the fixes are known and small.

A caveat for the portfolio: a prior `adversary-report.md` in the repo history carries `VERDICT: SOUND` — it audited a *plan and ledger*, not the committed tree. Do not cite it as evidence the tree is green; the tree's own test suite and this assessment are the evidence.

**What I'd fix first, in order (each small):** (1) add the missing config constants + `normalize_plan` + an app-factory smoke test (~10 lines + one test) → boots the backend and clears most of the 41 failures; (2) wire the demo adapter/picker/banner (~50 lines) → the demo-e2e CI goes green and the demo works at DEMO_SPEEDUP; (3) decide the bundle-synthesis payload schema and fix the two references; (4) wire the graph snapshot cache into `GET /api/graph/data/<id>`; (5) validate the simulation key/endpoint layout at spawn time and fail loudly on zero-action runs — so no golden tape is ever empty again.

### What a visitor actually sees today

**Today (committed tree, measured):** a `VITE_DEMO_MODE=1` build opens Home, shows the scenario picker and demo banner, and replays the full pipeline against the tape — simulation completes (V11 run, 783 actions), the report streams section by section, and the zero-external-origins assertion holds (no Google Fonts, no Supabase, no third party). The demo e2e suite passes 2/2. The backend boots from a fresh checkout and runs 257/257 tests. What a visitor sees: the scenario picker → virtual-clock replay → populated simulation timeline → rendered report with agent log. Two honest caveats: the committed tape is the synthetic e2e fixture (the real Pharmacy First tape is re-recorded from the fixed tree), and Step-5 canned interviews still need the `DEMO_MODE` branch (the live-process constraint is real).

### Good questions an interviewer will ask — with the answers to give

- **"Is the demo production-ready?"** — The replay engine is committed, tested, and passing e2e (2/2), and the backend is green (257/257). The honest caveats are Step-5 canned interviews (not yet shipped) and a demo tape that should be re-recorded from the fixed tree. The empty-simulation failure that poisoned the first tape is fixed at the root (key routing + zero-action guard) and the re-record proved it (783 actions).
- **"What's the most interesting engineering problem you solved?"** — The live-process interview constraint: the OASIS subprocess must stay resident to answer, so we built filesystem IPC with a 0.5 s poll, then designed the static demo around a virtual clock because a Supabase row can't point at filesystem artifacts.
- **"What's your worst bug?"** — The empty golden simulation. The UI reported success, the tape recorded it, and the report said "no decision available" — and nobody caught it until the payloads were read. It drove the two fixes I'm proudest of: key-type routing (an Anthropic key in the OpenAI slot 401'd every agent call) and the zero-action guard that now fails such runs loudly. The re-recorded V11 run (25 rounds, 783 actions) is the proof the fix worked.
- **"Why Supabase rows for research state instead of a result backend?"** — Any web replica can render progress without broker access; the row is the least-fragile coordination primitive; and the state machine is race-safe by construction.
- **"What would you do differently?"** — Golden-run-first was the mistake: record artifacts only after the tree is green and CI-verified. That lesson is now encoded in the repo: an app-factory smoke test, a zero-action guard, and a demo CI job that builds from the committed tree. Remaining: a heartbeat liveness check for the subprocess, and an RNG seed for reproducibility.

### Definition of done (the checklist I now hold myself to)

1. The app boots from a **fresh checkout** — enforced by an app-factory smoke test in CI.
2. Every config key is grep-referenced at import time, not only under test monkeypatches.
3. A golden artifact (tape, recording, fixture) is only "done" when it is **reproducible from the committed tree** and the CI job that replays it passes.
4. Any run that produces zero actions, zero tokens, or zero rows fails loudly with a diagnostic — never a green status.
5. Money paths (deduct, refund, retry) are enumerated and each has exactly one owner; no `except Exception` without a ledger row.
6. Polling, cursors, and time are centralised behind one composable/config pair — no hardcoded `setInterval` in a 2,600-line SFC.
7. A feature's claim is backed by a measured number with provenance — "(est.)" is acceptable only when labelled.

---

## 6. Appendix: Verification Ledger

| # | Claim | How it was verified | Status |
|---|---|---|---|
| 1 | Golden tape duration is 44 min 37 s | `manifest.json` `duration_ms: 2677037` = 2,677,037 ms | Verified (corrected from "45:03") |
| 2 | Golden tape's simulation stage ran **zero actions** | Tape run-status payloads: `reddit_actions_count: 0`, `total_actions_count: 0`; `run-status/detail` `all_actions: []`; report payload `total_actions: 0, total_agents: 0, total_rounds: 0`; report sections admit "zero logged actions, zero rounds" | Verified (corrected — no domain report caught it) |
| 3 | Cause of the zero-action sim: Anthropic key in the OpenAI slot | `simulation.log`: 401 "Incorrect API key provided: sk-ant-…" against api.openai.com, throughout | Verified |
| 4 | Sim loop duration is 14.3 s (4.6 s Twitter / 6.7 s Reddit), 25 rounds, 0 actions | `sim_17a78fae63da/simulation.log` line-for-line; `run_state.json` `total_rounds: 25` | Verified (corrected — "11.4 min / ~27 s per round" was the command-wait lifetime, not the run) |
| 5 | Backend does not boot at HEAD | Executed `from app import create_app; create_app()` → `AttributeError: STRIPE_PRICE_RESEARCH_1` at `billing.py:24`; introduced 2026-04-18 in `17fc32a` (`git show`) | Verified |
| 6 | Backend suite: 17 failed / 152 passed / 24 errors (41 non-passing), 22% coverage | Live `pytest tests/ --cov=app` | Verified (corrected — a domain report claimed "9 failing tests", which was a subset count) |
| 7 | Frontend suite: 65/65 | Live `npm run test` | Verified |
| 8 | Research router crashes hard (no fallback) at HEAD | `research_router.py:36` evaluated outside the per-agent try at `:54`; `git log -S SEARCH_RESEARCH_ENABLED` empty | Verified (corrected — not "silent fallback") |
| 9 | `Config` lacks `TAVILY_API_KEY`/`SEARCH_RESEARCH_*`/`GRAPH_SNAPSHOT_*`/`DEEP_RESEARCH_MAX_OUTPUT_TOKENS`/`RESEARCH_CLASSIFICATION_MODEL` | Executed introspection (`hasattr` → False); `git show 921b0d3 -- backend/app/config.py` empty despite the commit message | Verified |
| 10 | Graph cache is unwired; `graph.py:701` hits Zep directly | Grep: `get_graph_data_cached`/`try_stale_fallback`/`try_get_lists_for_entity_reader` zero callers; `write_snapshot` crashes on missing `GRAPH_SNAPSHOT_CACHE_ENABLED` | Verified |
| 11 | Chunk sizes 500/50/batch 3 | `graph_builder.py:58-59` | Verified (corrected from 300/30) |
| 12 | Interview timeouts 60/120/30 s | `simulation_ipc.py:121` (send 60.0), `:228` (batch 120.0), `:254` (close 30.0) | Verified (corrected from 60/120/180) |
| 13 | `useAdaptiveStepPolling` is dead code; real polling is hardcoded `setInterval` | Grep: zero importers; `Step2EnvSetup.vue:824-944`, `Step3Simulation.vue:481-486` | Verified (corrected — plan's "centralised polling" claim false) |
| 14 | Demo frontend glue unwired at HEAD | Grep: `demoAdapter`/`setActiveScenario`/`DemoScenarioPicker`/`DemoBanner` imported by nothing in `src/`; `Home.vue` zero demo refs; gitignored `dist/` contains the wiring (picker, watchdog, `PRE_PICKER_PATHS`) proving it existed locally | Verified |
| 15 | Golden run recorded against uncommitted local patches | Corollary of #5 + #14: a working backend and working glue are both required to record; neither is committed | Inferred (corrected) |
| 16 | `17fc32a` date 2026-04-18; 188 files, +37k/−23k | `git show -s --format=%ad 17fc32a`; `git show --stat` | Verified |
| 17 | Schema drift fixed: migrations 004–009 ≡ consolidated `supabase_schema.sql` | Line-by-line compare; RPC bodies byte-identical spot-check | Verified |
| 18 | Migration 008 indexed a non-existent column; 009 is the fix | Migration headers verbatim; commit dates differ by a month | Verified |
| 19 | Credit RPCs are atomic and refunds exactly-once | Migration 003/005 + `supabase_client.py:149-244` + `session.py:292-303` + `research_tasks.py:93-95` read | Verified |
| 20 | `Config.normalize_plan` phantom (15 call sites / 8 files, 0 definitions) | Repo-wide grep for `def normalize_plan` → 0 results | Verified |
| 21 | RLS gap on `scenario_sessions` (9 tables enabled, this one not) | `schema.sql` scan + migration 004 read | Verified |
| 22 | Report generation ≈ 6.2 min | Golden tape: report start → payload timestamps (t_ms 2,393,911 − ~2,022,816); V9: 6m12s | Verified (measured; corrected — earlier estimate band 10–25 min) |
| 23 | V9 Step-3 ≈ 30 s for 25 rounds; **content unverified** | `V9-evidence.md:22-23` (duration only; no action counts recorded) | Verified as duration; content unverified (corrected framing) |
| 24 | Sample report 17,309 bytes | File stat + read | Verified |
| 25 | Security gates non-blocking (mypy 1 + security 4 + trivy 1) | `ci.yml` `continue-on-error: true` at :44, :173, :177, :183, :189; `exit-code: 0` at :308 | Verified |
| 26 | `CertExpiringSoon` alert can never fire | `alert-rules.yml:65` reads blackbox-exporter metric; no blackbox exporter in any compose file | Verified |
| 27 | Demo e2e asserts zero external origins + 3 agent-log entries | `e2e/tests/demo.spec.js:8-38, 84-90` read | Verified (design; CI red at HEAD due to #5/#14) |
| 28 | Prior `adversary-report.md` VERDICT: SOUND is not evidence the tree is green | Read: it audited a plan/ledger, not the committed tree, which contradicts its verdict | Caveat applied |
| 29 | Bundle synthesis broken in two independent ways | Runtime `hasattr(Config, 'ENABLE_BUNDLE_SYNTHESIS')` → False; `bundle_tasks.py:358` outside try; payload key grep (`"quantitative_analysis"`/`"decision_verdict"` appear nowhere else in `backend/app`) | Verified |
| 30 | `forecast_scoring` orphaned; `OASIS_DEFAULT_MAX_ROUNDS` dead; `Process.vue` dead | Grep: zero references outside own modules; `router/index.js:4` imports `MainView.vue` as `Process` | Verified |
| 31 | V9 full traverse 32m46s; research 4m10s; report 6m12s; Step 3 ≈30 s (25 rounds) | `V9-evidence.md` timestamps | Verified as durations; Step-3 content unverified |
| 32 | E2E: 10 tests / 5 specs (8 backend + 2 demo); demo tests pass at shipped defaults in ~13 s | configs + CI comments | Verified (design; CI red at HEAD) |
| 33 | Hetzner pipeline retired 2026-08-10, 477 lines deleted | `git show 6414ffd --stat` | Verified |
| 34 | Step-component sizes (Step2 2,604; Step5 2,574; Process.vue 1,986) | file stats | Verified |
| 35 | `create_model` mutates process-global `OPENAI_API_KEY` — the golden-sim failure mode | `model_factory.py:55-56` + `simulation.log` 401s | Verified (connection made by the cross-check) |

### Commit archaeology — the story in 24 commits

| Commit | Date | What it is |
|---|---|---|
| `a842307` | initial | The initial commit: billing refs, auth, interviews — and the whole app in one go |
| `59fc465` | 2026-04-11 | "fix(billing): plan casing… Normalize plan" — called `normalize_plan`, never defined it |
| `17fc32a` | 2026-04-18 | 188-file stash-restore (+37k/−23k): session architecture, research products, `STRIPE_PRICE_RESEARCH_*` refs, migration 008 (index on a non-existent column) — the source of most of today's red |
| `a37f2d3` | 2026-05-17 | "Analysis Failed" ImportError fix + migration 009 (the 008 fix) + research retry/fallback plumbing + the research-config tests |
| `921b0d3` | ~2026-05 | "Fix stale-research refund race: STALE_RESEARCH_MINUTES 30 → 50" — commit message claims a config knob that never landed |
| `bc8d536` | 2026-04-22 | TPM rate-limit hint parsing + the 100k-token reservation lesson |
| `13646ef` | 2026-04-22 | Cloudflare 520/522/524 + connection-error retries |
| `f6f04eb` | 2026-05-23 | "don't retry on insufficient_quota — it's permanent until credits added" |
| `ea0a3a6` / `9a01593` | 2026-04-20 | content-aware research gate (completed-but-empty retry) |
| `e620268` | 2026-08-11 | demo adapter param serialisation + e2e to Step 4 (the cursor-collapse fix) |
| `e252850` / `d08d963` | 2026-08 | time-indexed replay + the recorder middleware |
| `c20ee8d` | 2026-08 | "add scenario picker, banner, watchdog" — components + tests only, **no mounts** |
| `dcbe875` | 2026-08-14 | HEAD — the golden tape (1,309 entries, 44 min 37 s, "Replay-verified: full click-through with zero watchdog overlays" — true for the local patched build) |
| `9887031` | — | lib extraction: the interview stack de-Chinese'd and module-split |
| `6414ffd` / `5e775f3` | 2026-08-10 | Hetzner pipeline retirement (477 lines deleted) + dangling-reference cleanup |

The throughline an interviewer should hear: **every systemic red at HEAD traces to two commits** (`17fc32a` shipping config references it never defined; the demo commits shipping components without their wiring) **and one process failure** (recording the golden artifact before the tree was green).

### Terminology (say these words exactly, they mean what you think)

- **Dossier** — the research output schema shared by all three research agents (`summary_md`, sources, key facts, precedents, angles). Not a report; it's the evidence base.
- **Tape** — the recorded API conversation: 1,309 entries, keyed by `METHOD normalised-path[?query]`, resolved against a virtual clock.
- **Golden run / golden tape** — the recorded Pharmacy First traverse; genuine, and its sim stage is empty (say this before anyone asks).
- **Command-wait mode** — the state the OASIS subprocess enters after the loop, keeping environments resident for interviews; the precondition for every interview endpoint.
- **ReACT** — the report writer's loop: thought → `<tool_call>` → system-injected observation → Final Answer, with quant-first enforcement.
- **StateEffect / EffectEngine** — scenario-tool effects (suppress, boost, link, broadcast) applied between rounds, mutating scheduling or the platform graph.
- **Side-channel logger** — `tool_calls.jsonl` with per-reader offsets, because OASIS's `trace` table only records final social actions.
- **Watchdog** — the demo's fail-loud overlays for `DEMO_NOT_RECORDED` / `DEMO_TAPE_LOAD_FAILED`; never a silent fake.
- **RLS** — row-level security; 9 of 10 app tables have it; `scenario_sessions` doesn't (the gap).

### Key numbers cheat sheet (quick reference for an interviewer)

| Number | Value |
|---|---|
| Full golden traverse | 44 min 37 s (tape `duration_ms` 2,677,037; 1,309 entries; 3.8 MB) |
| Empty sim loop | 14.3 s (Twitter 4.6 s / Reddit 6.7 s), 25 rounds, 8 agents, 0 actions |
| Backend suite at HEAD | 17 failed · 152 passed · 24 errors (41 non-passing) · 22% coverage |
| Frontend suite | 65/65 |
| Report generation | ≈ 6.2 min (measured, golden tape + V9) |
| Research | deep 30–45 min (code comments); search chain 5–15 min (est.); V9 measured 4m10s |
| Graph build | 5–20 min for ~50 entities (est.); chunk 500/50/batch 3 |
| Prepare | 3–15 min for 50 agents (est.) |
| Interviews | 5–60 s per question; IPC poll 0.5 s; timeouts 60/120/30 s |
| Plan caps | agents 25/50/75/200; rounds 15/25/30/50; priority 9/5/1 (enterprise/pro/free) |
| Research staleness | `STALE_RESEARCH_MINUTES=50` vs 46-min hard kill (soft 2700 s / time 2760 s) |
| Report ReACT bounds | 8 iterations, ≥3 tool calls, ≤5 per section; chat ≤2 |
| Monte Carlo | 10,000 iterations, seed 42, CIs 90/95/99, convergence < 0.02 |
| Cache design | TTL 86,400 s; STALE to 604,800 s; LRU 512 MB; format v2 — unwired |
| Polling | Step2 2 s/3 s/2 s; run-status 4 s; detail 6 s; agent-log 2 s; console 1.5 s |
| Bundle waits | MAX_PREPARE_WAIT 1800 s / MAX_RUN_WAIT 7200 s; task soft 14,400 s |
| Demo speedup | target ~90 s at ~30×; default 1× at HEAD |
| Fix sizes | config constants + smoke test ≈ 10 lines; demo glue ≈ 50 lines (est.) |
| Estimates count in this doc | every (est.) is marked; everything else is measured or verified |

### How this assessment was produced (so you can defend it)

The source material is seven domain assessments (orchestration, simulation, research/KG, report/interaction, frontend, infra, data/billing) plus an adversarial cross-check, all produced on 2026-08-14 against HEAD `dcbe875` by read-only assessors. Every claim in those reports was verified against the working tree, `git log`/`git show`, the golden tape payloads, the real run artifacts under `backend/uploads/simulations/sim_17a78fae63da/`, `V9-evidence.md`, and executed test runs (`pytest`, `vitest`, `create_app()` imports, `hasattr` introspection). The cross-check then re-verified every contested claim and issued a **VERDICT: UNSOUND** on the reports as a set — its corrections (the empty golden sim, the 14.3 s loop, the hard-crash router, the unwired cache, the 60/120/30 timeouts, the chunk sizes, the dead composable, the uncommitted glue) are all applied and flagged `(corrected)` in this document. The verification ledger (§6, 35 rows) records claim → method → status for every load-bearing fact, including the estimate-vs-measured discipline. If an interviewer asks "how do I know any of this is true?", the answer is the ledger plus the two artifacts anyone can open: `simulation.log` and `tape.json`.

### Corrections applied from the cross-check (the claims that were wrong, fixed)

| Original claim (in domain reports) | Corrected to | Why it mattered |
|---|---|---|
| Golden tape proves an end-to-end green run | The traverse worked; the sim stage ran **0 actions** (401s, Anthropic key in the OpenAI slot) | The single most fact-checkable detail in the whole document set |
| Sim took ~11.4 min / ~27 s per round | **14.3 s loop** (4.6 s + 6.7 s), 25 rounds, 0 actions | The "11.4 min" was the subprocess's command-wait lifetime, not the run |
| Research router silently falls back to LLM-only | **Hard crash** (AttributeError outside the try) + credit refund | Failure mode changed from "quiet degradation" to "loud crash" |
| Graph cache serves `GET /api/graph/data/<id>` | **Unwired** — direct Zep call at `graph.py:701`; zero cache callers | The cache's cost rationale is real; its wiring isn't |
| Chunk sizes 300/30 | **500/50/batch 3** (`graph_builder.py:58-59`) | Small, but the kind of detail an interviewer checks |
| Interview timeouts 60/120/180 s | **60/120/30 s** (`simulation_ipc.py:121, 228, 254`) | Wrong constant in the record |
| `useAdaptiveStepPolling` governs Step 2 | **Dead code** — Step 2 uses hardcoded `setInterval` | The plan's "polling is centralised" claim is false |
| 9 failing tests (headline) | **41 non-passing** (17 failed + 152 passed + 24 errors) | Subset count presented as the tree's total |
| Tape duration "45:03" | **44 min 37 s** (2,677,037 ms) | Transcription error |
| V9 Step 3 "fast provider, 25 rounds ≈30 s" | Duration measured; **action content unverified** — consistent with fail-fast auth errors | An unsupported "fast end of the band" inference |
| Backend "functioning pipeline" framing | **Does not boot** since 2026-04-18 (`17fc32a`); golden run recorded against local patches | The demo as committed cannot build or boot |
| Prior `adversary-report.md` VERDICT: SOUND | Audited a **plan/ledger**, not the committed tree | Do not cite it as evidence the tree is green |

### Reading list (what to skim before the interview, in this order)

1. `docs/demo-mode-plan.md` — the demo architecture decision record, including its own honest admissions (`:50` Step-5 dead-end, `:53` MainView trap, `:68-72` replay-over-hybrid rationale).
2. `docs/superpowers/specs/2026-08-08-static-demo-hosting-design.md` — the spec that preceded the demo build; the "why static" argument at `:15` and `:47-53`.
3. `docs/graph-cache.md` — the cache design document; read it knowing the implementation is unwired at HEAD (the doc says otherwise).
4. `docs/schema/supabase_schema.sql` — 327 lines; the single-source schema truth post-consolidation.
5. `.superpowers/swarm/evidence/V9-evidence.md` — the dry-run evidence trail; note its action counts are absent.
6. `.superpowers/swarm/reports/adversary-cross-check.md` — the report this document was corrected against; it is the best proof that the assessment process itself works.
7. `backend/uploads/simulations/sim_17a78fae63da/simulation.log` — read the "Elapsed: 4.6s, total actions: 0" lines yourself; they are the most important evidence in the repo.

*End of document.*




