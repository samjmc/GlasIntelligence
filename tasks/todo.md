## Remaining Launch Setup - March 18, 2026

### Plan
- [x] Stripe setup — Create products/prices, add keys to .env
- [x] Zep API key — Added to .env
- [x] Redis — Installed locally (C:\redis), running on port 6379
- [x] Login redirect fix — LoginView.vue now respects ?redirect param
- [x] CORS fix — Added port 3001 to CORS_ORIGINS
- [x] Stripe webhook — Created endpoint, secret added to .env
- [x] Welcome email — Updated to match free tier (no free credit)
- [x] ~~Production Docker config~~ — **OBSOLETED** — static hosting via Cloudflare Pages (Aug 2026)
- [x] ~~Deployment script~~ — **OBSOLETED** — static hosting via Cloudflare Pages (Aug 2026)
- [x] ~~Production .env template~~ — **OBSOLETED** — static hosting via Cloudflare Pages (Aug 2026)
- [ ] **Manual: Cloudflare Pages setup** (configure Git integration for auto-builds, see docs/superpowers/specs/2026-08-08-static-demo-hosting-design.md)
- [ ] **Manual: Sign up for Resend** (resend.com) and add API key to .env
- [ ] **Manual: Set ADMIN_USER_IDS** after signing up on the platform
- [ ] **Manual: Switch Stripe to live mode** when ready to charge real money

### Notes
- Stripe is in TEST mode (sk_test_). When ready for real payments, create live products in Stripe and update keys
- Stripe webhook endpoint is registered at glasinsight.com/api/billing/webhook
- Redis installed at C:\redis\redis-server.exe (Windows port v5.0.14.1)
- Docker Desktop was installed but daemon wouldn't start — Redis installed natively instead
- Resend email service gracefully skips if not configured
- Supabase auth redirect URLs need to be updated in Supabase dashboard when going to production

### Review
- All code changes completed successfully
- Backend starts clean with all services configured
- Frontend running on port 3001, backend on 5001
- All Stripe products/prices created in test mode
- Production Docker setup ready with SSL/certbot

---

## Backlog — input validation (simulation prepare)

- [ ] **`simulation_manager.prepare_simulation`**: `simulation_requirement` is passed into `scenario_context` with **no length cap** (unlike `document_text`, which is truncated to 5000 chars). When formalising input validation on the **prepare** API (`backend/app/api/simulation.py` → `prepare_simulation`), add a truncation limit for the requirement string (e.g. **`[:2000]`**) at the boundary and/or mirror it inside `prepare_simulation` for non-HTTP callers.

---

## Deferred — `simulation_manager.py` (state persistence & profile loading)

- [ ] **`_load_simulation_state`**: Still brittle for **corrupt JSON**, **non-object root** (`[]` / scalar), and **`warnings` (or other list fields) not a list** — can raise or yield types that break `warnings.append` later. Add a **schema validation wrapper** (or structured load + defaults) when formalising **state persistence**.
- [ ] **`profile_progress` / `prepare_simulation`**: **`ZeroDivisionError`** if **`total_entities == 0`** while **`filtered.filtered_count > 0`** (inconsistent entity reader). **Guard** `current / total` (or assert/sync counts) when hardening **entity counting**.
- [ ] **`get_profiles` (JSON path)**: **`json.load`** return type **not validated** — root may not be a **`list[dict]`**. Add validation (or safe parse) when hardening **profile loading**.

---

## Deferred — `zep_entity_reader.py` / entity-detail error signaling

- [ ] **`get_entity_with_context` (L607–609)**: Broad **`except Exception` → `return None`**. After **`get_node_edges`** was changed to **raise** on Zep failure, failures are still swallowed here → **`simulation.py`** entity-detail route treats as **missing** → **404 "Entity not found"** instead of **5xx**, so clients cannot tell **transient Zep errors** from **unknown UUID**. **Severity: medium**; **bulk prepare** uses **`filter_defined_entities`**, not this path.
  - **(a)** Accept 404 for now; monitor prod logs; add instrumentation.
  - **(b)** Tighten **`get_entity_with_context`** to **re-raise** or return a structured error for **5xx**.
  - **(c)** Move **try/except** to **API layer** (`simulation.py` **`get_entity_detail`**) so callers control semantics.
  - **When:** Post-launch if entity-detail 404s are noisy; pre-launch if stricter HTTP semantics are required.

