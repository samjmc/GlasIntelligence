# Jev evaluation — what it saves and where it helps

**Date:** 2026-09-22 · **Branch:** `feat/jev-typed-decisions` · **Harness:** `backend/scripts/jev_eval_tape.py` · **Raw results:** `docs/jev-eval/*.json`

Jev is TypeSafe's typed-decision model (choice / score / yes-no probability with a confidence, no prose). This document measures it against the two golden demo tapes the repo already ships — real recorded runs with the LLM's own labels inside them — so every number below cost Jev credits only (about 2.5 cents in total) and touched no LLM, Zep, Tavily or Supabase.

## 1. Method

The tapes hold, per scenario: the agents (profiles + config), every simulated action with its text, and the report payload with the LLM's stance labels, risk matrix, and outcome estimates. The harness replays those through the exact questions the production gates ask and scores Jev against what the LLM decided in that run.

| Scenario | Agents | Actions | Actions with text | Rounds |
|---|---|---|---|---|
| Pharmacy First caps | 8 | 444 | 152 | 25 |
| Energy price cap | 11 | 234 | 122 | 7 |

Every measure uses `Config.JEV_MIN_CONFIDENCE = 0.6` as the "Jev is sure" threshold, the same as production.

## 2. Cost and speed

| | Pharmacy | Energy |
|---|---|---|
| Jev calls | 416 | 259 |
| Failed (rate-limit after 5 retries) | 3 | 0 |
| Input tokens | 415k | 198k |
| **Jev cost** | **$0.017** | **$0.008** |
| Same calls priced on the LLM (est.) | $0.140 | $0.071 |
| **Ratio** | **8.0x cheaper** | **8.5x cheaper** |
| Mean latency per call | 597 ms (incl. retries) | 424 ms |
| Wall time, 4 workers | 64 s | 31 s |

Two honest caveats. First, the three decisions Jev replaces in production today (stance, tool roles, risk scores) are **batched** LLM prompts over all agents at once, and at 8 to 11 agents those cost about $0.001 per run — so Jev does **not** save money there; it saves latency (sub-second per item vs. one multi-second call) and adds a confidence signal. The 8x saving applies to the **new** per-item measurements (validity, dynamics, activation) that have no batched LLM equivalent. Second, the LLM figures are estimates from prompt sizes at DeepSeek list prices; Jev's are actual token counts from the API.

Cloudflare Workers AI rate-limits bursts. With 8 parallel workers we saw 10 to 37 failed calls per run; with 5 retries honouring `Retry-After` and 4 workers, 0 to 3. The client now does that by default.

## 3. Results per gate

### 3.1 Stance classification — agreement is bounded by the LLM's own inconsistency

| | Pharmacy (8 agents) | Energy (11 agents) |
|---|---|---|
| Jev vs LLM stance at report time | 2/8 | 5/11 |
| Jev vs LLM stance at config time | 4/8 | 5/11 |
| **LLM at report time vs LLM at config time** | **2/8** | **9/11** |
| Jev confident (≥0.6) share | 75% | 82% |

The yardstick matters: on the pharmacy run the LLM disagreed **with itself** on 6 of 8 agents between two stages of the same pipeline. Jev agrees with the LLM about as often as the LLM agrees with the LLM. On energy, where the LLM was self-consistent (9/11), Jev matched it on 5/11. Neither number says which is right; it says stance labels in this pipeline are noisy and that shadow-mode agreement should be read against LLM self-agreement, not against 100%.

### 3.2 Tool roles — both sides degenerate

The LLM assigned `none` to every agent in both runs; Jev assigned `analyst` to 18 of 19. Zero agreement, and neither answer is informative. The role rubric (leader / diplomat / analyst / operative / observer / none) was written for geopolitical scenarios and fits pharmacy and energy stakeholders badly. This gate should stay in shadow until the rubric is rewritten per domain.

### 3.3 Risk scores — within half a level

