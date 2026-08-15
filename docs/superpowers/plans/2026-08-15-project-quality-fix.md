# Project quality fix: measurement loop, MC tests, zero-action guard, correlation discount

Date: 2026-08-15 · Branch: main lineage · Status: vetted (adversarial pass applied; both open decisions resolved)

## The problem

Four verified gaps in the live project, in portfolio-impact order:

1. **Measurement loop missing.** The live Supabase project already contains an orphaned calibration model — `case_predictions`, `case_outcomes`, `calibration_runs`, `historical_cases` — referenced by **zero** backend code (verified 2026-08-15: grep across `backend/`). Meanwhile `forecast_scoring.py` is complete and tested but only imported by its test file. The writeup's "no accuracy number" is honest but reflects no data-collection pipeline, not just no resolved outcomes.
2. **Monte Carlo engine untested on the live path.** `quantitative_analysis_service.py:1299-1306` imports `monte_carlo_engine`; CIs flow into `report_payload.py:330-334` and `bundle_synthesis.py:106`. No `test_monte_carlo_engine.py` exists. Unpinned numerics: PERT parameterization fallbacks in `sample_pert`, convergence gate `relative_error < 0.02` (`monte_carlo_engine.py:306`), and the `low >= high` → `None` contract (`monte_carlo_engine.py:363`, filtered downstream at `report_payload.py:326`).
3. **Zero-action runs report success.** The golden tape's simulation stage produced 0 actions (Anthropic key in `OPENAI_API_KEY` slot — 401s); the UI reported a successful run. Root cause is patched in the working tree (`model_factory.py:66-77`), but no guard exists: a future key/config failure will silently complete empty again.
4. **Correlation discount is a magic constant.** `calibration_guardrails.py:198` halves effective sample size with `avg_correlation = 0.5` and no derivation. The matrix path of `apply_evidence_correlation_discount` is untested except the `m < n` fallback (`test_calibration_guardrails.py:104` passes a 1-row matrix).

## Decisions (resolved during vetting)

- **Measurement loop:** integrate the orphaned tables (score-bridge), not a new schema. No migration.
- **Zero-action guard:** `FAILED` status with clear error on natural completion with 0 actions, reusing the existing frontend failure path.

## Phase 0 — Land the working tree clean

| # | Step | Verification |
|---|---|---|
| 0.1 | `ruff check --fix` + mypy on the 10 modified backend files (551 ruff errors at tree state, 494 auto-fixable — mostly pre-existing style: unsorted imports, trailing whitespace) | ruff clean, mypy clean |
| 0.2 | Review full diff; gitleaks check (`.env.demo-record.example` touched — no real keys) | gitleaks clean |
| 0.3 | Full backend suite | 193 passed |
| 0.4 | Commit. Note in message: `docs/schema/supabase_schema.sql` is a partial snapshot (11 of 27 live tables) — not a sync gate | commit lands green |

## Phase 1 — Tests and guardrails

### 1.1 `backend/tests/test_monte_carlo_engine.py`

Identity/numerical tests over the pure functions (no mocks):

| Property | Assertion |
|---|---|
| Seeded determinism | same seed → identical result; different seed → differs |
| Bounds clamping | `sample_from_distribution` with bounds never escapes min/max |
| PERT mean | E[sample] ≈ (low + 4·mode + high)/6 (10k samples, tol 0.01) — derivable from the a1/a2 construction |
| Percentiles/CIs | `_percentile` matches known quantiles of a sorted list; 95% CI of a normal sampler contains ~95% of draws |
| `low >= high` contract | `run_monte_carlo_on_estimates` returns `None` entry; downstream filter (per `report_payload.py:326`) handles it |
| Convergence semantics | pin current behavior (documented gate, not redesign): se/mean < 0.02 → converged; `recommended_iterations` formula |
| Distribution samplers | triangular/beta/uniform/normal edge cases (degenerate low==high, alpha<=0 clamps) |

### 1.2 Zero-action guard

In `simulation_runner.py` at the completion transition (`:636-640`, where `_check_all_platforms_completed` → `RunnerStatus.COMPLETED`):