---

## Housekeeping — `simulation_runner.py` (logged Apr 3, 2026)

- [ ] **`_monitor_threads` dict**: Written when starting the monitor thread (`SimulationRunner._monitor_threads[simulation_id] = monitor_thread`) but **never read or cleaned up**. Remove dict + assignment in a housekeeping pass (or wire it up if you intend join/inspection).
- [ ] **`_read_actions_from_file` round coercion**: Bulk log reading uses `round_num=data.get("round", 0)` with **no** `int`/`float` coercion. **`_read_action_log`** already coerces `action_round` before `AgentAction`. Align coercion when hardening bulk log reading so malformed JSON cannot diverge between streaming state vs `get_all_actions` / timeline paths.

---

## Deferred — `oasis_profile_generator.py`

- [ ] **`interested_topics` (and similar list fields)**: **Non-string list elements** can pass through unchanged — add a **full profile validation pass** (normalize or reject bad LLM output) before persistence / OASIS export.
- [ ] **`parallel_count`**: Currently **uncapped** in parallel profile generation — add a **ceiling** aligned with **`Config` / worker limits** when formalising **resource limits**.

### Post-audit backlog (logged Apr 3, 2026)

- [ ] **#12 — Zep client thread-safety** (`_search_zep_for_entity`, hybrid search): Only OpenAI client uses `self._client_lock`; **`self.zep_client`** is used from **two threads** (edge + node search). **Severity: low** (depends on Zep SDK thread-safety, often OK). **Fix if prod issues:** wrap Zep calls in same lock or use per-thread Zep clients. **When:** If production shows Zep-related concurrency glitches; else defer.

- [ ] **#13 — `safe_float` unused** (~400–405): Dead code; remove or add comment *reserved for future numeric fields*. **Severity: trivial.** **When:** Next cleanup pass.

- [ ] **#14 — Redundant random defaults** (`OasisAgentProfile` construction ~425–428 area): After `safe_int` coercion, `profile_data` always has karma / friend / follower / statuses keys — `.get(..., random.randint(...))` fallbacks are **unreachable** on normal paths. **Severity: trivial.** **Fix:** Drop random defaults once keys are guaranteed. **When:** Next cleanup pass.

- [ ] **#15 — Institutional type normalization** (`_generate_profile_rule_based` ~1064): Covers `organization` / `organisation`; may miss **`org`**, **`nonprofit_org`**, mixed case, etc. **Severity: low.** **Fix:** Optional `_normalize_type`-style matching for this branch. **When:** If prod shows wrong institutional personas; else defer.

- [ ] **#16 — Numeric coercion contract (informational)**: Missing social stats → **0**; missing age → **25**; `account_age_days` → **365**. Reddit save maps **karma 0 → 1000**. **Verify in OASIS integration testing** that all consumers accept **0** for counts (no required null/missing distinction). **When:** OASIS integration testing.

---

## Deferred — `graph.py`

- [ ] **Legacy graphs without `user_id`**: May be **world-readable among authed users** (no row-level owner) — **migration** to **backfill `user_id`** (or equivalent ownership) on old rows.
- [ ] **`_project_meta_for_graph_id`**: **500-project scan cap** — replace with **pagination**, **DB index**, or targeted lookup so large workspaces do not miss metadata.

---

## Deferred — `Home.vue`

- [ ] **`pollSessionResearch` concurrency**: Multiple overlapping calls can share a single **`researchPollActive`** ref — if **concurrent polling** becomes possible (e.g. multi-session UI), add an **instance counter** (or per-session guard) so one completion does not clear another poll’s state.

---

## Deferred — `BundleResultsView.vue`