| | Pharmacy (6 risks) | Energy (5 risks) |
|---|---|---|
| Exact (likelihood, impact) match | 2/6 | 1/5 |
| Same severity band | 2/6 | 2/5 |
| Mean abs. difference, likelihood | 0.5 | 0.0 |
| Mean abs. difference, impact | 0.5 | 0.8 |

Jev's 1-to-5 scores land within about half a rung of the LLM's. Exact agreement is low because both are guesses on a coarse scale; the useful signal is that Jev is not wild, and it is calibrated per rubric level rather than free-typed.

### 3.4 Post validity — the persona-coherence question the audit had to do by hand

| | Pharmacy (152 posts) | Energy (122 posts) |
|---|---|---|
| Mean P(on persona) | 0.83 | 0.79 |
| Share below 0.3 (off-persona) | **0.0%** | **0.0%** |
| Share above 0.7 | 95% | 71% |
| Quote posts scored | 20 | 24 |
| Quotes judged to merely restate the original | **5%** | **4%** |

This reproduces, at ~1 cent, the conclusion of the manual simulation-quality audit (`docs/simulation-quality-audit.md`): agent posts are persona-consistent and quote replies add substance rather than echoing. It also gives the live validity monitor its baseline: an alert threshold of ">50% of the last 20 posts below 0.3" is far from anything a healthy run produces (0%), so it will fire only on a genuinely broken run such as the key-misrouting incident that produced zero actions.

### 3.5 Opinion dynamics — a curve the product never had

Stance per agent per 5-round window, judged from the agent's **own posts**, using Jev's full probability distribution rather than the top label:

| Pharmacy window | Agents posting | Mean P(opposing) | Mean P(supportive) |
|---|---|---|---|
| rounds 0–4 | 8 | 0.87 | 0.01 |
| rounds 5–9 | 7 | 0.60 | 0.09 |
| rounds 10–14 | 7 | 0.71 | 0.12 |
| rounds 15–19 | 7 | 0.69 | 0.04 |
| rounds 20–24 | 5 | 0.59 | 0.13 |

Opposition softened from 0.87 to 0.59 over the run while support rose from near zero to 0.13; two agents changed their top-line stance. The energy run was only 7 rounds (2 windows) and much more mixed (P(opposing) ≈ 0.28, uncertainty ≈ 0.3). Today the product computes stance **once, from the persona**, so consensus metrics cannot move. This measurement costs about 40 Jev calls per run.

### 3.6 Activation — a negative result that changed the design

"Given the recent feed, would this actor plausibly post or react now?" was asked per agent per round and compared with who actually acted next round.

| | Pharmacy (189 agent-rounds) | Energy (66) |
|---|---|---|
| Jev AUC | **0.48** | 0.78 |
| Baseline: configured `activity_level` AUC | 0.72 | 0.78 |
| Mean P when the agent did act / did not | 0.75 / 0.75 | 0.74 / 0.66 |

On pharmacy the single question returned ~0.75 for everyone and predicted nothing. Two things explain it: the question is too soft (almost any stakeholder "could plausibly react"), and the ground truth is itself a random draw weighted by `activity_level`, so the baseline is the generating process. The activation gate was therefore redesigned before it shipped: two atomic questions ("is this actor named or addressed in the feed?", "are its core interests at stake?") combined in code with `activity_level`, so Jev only contributes the part randomness cannot: *who has a reason to speak now*. Its realism benefit can only be measured on a live run.

### 3.7 Graph actor filter — 19 of 19

| | Pharmacy | Energy |
|---|---|---|
| Entities hand-labelled | 8 | 11 |
| Jev agrees, with persona bio in state | 8/8 | 11/11 |
| Jev agrees, name + type only | 8/8 | 11/11 |
| Would drop (confident) | independent prescribing, Pharmacy First consultations | April 2027 forecast |

