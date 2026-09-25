# Plan: trustworthy Jev evidence, cheaper runs, and independence from Zep credits

**Date:** 2026-09-22 · **Owner:** this session · **Status:** proposed, **vetted 2026-09-22 (verdict: needs rework → reworked below)**

## Vet results (2026-09-22) — these override anything below that conflicts

**Phase 0 is done:** PR #9, 837527d.

**Blocker — repeats must be separate processes (Phase 1.2).** `jev_live_ab.py:169-175` evicts `app.*` and the runner modules, but `scripts/lib/db_utils.py:11` keeps a reference to the OLD `ToolCallLogger` class. So from run 2 onward `fetch_new_tool_calls` reads run 1's logger, and `TOOL_*` actions silently vanish from the feed and every metric. `builtins.open` is also re-wrapped on every re-import (`run_parallel_simulation.py:51-65`), and `action_logger.py:151` drops log handlers without closing them. **Fix:** give every repeat a fresh process (`jev_live_ab.py --only <mode> --out <dir_i>`) and its own directory, driven by a small orchestrator.

**High — exact cost per run cannot come from the balance.** Verified 2026-09-22: DeepSeek's `total_balance` is a string with **2 decimal places**, so a few-cent run reads $0.00–0.01. **Fix:** sum `usage` tokens from each LLM response — CAMEL returns usage per step; otherwise use a thin OpenAI-client wrapper in `model_factory` — and use the balance only as a whole-batch cross-check.

**High — seeds don't pair the runs.** `platform_runners.py:274-277, 526-529` never pass `rng`. OASIS (`recsys.py:163,413,646,749`) and openai's retry jitter share the global `random`. **Fix:** treat runs as independent samples (the permutation test is right for that), pass each platform its own `random.Random(seed)`, and do the "≥90% same decisions" equivalence check offline only.

**High — `JEV_DISABLED_SITES=tool_roles` does not equalise the arms.** Every tape agent has `tool_role: "none"` with `enable_agent_tools: true`, so `assign_tool_roles` runs on its LLM path. That path uses a raw OpenAI client **without** the DeepSeek thinking-off fix (`simulation_tools.py:578-584`, `max_tokens=1000`), so it returns an empty reply and gives `{}` (`:588-591`, `:606-608`). That is also a **production bug**: tool roles never get assigned on V4.1. Scenario tools also re-roll each run (temperature 0.7, `:334-340`), and `effect_targets` still runs through Jev in the active arm.
**Fix:** for the A/B, set `cfg["enable_agent_tools"] = False` in `build_sim_dir`. That also removes the tool-logger leak's effect. Separately, fix the thinking-off gap in `simulation_tools.py`'s two raw OpenAI calls.

**High — validity is scored in the active arm only.** Off mode never builds a Jev client (`jev_client.py:149`). **Fix:** after each run, score both arms' `actions.jsonl` with the same `ValidityMonitor` questions.

**Medium — metrics.** The key `round` is correct (`action_logger.py:55`). But round 0 (the 8 identical opening posts, `platform_runners.py:212-219`) dilutes every difference, and the two platforms share round numbers. **Fix:** exclude round 0 and report each platform separately. For stderr error counting, don't swap `sys.stderr`, because handlers capture the old stream (`logger.py:80`). Pipe the subprocess stderr or attach a counting `logging.Handler`.

**High — Phase 2 assumptions.**
- **Today's cost:** one Jev request per eligible agent per round per platform (2 yes/no questions each), on up to 8 threads. It blocks the async round loop (`platform_runners.py:274`), and the validity scoring after every round blocks it too (`:318`). With N = 8, all requests already go out as one parallel wave. So batching cuts request count, not necessarily wall time, and the ledger's summed `jev_latency_ms` is not wall time.
- **Before claiming a speed-up:** time each site, and state acceptance "per platform per round".
- **Batching** needs a new request builder and a way to map answers back to agents. The existing question is named `interest_at_stake`. One failed request now sends ~10 agents to baseline, not one. Tests that break: `test_jev_simulation.py:193-197, 212-216, 290-293`.
- **Voice floor:** the weights sum to exactly 1.0 (`jev_simulation_gates.py:46-48`), so Jev can only ever LOWER an agent's activation below `activity_level`. That is the root cause of quiet agents being silenced. A 0.5× floor overrides `ACTIVATION_P_FLOOR` whenever activity > 0.1. Shadow agreement tests p ≥ 0.5 (`:196`), which is impossible for agents with activity < 0.5 (the trainee has 0.2). `rng.sample` caps the round size, so a floor guarantees no share. Tests that break: `:209, :211, :241-242`. **Better fix:** rescale so Jev can raise as well as lower. For example, p = activity_level × (0.5 + 1.0 × signal), clamped. Then compare evenness (Gini) against the off arm.

