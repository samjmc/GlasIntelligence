# Golden Run Pre-Flight Verification — swarm plan

Date: 2026-08-14
Status: executing
Branch: `feat/static-demo-hosting` (worktree `-demo`)

## Goal

Verify the entire golden-run pipeline works *before* spending a full paid run,
then commit and push live. The research chain (Claude + Tavily) has never run
live; routing, auth/billing, step-to-step data flow, and the recording stack
have never been exercised together with real keys.

## Order (user-directed)

1. **This verification swarm** → fix waves → green gates
2. Commit everything to GitHub (main)
3. Deploy live (Cloudflare Pages)
4. Golden run (Pharmacy First) → real tape → commit → redeploy

## Verification partitions

| ID | Partition | Type | Wave |
|----|-----------|------|------|
| V1 | Backend baseline: pytest suite, ruff, mypy, app boot | gate | 1 |
| V2 | Frontend baseline: vitest, lint, build | gate | 1 |
| V3 | Claude research chain LIVE (Anthropic + Tavily, real keys, 1 round, tiny scenario) | live | 1 |
| V4 | Router + task flow: chain selection ×3 configs; run_deep_research_task with mocked DB; dossier consumed by grounding_bundle | gate | 1 |
| V5 | Pipeline contract audit (read-only): session → research → graph → simulation → report field/ID flow | audit | 1 |
| V6 | Auth + billing LIVE: admin signup → profile → credits → can-research/can-simulate | live | 1 |
| V7 | Recording stack boot: redis, 3 celery queues, backend with DEMO_RECORD=1 → scratch tape path | live | 1 |
| V8 | Mini end-to-end (live, scratch tape): session → research → graph build → simulation create, verify step-to-step transfer + status transitions in Supabase | live | 2 |
| V9 | Adversary: cross-partition interfaces, ID flow, schema drift, hidden coupling | adversary | 3 |

## Gates (all must pass before fix waves end)

- V1: `pytest` green (pre-existing failures documented, not introduced)
- V2: vitest + lint + `npm run build` green
- V3: dossier dict with non-empty `summary_md`, `key_facts`, `sources`, `verification`; zero exceptions
- V4: router returns the right chain per config; task completes dossier; grounding_bundle accepts shape
- V5: no unhandled mismatches; findings → fixes
- V6: `can_research: true` on the test account
- V7: backend + 3 workers up; `/healthz` 200; DEMO_RECORD writes a tape file
- V8: session research_status transitions pending→processing→completed; graph project/simulation IDs chain correctly
- V9: SOUND or fixes landed + re-verified

## Money

V3 ≈ $0.10–0.50 (1-round chain). V8 ≈ $1–5 (research + graph build, no simulation
run). User-approved; usage explicitly not a concern.

## Secrets

Verifiers never echo key values. `.env` is gitignored. Scratch tapes go to
`/tmp/verify-*`, never `frontend/public/demo/`.

## Artifacts

- Ledger: `.superpowers/swarm/ledger.md`
- Evidence: `.superpowers/swarm/evidence/V{n}-evidence.md`
- Report to user: per-partition PASS/FAIL + findings + money spent
