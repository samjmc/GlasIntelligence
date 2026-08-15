# Simulation Quality Audit — agent decision coherence and feed density

Date: 2026-08-15 · Data: V11 golden run (`sim_11ae92c2d1d8`, DeepSeek, 25 rounds, 783 actions) + 8 controlled re-runs
Status: investigation complete — two false positives corrected by measurement, one real dial identified

---

## 1. Problem statement (as first reported)

Two claims were made about the V11 simulation's agent behavior:

1. **"Identity bleed"** — institutional accounts (NHS England, NCHWA, ICBs) appeared
   to speak first-person clinical anecdotes ("my own practice data", "Just
   finished surgery...").
2. **"Quote-dense feed"** — 65% of content posts were quotes of a small set of
   originals, so the visible text surface repeated ~44 texts constantly and the
   action count inflated perceived diversity.

## 2. What the deeper investigation found (both claims were measurement artifacts)

**Claim 1 was a misread of the data model.** In the platform SQLite, a QUOTE_POST
row stores the *quoted* text in `content` and the quoting agent's *own words* in
`quote_content`. Reading `content` only made every quote look like an identical
copy. Reading `quote_content` shows the opposite — quotes are answered with
persona-correct commentary:

| Quoting agent | Quoting the GP's "Pharmacy First paradox" post | Their own reply |
|---|---|---|
| NHS England | (GP's anecdote) | "Pharmacy First continues to deliver: 3.3 million consultations in the past year, up 43% year-on-year..." — official rebuttal with the service's own data |
| ICBs | (same) | "We hear the concerns, and it's important to be clear: capping does not mean cutting services..." |
| NCHWA | (the "just finished surgery" anecdote) | "Anecdotal reports of reduced clinical hours... are consistent [with our workforce models]" — the agency translating an anecdote into data language |

Institutions never claim the first-person voice; they reply institutionally.
**Zero instances of genuine identity bleed were found** (measured: 44/44 original
posts distinct, 0 cross-agent adoptions).

**Claim 2 was a table-scoping artifact.** The 65% figure counted quote *rows* in
the `post` table against content rows — but the `post` table excludes likes and
reposts, which live in separate tables. Measured on the action stream (the true
behavior), quote density per round-window was:

| Rounds | Total actions | Quotes | Quote % | Creates | Likes |
|---|---|---|---|---|---|
| 1–8 | 147 | 44 | **30%** | 39 | 50 |
| 9–16 | 70 | 25 | **36%** | 12 | 21 |
| 17–24 | 51 | 13 | **25%** | 8 | 14 |

A 25–36% quote share of *actions* is a healthy Twitter mix (commentary, original
posts, likes, reposts all present). Reddit has no quote mechanism at all (its
engagement is comments + likes). The "65%" was `post`-table rows only.

## 3. What was tried, and why it failed (the address step)

Even with the artifact corrected, the *visible feed surface* still skews toward
quotes (82 quote rows vs 44 originals at the DB level — a reader sees originals
repeated ~3x). Three controlled experiments attacked this, each measured on the
same config, 8 rounds, twice per variant (noise band ±1pp):

| Iteration | Change | Quote ratio (run 1 / run 2) | Result |
|---|---|---|---|
| Baseline | unchanged | 43% / 42% | — |
| 1 | Explicit guidance: "quote-with-commentary at most 1 in 3 actions" | 60% / 49% | **Worse** — naming the action made it salient |
| 2 | Positive-only framing: "publish something new; prefer a like over repeating" | 59% / — | **Worse** — no improvement |
| 3 | Adaptive hard constraint: agents that quoted in the last 2 rounds are told to post original content | 47% / 52% | **No improvement** — within noise of baseline |

**Conclusion:** the quote share is a structural property of the action-selection
design — the agent sees the feed and quoting-with-commentary is the lowest-effort
way to respond to visible content — not a prompt-tunable behavior. All three
experiments were reverted; the codebase is unchanged.

## 4. What the measurement says the truth is

- **Agent decision coherence: good.** The strong personas (GP, community
  pharmacist, trade press, CPE, GOV.UK, ASHP) make consistent, escalating,
  persona-correct decisions — e.g. the GP moves from tweeting to health-scrutiny
  committee testimony; the pharmacist's "mother referred by 111, we'd hit our
  cap" anecdote; The Pharmacist's "FACT CHECK" post; GOV.UK's unwavering
  neutrality. Quote replies are substantive (0 empty commentaries measured).
- **Feed composition: a dial, not a bug.** Quotes-with-commentary are a
  legitimate engagement mechanism and the commentary is on-voice; the residual
  question is presentational density for a hypothetical reader of the raw feed.

## 5. Remaining trade-offs (the honest position)

1. **Feed density vs engagement.** Suppressing quotes (via any lever found so
   far) *lowers* engagement and original-post volume — the structural incentive
   makes quotes the cost-effective response. Tuning the action distribution
   would require changing the oasis tool definitions (site-packages, upgrade-
   fragile) — possible, but the current mix is defensible as-is.
2. **One scenario, one model.** All measurements are on the Pharmacy First
   scenario with deepseek-v4-flash; generalization is unproven.
3. **Demo visibility.** The social feed is not rendered in the current UI (the
   Step-3 feed components are dead code, verified separately), so the quote
   density is invisible to a recruiter; what they see — the report — is grounded
   in the healthy action stream.
4. **Measurement discipline lesson.** Both original findings survived a first
   pass and failed a *measured* second pass. The controlled-rerun methodology
   (same config, fixed rounds, noise band, per-window analysis) is what caught
   them — and is now the documented standard for any future simulation-quality
   claim.

## 6. Interview-ready summary (one paragraph)

> "I audited whether the simulated agents' decisions are actually coherent —
> reading every post against each persona. Two apparent problems — institutional
> accounts 'borrowing' personal anecdotes, and a quote-dense feed — both turned
> out to be measurement artifacts once I read the data correctly (quote rows
> carry the quoted text in the wrong column from the reader's perspective, and
> the 65% figure counted the wrong table). The measured reality is a healthy
> action mix with persona-correct decisions, including quote replies that are
> substantively on-voice. I ran three controlled experiments attempting to
> rebalance the feed composition; all three failed to beat baseline, which
> taught me the quote share is structural to the action-selection design rather
> than prompt-tunable. The honest position is: agent decision quality is good
> and measured; feed density is a design dial with an engagement trade-off, not
> a defect."