**High — Phase 3.** `jev_eval_tape.py` has no labels argument, and `ACTOR_LABELS` is hard-coded (19 entries). Its `measure_activation` tests the OLD single "would_act" question, and its `measure_validity` uses different prompts from the live monitor. **Fix:** add `--labels`, import the question builders from `jev_simulation_gates.py` so offline and live evaluation ask the same thing, and bin reliability on confidence = max(p, 1−p).

**High — Phase 4.0 facts were wrong.**
- The real build uses the project's **300/30 character** chunks (`project.py:49-50`, `api/graph.py:444-445`). The frontend sends only `project_id` (`MainView.vue:281`). So builds are ~110–150+ **1-credit** episodes; the "2 credits per chunk, 30% waste" claim is wrong.
- The splitter (`utils/file_parser.split_text_into_chunks`) counts characters and backs off to sentence breaks, so a ≤700-byte target needs a byte-aware splitter. The saving is ~20–25% against 300-char chunks.
- Live memory sends 5 actions per episode, so "≥1 credit per action" overstates it.
- **Ledger write sites** (and every retry attempt): `graph_builder.py:311`, `graph_enrichment_service.py:307, 455`, `zep_graph_memory_updater.py:409` (inside a retry loop at `:407`). The ledger file needs a lock, because it is written from Flask threads and possibly Celery.
- **4.0 gets a new step 1: turn live graph memory off by default.** `Step3Simulation.vue:409` hard-codes it ON, which is a live credit drain.
- 4.0 is gated on PR #11: the vet found it rewrites `graph_builder.py`, `graph_enrichment_service.py` and `zep_graph_memory_updater.py`. The "none are owned by parallel sessions" claim below is wrong.
- The top-5 type cap must keep `Person` + `Organization`; see the migration plan's vet section.

**High — Phase 5.** `tavily_client.search` keeps only `title`, `url` and `content` (`tavily_client.py:18, 34-41`), dropping `published_date`. `outcome_resolution.py:74-79` filters on a `published` key that never exists, so that filter is a silent no-op today. **Fix:** map `published_date` to `published` in the client.
Research has no cutoff parameter at all. Two other paths also leak post-cutoff news, with no date filter possible: the agents' DuckDuckGo tools (`simulation_tools.py:147-228`) and `deep_research_agent.py:119` `web_search_preview`. **So a leak-free backtest must also disable agent web tools and deep research for backtest runs.**
`services/entity_expansion.py` no longer exists; the comment at `config.py:310` is stale.

**Medium — lint.** PR #11 ignores `**/jev_*.py` in ruff as "owned by a parallel branch". That branch is this plan. Phase 2 must make `jev_simulation_gates.py` lint-clean and remove the ignore.

Parallel sessions already running (do not touch their files): CI + dev-env health, offline agent interviews (`simulation_interview_env_routes.py`, `simulation_ipc.py`, `Step5Interaction.vue`, the `interview_agents` path in `zep_tools.py`), opinion-over-time chart (new `opinion_dynamics.py`, report payload assembly, `Step4Report.vue`).

## Constraint that shapes everything: Zep credits

The Zep account is on the free plan. Every graph build sends about one episode per 500-character chunk of the dossier (about 60–80 for a typical 30–40k-character dossier), plus up to 3 enrichment rounds and one `add_nodes` call. Live graph memory during a simulation would add many more, but it is off by default. **Rule for every phase below: no step may call Zep unless the phase says so, and each such step states its episode cost first.** Phases 1–3 cost zero Zep credits.

## Phase 0 — Land the pending local work (blocking)

Uncommitted on local `main`: the DeepSeek-V4.1 thinking-mode fix (`scripts/lib/model_factory.py` + `tests/test_model_factory_deepseek.py`), `scripts/jev_live_ab.py`, the live section of `docs/jev-evaluation.md`, `.env.example` (`deepseek-flash`), and this plan. The interview and opinion-chart sessions reference `jev_live_ab.py` on `main`, and without the model fix any agent run on V4.1 loses turns to HTTP 400s.

- Commit on a branch, PR to `main`, merge. **Needs Sam's go-ahead** (repo rule: commit only when asked).
- Verify: `git show origin/main:backend/scripts/jev_live_ab.py` exists, and the model-factory tests pass.

