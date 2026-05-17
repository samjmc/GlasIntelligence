# Review Loop

Iterative code review skill that runs deep review passes (security, logic bugs, implementation gaps, second-order effects, loose ends, AI-slop / code bloat), fixes findings in severity order, self-reviews the fixes for regressions and bloat, and repeats until the codebase is clean and minimal.

Use this skill whenever the user asks for a code review, security audit, bug hunt, slop audit, or "review and fix" pass on a project — especially phrases like "review the project", "do a review pass", "find bugs and fix them", "security review", "audit the codebase", "clean up the AI slop", or "review loop". Also trigger when the user says things like "keep reviewing until clean" or "do another pass". This skill handles the full loop autonomously — the user does not need to ask for each individual pass.

---

You are running an iterative code review loop. Your job is to find real problems, fix them with the *minimal correct change*, verify your fixes haven't introduced new bugs or bloat, and keep going until the codebase is clean.


```
orient → review → present findings → fix → self-review → repeat
```



Stop when a full review pass returns no findings above LOW severity **and** Phase 4 self-review confirms no new bloat was introduced.

A guiding principle from current practice (DHH, Pragmatic Engineer 2026; Simon Willison's vibe-coding bar): **prefer deletion over addition**. The best fixes shrink the codebase. If your fix added more lines than it removed, ask whether you could have deleted instead.

---

## Phase 0 — Orient

Document as **Phase 0: Orient** in your process log.

1. Read `CLAUDE.md` if it exists
2. Run `git status` and `git log --oneline -10`
3. Glob for structural files (`middleware.ts`, `lib/auth/`, `app/api/`, backend dirs)
4. Note the stack — it shapes where vulnerabilities live
5. **Flag oversized files for later passes** — see Size Heuristics reference below. Note any file >500 lines or that looks like it has multiple unrelated concerns. You don't have to fix them this pass; flag them in **Remaining surface**.

Keep a running note of:
- **Covered areas** — files/modules you've reviewed in depth this pass
- **Fixed findings** — what you've patched so you don't re-raise them
- **Remaining surface** — areas you know exist but haven't reached yet

---

## Phase 1 — Review

Systematically read through the Coverage Map (bottom of file). For each file you read, actively look for all SIX finding categories:

### Finding categories

**Security** — auth bypasses, missing authorization, injection (SQL/command/template), exposed secrets, IDOR, JWT/token mishandling, CORS, unsafe redirects, stored XSS, header injection

**Logic bugs** — wrong conditionals, faulty data flow, race conditions, broken error handling, off-by-one, state bugs

**Implementation gaps** — TODOs/FIXMEs in production paths, stubs, partially wired features, missing error paths, hardcoded values that should be config

**Second-order effects** — a change here breaks an assumption there (API contracts, caching, DB schemas, shared state)

**Loose ends** — dead code, orphaned routes, commented-out blocks, deprecated functions still callable, endpoints returning success without doing anything

**Code bloat / AI slop** — defensive code for impossible conditions, wrapper functions that add nothing, semantic duplication of existing helpers, convention drift, comments that just narrate code. **Before flagging this category, consult the Slop Patterns reference** at the bottom of this file.

### Required output format for every finding


```
### [SEVERITY: CRITICAL/HIGH/MEDIUM/LOW] Title
**File:** path/to/file.ts:line
**Issue:** What the problem is
**Impact:** What could go wrong
**Fix:** Specific recommended fix
```



Group findings under category headers (`## Security`, `## Logic Bugs`, etc.).

**Why this format is load-bearing:** subsequent passes use simple text search to find each finding's severity, file, and title. `FINDING-1 — Dead guard (Bug)` is invisible to that search. `### [SEVERITY: HIGH] Dead guard in sites/select` is one regex.

**Before presenting:** verify every finding starts with `### [SEVERITY: ` and contains explicit `**File:**`, `**Issue:**`, `**Impact:**`, `**Fix:**` lines. Rewrite any that don't.

---

## Phase 2 — Present findings


```
## Pass N findings — X total
**CRITICAL (N):** [titles]
**HIGH (N):** [titles]
**MEDIUM (N):** [titles]
**LOW (N):** [titles]
```



Then the full detail grouped by category.

---

## Phase 3 — Fix

Work CRITICAL → HIGH → MEDIUM → LOW.

- **CRITICAL/HIGH:** Fix without asking. Read the file first.
- **MEDIUM:** Fix unless the user said skip. If risky (public API change), ask first.
- **LOW:** Present the list and ask before fixing.

### The minimal-fix principle

The best fix is the smallest one that addresses the root cause. Before writing any new code, ask:

1. **Can I delete instead of add?** A bug fixed by deleting code is the strongest kind of fix.
2. **Does the existing codebase already have what I need?** Search before creating a new helper, util, or pattern (this is the #1 source of AI slop — semantic duplication).
3. **Am I adding defensive code the types/upstream already guarantee?** If yes, don't.
4. **Will I add a comment that just narrates the code?** If yes, don't.
5. **Am I introducing a new convention that the rest of the repo doesn't use?** If yes, match the existing convention.

### Fix quality checklist

- Read the file before editing
- Address root cause, not symptom
- Doesn't break callers, imports, or DB queries
- No new hardcoded values that should be config
- For auth fixes: gate applies to ALL methods (GET, POST, etc.), not just one
- Lines deleted ≥ lines added, when possible
- No new convention drift (match existing logging/error/DB patterns in the repo)

---

## Phase 4 — Self-review

Re-read every file you changed. For each, ask:

1. **New bugs** — did the fix introduce a logic error, broken import, new edge case?
2. **Regressions** — did changing this file break an assumption elsewhere?
3. **Consistency** — does the fix follow the same patterns as the rest of the codebase? (logging, error handling, auth-gate level, DB access style)
4. **Loose ends** — stubs, TODOs, unused imports left behind?
5. **Bloat audit** — did the fix introduce any of: defensive code for impossible cases, wrapper functions adding nothing, narrating comments, duplicate logic that already exists, convention drift? (consult Slop Patterns reference below if unsure)
6. **Net size** — did this fix shrink, stay flat, or grow the file? If grew, was it strictly necessary?

Fix anything found. Report as **Phase 4: Self-review**.

---

## Phase 5 — Decide whether to loop


```
Pass N complete. Fixed X findings (Y critical/high, Z medium, W low).
Net code change: +A lines / −B lines.
Remaining surface: [what hasn't been reviewed yet].
```


Then:
- **CRITICAL or HIGH found:** Always do another pass. Start immediately.
- **Only MEDIUM/LOW, all fixed:** Ask: "Want another pass to go deeper, or are we done?"
- **Nothing above LOW:** Tell the user the codebase is clean at this level.

For each subsequent pass, explicitly tell yourself what was already fixed and which areas were covered, so you move to new territory.

---

## Coverage Map

Work top to bottom across passes. Each pass covers new rows.

| Area | Priority |
|------|----------|
| API route auth gates | Very high |
| Middleware | Very high |
| Auth/session layer | Very high |
| Python / backend handlers | High |
| DB query construction | High |
| Admin/staff endpoints | High |
| CI/CD workflows | Medium |
| Frontend XSS surface | Medium |
| DB schema constraints | Medium |
| Shared utility libraries | Medium |
| Code bloat / slop sweep | Medium (run on files >300 lines first) |
| Dead code / stubs | Lower |

---

## Reference: Slop Patterns

Load when reviewing files for the **Code bloat / AI slop** finding category.

### The 5 strongest signals — flag these first

1. **Shallow module** — interface complexity is roughly equal to or larger than the body. One-line wrapper functions, pass-through classes, files with more exports than logic.
2. **Comment density exceeds the file's norm** — comments that narrate code rather than explain *why*.
3. **Defensive code where types/upstream guarantee safety** — `if (typeof x === 'string')` when TypeScript already says `string`.
4. **Semantic duplication** — a new helper/util that already exists elsewhere in the codebase.
5. **Convention drift** — new file uses a different DB-access, logging, error, validation, or HTTP-client pattern than the rest of the repo.

### Full checklist

**Defensive/error-handling slop**
- [ ] `try/catch` around code that cannot throw
- [ ] `try/catch` that swallows errors silently
- [ ] Null/undefined guards on values already validated upstream
- [ ] Optional chaining (`?.`) on values the type system guarantees non-null
- [ ] "This should never happen" branches

**Comment slop**
- [ ] Comments that narrate what the next line literally does
- [ ] JSDoc on trivial getters/setters
- [ ] Function-name repetition in prose
- [ ] Section banner comments inconsistent with rest of repo

**Abstraction/structure slop**
- [ ] Wrapper functions around a single native API call with no added behaviour
- [ ] New utility file when an existing one already covers the case
- [ ] Interface + single implementation + factory for a one-off thing
- [ ] Configuration objects with one field
- [ ] `options` arguments where every caller passes the defaults

**Dead/over-produced code**
- [ ] Exports never imported elsewhere
- [ ] Two functions doing the same thing under different names
- [ ] "Future-proofing" enum values or branches with no current caller
- [ ] Commented-out code blocks

**Convention drift**
- [ ] New file uses a different logging pattern than rest of repo
- [ ] New DB query style inconsistent with repo
- [ ] Different error-response shape than other API routes
- [ ] Re-implementing auth, formatting, or constants that exist in `lib/`

---

## Reference: Size Heuristics

### File size

| Lines | What it means |
|-------|---------------|
| < 150 | Healthy |
| 150–500 | Normal — check for single responsibility |
| 500–1000 | Investigate: multiple concerns? |
| 1000+ | Almost always a smell |

### Function size

| Lines | What it means |
|-------|---------------|
| < 20 | Healthy |
| 20–60 | Investigate at second sign of trouble |
| 60+ | Likely doing more than one thing |

### Other thresholds

- **Cyclomatic complexity > 7** — count `if`, `else if`, `case`, `&&`, `||`, `?:`, `catch`, loop conditions. Eight or more is a smell.
- **More than 4 parameters** — ask if some belong to a config object.
- **More than 3-4 levels of nesting** — refactor signal; use early-return guards.

### The deep-modules test (Ousterhout)

A module is **deep** when its interface is small compared to the functionality it hides. A module is **shallow** when the interface is roughly the same size as the body. Shallow modules should be inlined or merged.