- Accumulate `total_actions` from each platform's `simulation_end` event (`:627`, `:631` already log it).
- On natural completion: if `total_actions == 0` across **all enabled platforms** → `runner_status = FAILED`, error = `"Simulation completed with zero actions across all platforms — check model/API key configuration."`
- Stopped/killed runs bypass the guard (different status path). A legitimately quiet run (off-peak rounds skipped) is possible — the guard only fires on complete 0, which is a config/key failure signal; a false positive is a recoverable re-run.

Frontend renders the existing FAILED path for free.

### 1.3 Correlation discount (corrected approach)

The discount applies to correlated *evidence likelihood ratios* (effective sample size), NOT MC outcome samples — MC joint samples cannot measure it. Fix:

- Make `avg_correlation` config-driven (`Config.CORRELATION_DEFAULT_AVG_CORRELATION` or similar, default 0.5 preserved).
- Document the rationale and its honest status (heuristic, no derivation) in the module docstring and the config comment.
- Add tests for the real matrix path: proper n×n matrix with mixed correlations, row < n fallback, malformed matrix → uncorrelated fallback.

## Phase 2 — Measurement loop (integrates orphaned schema)

### 2.1 Write predictions

At report completion where `estimate_risks` produced estimates (`quantitative_analysis_service.py:1296-1314`): upsert into `case_predictions` — `case_id` derived from session/project, `dimension` = outcome name, `predicted_score` = MC mean (fallback mid), `rationale` = estimate summary. No schema change.

### 2.2 Resolutions

Manual: record `case_outcomes.actual_score` per dimension (user/analyst judgment; `sources` field for provenance). No automation claim — the honest scope is that someone judges outcomes.

### 2.3 Grading job

Script (or Celery task if it lands on the live path):

- Per-dimension score error (predicted vs actual) → aggregate into `calibration_runs` (`overall_accuracy`, `dimension_accuracies`, `dimension_biases`, `run_date`, `total_cases`).
- Where a resolution is genuinely binary (yes/no), run `forecast_scoring` with `mc_samples_per_forecast` from the MC engine — the module was built for exactly this pairing (`forecast_scoring.py:226`).

### 2.4 Explicitly out of scope

`weight_adjustments` (the original design's feed-back-into-future-predictions step). Deliberate boundary; noted in code/plan, not quietly omitted.

## Phase 3 — Demo believability (gated on the sim-quality plan)

Order is load-bearing — one re-record, not two:

1. Simulation-quality fix **accepted** (see `docs/superpowers/plans/2026-08-15-simulation-quality-fix.md`)
2. Phase 0 landed (key fixes committed)
3. Harness smoke (3-round run, no Zep)
4. Full re-record (DeepSeek, ~45-60 min, $2-6 + Zep)
5. Re-grade (actions, report honesty, quote ratio)
6. Swap tape, replay-verify (zero-origin e2e), redeploy

## Execution order

Phase 0 → Phase 1 (0.1-0.2 parallel-safe) → Phase 2; Phase 3 gates on the sim-quality plan's acceptance, independent of 0-2.

## Acceptance

| # | Criterion |
|---|---|
| A1 | Working tree committed, ruff/mypy clean, 193 backend tests + frontend suite green |
| A2 | `test_monte_carlo_engine.py` present and green (properties in §1.1) |
| A3 | Zero-action completion → `FAILED` with the error string; stopped runs unaffected (tested) |
| A4 | Correlation discount config-driven + documented; matrix-path tests green |
| A5 | A report-completion run writes `case_predictions` rows; grading script produces a `calibration_runs` row from a seeded case_outcome |
| A6 | Demo tape replays a productive simulation (Phase 3) |

## Trade-offs to document

- The correlation default (0.5) remains a heuristic — the fix makes it explicit and pinned, not derived.
- Manual resolutions mean the first accuracy figure lands only after the first judged outcome cohort — "measurements coming" framing, not "measured."
- Zero-action FAILED can false-positive on a genuinely quiet run; recoverable by re-run.
- `case_predictions` stores a score, not a triplet — binary calibration is a derived cohort, not the primary model.