## Phase 1 — Measurement you can trust (zero Zep)

**1.1 Exact LLM cost per run.** Read the DeepSeek account balance before and after each run and record the difference in `ab_summary.json`, next to the Jev ledger. Verified 2026-09-22: `GET https://api.deepseek.com/user/balance` returns `balance_infos[].total_balance` in USD. Use `total_balance` rather than `topped_up_balance`, because granted credit is spent first. Runs are sequential, so the difference belongs to that run. Also record agent-call failures by capturing stderr and counting `BadRequestError`, `RateLimitError` and `APIError`, since these never reach `simulation.log`.
Verify: two back-to-back 1-round runs produce plausible, non-zero, similar costs.

**1.2 Multi-seed A/B, one variable at a time.** Extend `jev_live_ab.py` with `--repeats N`, and pin `JEV_DISABLED_SITES=tool_roles` in BOTH arms, so that only activation and the validity monitor differ (tool roles confounded the first live run).
Arms: `off` ×5 and `active` ×5, 8 rounds each, pharmacy tape. Run them interleaved, off/active/off/active, so a provider slowdown hits both arms.
Metrics per run: actions, posts with text, distinct texts, quote share, speakers per round, **voice evenness** (Gini coefficient of actions across agents), the smallest agent's share of actions, validity on-persona mean, wall time, DeepSeek cost, Jev cost.
Report the mean ± standard deviation per arm, and call a difference real only if a permutation test gives p < 0.05. With 5 runs per arm this is still a small sample, so the write-up must say so.
Estimated cost: ~10 runs × (DeepSeek measured in 1.1, expected well under $0.20 each) + Jev ~$0.01 each.
Verify: `docs/jev-evaluation.md` gains a table with spreads, and the run logs show zero `BadRequestError`s.

## Phase 2 — Make the activation gate fast and fair (zero Zep)

**2.1 Batch the activation questions.** Today activation makes one Jev call per agent per round, which made the live run ~30% slower. Every agent reads the same feed, so ask once per round: state = `{recent_feed, actors: [...]}`, with two questions per agent, `addressed__<i>` ("Is <name> named, quoted, replied to or addressed in the recent feed?") and `interest__<i>`. Chunk into groups of about 10 agents per request so the state stays small; accuracy drops as irrelevant context grows. The weight formula in code stays unchanged.
- Before switching: probe the per-request question limit with a 20- and a 40-question request.
- Equivalence check offline on the pharmacy tape: batched and per-agent probabilities must agree (Pearson ≥ 0.9 for both questions), and the activation decisions for a fixed seed must match on ≥ 90% of agent-rounds.
- Files: `app/services/jev_simulation_gates.py`, `scripts/lib/time_utils.py`, and its tests.
- Acceptance: Jev's added wall time is ≤ 10% of an 8-round run, and Jev calls per round drop from about N to ceil(N/10).

**2.2 A voice floor.** In the first live run the pre-registration trainee fell from 17 actions to 2. Add a floor: an agent's activation probability never drops below `ACTIVATION_FLOOR_FACTOR` (default 0.5) × its baseline `activity_level` probability.
Acceptance, from the 1.2 re-run: the active arm's Gini is not worse than the off arm's, and no agent's share falls below half of its off-arm share.

## Phase 3 — Ground truth instead of LLM agreement (zero Zep)

Agreement with the LLM is not accuracy; on the pharmacy run the LLM agreed with itself on only 2 of 8 stances.

**3.1 Build a labelled set** under `docs/jev-eval/labels/`, pre-labelled by me and reviewed by Sam in a small shared page:
- 60 real posts (from both tapes and the Phase 1 runs): on-persona yes/no, and for quotes, "adds new content" yes/no;
- all 19 agents: stance, from their own posts;
- 30 dossier-style claims paired with a source passage: supports / contradicts / says nothing;
- the 19 actor-filter labels that already exist.

**3.2 Score accuracy.** Extend `jev_eval_tape.py` to report each gate's accuracy, precision and recall against the labels, plus a **reliability table**: accuracy per confidence bin (0.6–0.7, 0.7–0.8, 0.8–0.9, 0.9–1.0). This checks the calibration claim that nobody has published.
Acceptance: every gate in `docs/jev-evaluation.md` has an accuracy number and a go / shadow / off decision justified by it.

## Phase 4 — Stop Zep eating the monthly credits