- [ ] **`isFirstBundleScenario` string indices**: If **`index` / `scenario_index`** arrive as **strings** (e.g. **`"1"`**), the **`Number(...)`** fallback can treat **`"1"`** as **first** (**`n === 1`**) even for the **second** 0-based row. **`typeof sc.index === 'number'`** skips that path for real numbers. **Fix if API ever returns string indices:** normalize with **`Number.parseInt(..., 10)`** after **`typeof === 'string'`** checks, or require numeric **`index`** from the bundle **`/status`** response only. **Severity: low** (current API uses numeric **`index`** from **`bundle.py`**).

---

## Deferred — `bundle_tasks.py` (bundle runtime & idempotency)

- [ ] **Per-scenario `generate_report` is synchronous** in `run_bundle_task`: each completed scenario blocks the Celery task until report + payload work finishes, adding **significant wall-clock** before the next scenario and before bundle-level synthesis. **When optimising bundle runtime:** consider **async** or **background** report generation (e.g. chained tasks, worker pool, or post-loop batch) so scenario throughput is not serialised on report latency.
- [ ] **Worker redelivery** (`acks_late=True`, non-idempotent bundle task): a restarted/redelivered task can **regenerate simulations and reports** for scenarios that already completed — same class as the **existing bundle idempotency gap** documented in-task. **When adding bundle resume / idempotency:** dedupe by stored `simulation_id` / `report_id`, skip completed scenarios, or use explicit checkpointing so redelivery does not duplicate payloads.

---

## Deferred — calibration / config / forecast scoring (session wrap-up)

- [ ] **`calibration_guardrails.py` — `CORRELATION_DISCOUNT = 0.7`**: Heuristic with no formal derivation — **document basis** when calibration methodology is formalised.
- [ ] **`calibration_guardrails.py` — `corrections` strings**: No numeric before/after per field — **extend** when building the **A/B comparison** pipeline.
- [ ] **`quantitative_analysis_service.py`**: **Raw guardrail values** not persisted — add **`raw_low` / `raw_mid` / `raw_high`** or **`guardrail_corrections`** on the estimate when building **scoring comparison**.
- [ ] **`config.py`**: **`logging.getLogger("glas.config")`** (via **`get_logger`**) may not match other **`get_logger`** sinks/formatting — **align** after import cycle is fully resolved.
- [ ] **`forecast_scoring.py`**: Callers that treated **empty batch score == 1.0** as finite will need to handle **`nan`** — **audit call sites** before using **`scoring_summary`** in production.
- [ ] **`forecast_scoring.py` — `calibration_curve`**: Small **n** yields unreliable curves — **document minimum n** or add **adaptive binning**.
- [ ] **`crps_empirical`**: **O(n²)** complexity **undocumented** — add **docstring warning** before using with large sample sizes.

---

## Deferred — session backlog (logged Apr 3, 2026)

Cross-reference: **`bundle_tasks.py`** items below mirror § **Deferred — `bundle_tasks.py` (bundle runtime & idempotency)** — both are logged.

- [ ] **`bundle_tasks.py`**: Per-scenario **`generate_report`** runs **synchronously**, adding wall-clock time per scenario — consider **async** (or background/chained tasks) when optimising bundle runtime.
- [ ] **`bundle_tasks.py`**: **Worker redelivery** can **regenerate reports** for already-completed scenarios — fix when adding **bundle resume** / idempotency (dedupe by `simulation_id` / `report_id`, skip completed scenarios, checkpointing).
- [ ] **`bundle.py`**: **`load_payloads_from_bundle`** is invoked **outside** the PATCH **`try/except`** — wrap in a **hardening pass** so load errors are handled consistently with the rest of the PATCH flow.
- [ ] **`bundle_synthesis.py`**: **JSONB synthesis size** is not enforced — add a **size check** when large bundles become common.
- [ ] **`BundleSynthesis.vue`**: After **`finally` retry exhaustion** (`saveRetryCount >= SAVE_FINALLY_RETRY_LIMIT`), the user must **manually interact** to persist — consider surfacing a **"Retry"** (or similar) control when the limit is reached and weights are **unsaved**.
- [ ] **`BundleResultsView.vue`**: **Synthesis** in the **comparison** payload can **inflate response size** for large bundles — consider **lazy-loading synthesis** separately (dedicated fetch vs embedding in comparison).
