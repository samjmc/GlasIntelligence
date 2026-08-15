# Simulation quality: fixing quote-dense feeds (identity-bleed investigation)

Date: 2026-08-15 · Branch: main lineage (via /tmp/glas-fix-wt)

## The problem (corrected)

Original hypothesis — "identity bleed": institutional agents speaking first-person
clinical anecdotes — was **disproven** by re-reading the data correctly
(quote rows carry the quoted text in `content` and the agent's own words in
`quote_content`). Quote replies are persona-correct: NHS England rebuts with
official metrics, NCHWA translates anecdotes into data-consistent statements.

**Measured real problem:** 65% of content posts are QUOTE_POSTs (82 quotes of
44 originals on Twitter). The visible text surface repeats a small set of
originals; the 382-action engagement total overstates content diversity. The
feed reads echo-y, and any interview claim of "rich discourse" is weakened by
it. Reddit: same pattern expected (515 actions, largely quotes/likes).

**Baseline (V11 run, twitter):**
- M1 quote ratio: 82/126 = **65%**
- M2 distinct originals: 44 (100% distinct among originals)
- M3 total actions: 783 (twitter 268 + reddit 515)

## Root-cause hypothesis

Action selection is an unguided LLM tool call (`oasis/social_agent/agent.py`
`perform_action_by_llm`): the model sees the feed (`env.to_text_prompt`) and
picks any tool. Quoting-with-commentary is the lowest-effort action that
demonstrates engagement, so it dominates. No action-mix guidance exists in the
agent system prompt (injected in `run_parallel_simulation.py:1504`).

## The fix (one lever)

Add action-mix guidance to the agent system prompt at the single injection
point (run_parallel_simulation.py, where the time label is injected; same for
reddit):

> Prefer creating original posts and replying in your own voice. Quote-with-
> commentary sparingly (at most ~1 in 3 actions). Never post text already in
> the feed; always write new content.

Rationale: a prompt change, not a platform/patch change — survives oasis
upgrades, applies to both platforms via one shared constant.

## Iteration loop (cheap, fast)

Reuse the V11 sim config + profiles; run the simulation standalone from a
SCRATCH COPY (outputs derive from the config's simulation_id — copy config +
profile files to /tmp/sim-iter/ so V11 artifacts stay untouched):

`python scripts/run_parallel_simulation.py --config /tmp/sim-iter/simulation_config.json --no-wait`

Each run ~2–4 min, ~$0.30. The V11 config yields 6 rounds (time_config
total_simulation_hours=6) with graph_memory_update_enabled unset → NO Zep
spend during iteration.

Sequence (vetted 2026-08-15):
0. **Harness smoke** — 3-round run (`--max-rounds 3`) proving config reuse,
   flags, no Zep, correct output dir. Kill if anything's off.
1. **Baseline rerun ×2** — unchanged config, two runs, to measure run-to-run
   noise on M1 before any fix is attributed.
2. **Apply fix** — bake guidance into `_original_system_content` at first
   injection (run_parallel_simulation.py twitter ~1504 + reddit ~1742; both
   re-prepend from it each round, so one edit per platform persists).
3. **Rerun ×2** — compare M1/M2/M3 against the noise band.
4. Max 3 fix iterations (guidance wording), then stop and document.

## Metrics (same defs before/after, per platform AND combined)

| # | Metric | Before (V11) | Target |
|---|---|---|---|
| M1 | quote ratio (quotes / content posts) | 65% | < 45% |
| M2 | distinct originals per content post | 35% | > 50% |
| M3 | total actions per run | (baseline rerun) | ≥ 50% of baseline (don't collapse engagement) |
| M4 | commentary voice spot-check | pass | pass (10 quote replies read; persona-consistent) |

## Acceptance

M1 < 45% AND M3 ≥ 50% of baseline AND M4 pass. Otherwise: stop and document
the trade-off (engagement vs diversity is a dial, not a bug). Default stance:
**prefer realism** — a quieter-but-original feed reads better than an echo-y
one; if M3 collapses below the guard we re-record anyway and document the
trade-off rather than soften the fix.

## Execution order

Harness smoke → baseline ×2 → fix → rerun ×2 → (×3 iterations max) →
accept/reject → re-record → re-grade → swap tape + replay-verify → redeploy →
write docs/simulation-quality-audit.md

## If accepted

1. Re-record the golden run (full pipeline, DeepSeek, ~45–60 min, $2–6 + Zep)
2. Re-grade (actions, report honesty, quote ratio)
3. Compact, swap tape on main, replay-verify, redeploy
4. Write `docs/simulation-quality-audit.md` in the interview narrative format:
   problem (with the corrected-diagnosis story), root cause, change, before/
   after numbers, remaining trade-offs

## Trade-offs to document

- Fewer quotes ⇒ fewer total actions ⇒ report metrics ("382 actions") shrink;
  the demo tape must be re-recorded for the numbers to match the fix
- Prompt guidance may over-suppress (agents post less) — M3 guards this
- One scenario, one model (deepseek-v4-flash) measured; generalization
  unproven
- Engagement inflation vs content diversity is a dial — a residual bias toward
  quotes may be intentional for demo vibrancy