**Facts** (from [getzep.com/pricing](https://www.getzep.com/pricing), 2026-09-22):
- The free plan gives 10,000 credits per month, with no rollover and no top-ups.
- Credits are charged per episode: 1 credit per 350 bytes or part of 350 bytes.
- Only 5 custom entity or edge types are allowed.
- Past the quota, the account drops to a 5 requests-per-minute penalty with HTTP 429s. There is no paid overage.
- The next tier, Flex, costs $125 a month for 50,000 credits.

What this means for the app:
- A 500-character chunk costs **2 credits** but uses only about 1.4 credits' worth of bytes. About 30% of every build is rounding waste.
- A 30k-character dossier costs about 135 credits, so the monthly quota covers about 70 builds.
- **Live graph memory is the real drain.** Each agent action is at least 1 credit, so 50 agents × 40 rounds is at least 2,000 credits for one simulation.
- **The ontology is over the free limit by design.** `ontology_generator.py` asks for exactly 10 entity types (`MAX_ENTITY_TYPES = 10`) and up to 10 edge types, and `graph_builder.set_ontology` sends them all. The free plan allows 5. How Zep responds is unverified: it might reject the request, truncate the list, or fall back to generic types. Any of these would quietly change which stakeholders exist, which is exactly the "concepts simulated as agents" defect the evaluation found. Check this in 4.0.

**4.0 Guard the credits now (small, no behaviour change beyond refusing to overspend).**
- Put a `ZepCreditLedger` in `utils/`. Every Zep write (`graph.add`, `add_batch`, `add_nodes`) records `ceil(bytes/350)` per episode into a month-keyed JSON file under `uploads/`.
- `ZEP_MONTHLY_CREDIT_BUDGET` defaults to 9,000, keeping 1,000 in reserve. A write that would cross the budget raises a clear error before calling Zep, instead of landing in the 429 penalty mode.
- Log the credits after every build: "used N, month total M of 10,000".
- Chunk to credit boundaries: make `chunk_size` the largest value whose UTF-8 byte length stays at or under 700 bytes (2 credits), with the same overlap. That cuts build credits by about 25–30% for the same text. Check extraction on one dossier: node count must not drop more than 10%.
- Live graph memory stays off by default. If it is enabled, first estimate credits as agents × rounds × platforms and refuse if the budget cannot cover it.
- Ontology vs the plan's type limit: add `ZEP_MAX_CUSTOM_TYPES` (default 5, the free-plan limit), and keep the entity and edge types sent to Zep within it. The generator should still rank all 10; only the top 5 are sent, and the rest are logged. Then learn what Zep actually does with more than 5 by reading the SDK and docs, not by spending credits. If the answer is still unclear, it costs one `set_ontology` call on a throwaway graph, which uses no episodes. This also becomes a Graphiti advantage, since Graphiti has no type limit.
- Tests with a fake Zep client, so zero credits are spent.
- Files: new `utils/zep_credit_ledger.py`, plus call sites in `graph_builder.py`, `graph_enrichment_service.py` and `zep_graph_memory_updater.py`. *(Vet: all three ARE rewritten by PR #11, so wait for it to merge.)*

**4.1 One graph interface (no behaviour change).** A `GraphStore` protocol covering the operations the app actually uses:
- `create`, `set_ontology`, `add_text_batch`, `wait_for_episodes`, `add_nodes`, `delete`
- `list_nodes`, `list_edges` (cursor paging), `get_node`, `get_node_edges`
- `search(query, scope=edges|nodes, limit)`, `add_memory`

`ZepGraphStore` wraps today's 16 call sites in 8 files, and a `FakeGraphStore` serves tests. Callers switch to the interface one file at a time, and the suite stays green after each.
**Sequencing:** `zep_tools.py` is shared with the offline-interviews session. Change only its `search` / `node.get` call sites, never `interview_agents`, and rebase after that PR merges.

**4.1–4.4 are detailed, with the Graphiti API verified against source, in [`2026-09-22-zep-to-graphiti-migration.md`](2026-09-22-zep-to-graphiti-migration.md) (phases G0–G5).** That plan supersedes two claims below: graphiti-core has **no** local sentence-transformers embedder (we write a ~40-line one), and DeepSeek must run Graphiti in `json_object` mode, not `json_schema`. It also adds a go/no-go spike (G0) before any build-out.

**4.2 Graphiti backend (the recommended alternative).** `GraphitiGraphStore` uses `graphiti-core` (pin one version, currently 0.30.x) on **local Neo4j Community 5.26+**, which runs natively on Windows without Docker.
- Extraction runs on DeepSeek-V4.1-Flash through `OpenAIGenericClient` with a `base_url`.
- Embeddings come from local `sentence-transformers`, because DeepSeek has no embeddings API; this also means no OpenAI key.
- Reranking uses a local BGE reranker.
- The ontology maps to Graphiti's Pydantic `entity_types` / `edge_types` / `edge_type_map`. The first build uses `add_episode_bulk`; simulation write-back uses batched `add_episode`.
- Use ~2,000-character chunks, since tokens, not bytes, now drive cost. Estimated **$0.15–0.40 per build** in DeepSeek tokens; measure it.
- Silent-failure guards after every build: node and edge counts must be > 0 and grow with episodes, check the embedding dimension at startup, and cap the semaphore (start at 5, not 20).
- Selected by `GRAPH_BACKEND=zep|graphiti`, defaulting to `zep` until 4.3 passes.

**4.3 Head-to-head on one dossier (costs ONE Zep build, about 100–135 credits, about 1% of the month).** Build the pharmacy dossier on both backends and compare:
- node count and edge count;
- the share of nodes that are real actors, using the Jev actor filter (19/19 on hand labels);
- whether the Step-2 persona generator finds grounding facts for every agent (search hit rate);
- whether a simulation plus report runs end to end.

Acceptance: actor count within 20% of Zep, with no fewer real stakeholders; search returns at least one relevant fact for at least 90% of agents; and a full run makes **zero Zep calls** with `GRAPH_BACKEND=graphiti`.

**4.4 Switch the default** to `graphiti` for development, and keep Zep available as an option. Other options reviewed and rejected:
- Mem0: graph memory needs the $249 Pro tier.
- LightRAG and GraphRAG: no typed ontology, and GraphRAG is batch-only.
- Cognee and LlamaIndex: bigger rewrites.
- FalkorDB-lite: needs WSL on Windows.
- Kuzu: deprecated.
- Neo4j AuraDB Free: fine for later shared hosting, but it pauses after 3 days idle.

## Phase 5 — Live checks that need the graph (Zep or its replacement)

Deferred until Phase 4 decides the graph backend, so they don't burn Zep credits:
- **5.1 Research and report gates live, in shadow mode.** Research screening, claim verification and angle routing need only Tavily and can run earlier if a Tavily key is added. The report gates need a full report, which needs a graph.
- **5.2 Forecast backtest.** For 10 resolved past policy events, run the pipeline as of a cut-off date, let `calibration_ledger.py resolve` settle outcomes, and grade. Fix the leakage first. `utils/tavily_client.py` has only `search(query, max_results)` today. Add the verified Tavily parameters `start_date` / `end_date` (YYYY-MM-DD), `filter_by_published_date: true`, and `include_published_date: true`. Research gets `end_date = cutoff`; resolution gets `start_date = cutoff`. Keep `published_date` on the returned results. Otherwise the dossier and the resolver can see the outcome and inflate the score.

## Order and parallel safety

| Phase | Zep cost | Depends on | Files (all outside the parallel sessions' files) |
|---|---|---|---|
| 0 | 0 | Sam's OK | the pending files listed above |
| 1 | 0 | 0 | `scripts/jev_live_ab.py` |
| 2 | 0 | 1 (for the re-measure) | `jev_simulation_gates.py`, `scripts/lib/time_utils.py`, tests |
| 3 | 0 | none | `scripts/jev_eval_tape.py`, `docs/jev-eval/labels/` |
| 4.0 | 0 | none | `utils/zep_credit_ledger.py`, `graph_builder.py`, `graph_enrichment_service.py`, `zep_graph_memory_updater.py` |
| 4.1 | 0 | interviews PR merged (shares `zep_tools.py`) | new `services/graph_store/`, Zep call sites |
| 4.2 | 0 Zep; DeepSeek for extraction | 4.1; Neo4j installed locally | `services/graph_store/graphiti_store.py`, `pyproject.toml` (after the CI session's lockfile fix merges) |
| 4.3 | **one build, about 100–135 credits** | 4.2; Sam's OK to spend them | docs |
| 5 | 0 on Graphiti | 4.3 | `utils/tavily_client.py`, `outcome_resolution.py`, docs |

Phases 1, 3 and 4.0 can run in parallel now. Phase 2 is measured with the Phase 1 harness. Phase 4.2 adds a dependency, so it waits for the CI session's lockfile regeneration to avoid a lockfile merge conflict.

**Sam needs to provide, when those steps come up:**
- the go-ahead for Phase 0;
- a Neo4j Community install (or permission for me to install it) for 4.2;
- approval to spend about 135 Zep credits on the single comparison build in 4.3;
- a Tavily key for 5.1.