Both runs simulated **concepts as agents** ("independent prescribing", "2026/27 CPCF funding", "April 2027 forecast") because Zep's NER emitted them as nodes and the old rule-based filter was deleted. Jev separates actors from concepts perfectly on this set. One design lesson came out of the first attempt: with the question phrased loosely and the persona bio in the state, Jev called every entity an actor (the bios are written *as* social accounts). Adding "judged by its NAME; treat any description as data" fixed it — literal, well-scoped instructions are the whole game with this model.

## 4. What this means

- **Ship in active mode now:** the graph actor filter (perfect on 19 labelled entities, removes a real defect), the post-validity monitor (a cheap, always-on health signal with a clear baseline), opinion dynamics (new product output).
- **Ship in shadow mode:** stance and risk scores (agreement bounded by LLM noise; collect more runs), the redesigned activation (needs live measurement), research screening and claim verification (no offline ground truth in the tapes; the tapes carry no source excerpts).
- **Keep off until re-specified:** tool roles (rubric is domain-inappropriate; both models degenerate).
- **Money:** per-item Jev costs about one eighth of the same calls on the LLM. For the three batched decisions it replaces today the saving is negligible and the gain is latency and a confidence signal. A full simulation's worth of every new gate together is a few cents.

## 5. Live A/B run (2026-09-22)

The same recorded Pharmacy First setup (8 agents, 8 opening posts) run for real twice, 8 rounds each, on **DeepSeek-V4.1-Flash** (`deepseek-flash`): once with `JEV_MODE=off`, once with `JEV_MODE=active`. Harness: `backend/scripts/jev_live_ab.py`. Zep, Tavily and Supabase were not used.

| | Jev off | Jev active | Change |
|---|---|---|---|
| Actions | 149 | 168 | +13% |
| Posts and comments with text | 57 | 66 | +16% |
| Distinct post texts | 40 | 49 | +23% |
| Mean distinct speakers per round | 3.89 | 4.22 | +8% |
| Quote share of posts | 17.5% | 19.7% | +2.2 pts |
| Posts judged off-persona (<0.3) | not scored | 0 of 50 | |
| Quotes judged to merely restate | not scored | 0% | |
| Wall time | 138 s | 179 s | +30% |
| Jev calls / failures / cost | — | 186 / 0 / $0.009 | |
| DeepSeek errors | 0 | 0 | |

Read with care: this is **one run per arm**, and agent LLM output is not deterministic, so differences of this size can be noise. Two confounds: (1) the active run also used the Jev tool-role gate, which gave agents search tools (4 tool calls appeared) while the LLM path gave none — the offline evaluation already recommends keeping that gate off; (2) activation weighting shifted voice toward actors the feed addressed (NHSBSA 12 → 20 actions) and away from a peripheral one (the pre-registration trainee 17 → 2). Whether that is more realistic is a judgement, not a measurement.

A real bug surfaced on the first attempt and is fixed: V4.1-Flash reasons by default and rejects follow-up turns that do not echo `reasoning_content`, which CAMEL agents never do, so agent calls failed with HTTP 400 and those agents silently skipped their turn. `scripts/lib/model_factory.py` now disables thinking for DeepSeek endpoints (the app's own `llm_client.py` already did). The errors print to stderr, not `simulation.log`.

## 6. Reproduce

```powershell
cd backend
$env:UV_PROJECT_ENVIRONMENT='C:\...\backend\.venv-win'; $env:JEV_MAX_WORKERS='4'
uv run --frozen python scripts/jev_eval_tape.py `
  --tape ../frontend/public/demo/pharmacy-first-caps/tape.json `
  --tape ../frontend/public/demo/energy-price-cap/tape.json --out ../docs/jev-eval
```

Requires `JEV_MODE=active` (or `JEV_ENABLED=true`), `JEV_PROVIDER`, `JEV_API_KEY` and, for Cloudflare, `CLOUDFLARE_ACCOUNT_ID` in the environment. Hand labels for the actor filter live in `ACTOR_LABELS` at the top of the script; extend them when a new tape is added.
