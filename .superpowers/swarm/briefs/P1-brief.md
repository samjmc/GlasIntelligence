# P1 — Floating report actions: fullscreen + save as PDF

Repo: /Users/sammcdonnell/Documents/glas-product-work (branch feat/report-actions — work here). This task WRITES CODE.

## Requirements (surgical, no new dependencies)

In `frontend/src/components/Step4Report.vue` (the prediction report component, ~1724 lines), add a floating action cluster:

1. **Floating buttons** — fixed bottom-right, always visible while the report component is mounted, two actions:
   - **Fullscreen**: `[data-test="report-fullscreen"]` — opens the report content (the `.left-panel.report-style` element — give it a stable ref/class, e.g. add `report-print-area` class to it) in fullscreen. Use the Fullscreen API (`requestFullscreen`); on failure/unavailability (iframe contexts, exceptions), fall back to a CSS fullscreen overlay (fixed inset-0, z-index above everything, the report content inside, plus a close button). Track state via `fullscreenchange`; the button toggles (Enter/Exit) and shows the right label.
   - **Save as PDF**: `[data-test="report-pdf"]` — adds `report-print-mode` to `document.body`, calls `window.print()`, then removes the class on `afterprint` (or a timeout fallback).

2. **Print isolation** — in `frontend/src/style.css` (global), add:
   ```css
   @media print {
     body.report-print-mode * { visibility: hidden; }
     body.report-print-mode .report-print-area,
     body.report-print-mode .report-print-area * { visibility: visible; }
     body.report-print-mode .report-print-area { position: absolute; inset: 0; overflow: visible; }
   }
   ```
   (adjust selectors if the report content needs ancestors visible — verify the print output contains the report only.)

3. **Constraints**:
   - NO new runtime dependencies (print = `window.print()`; the browser's Save-as-PDF is the mechanism).
   - Must work identically in the DEMO replay (the component renders the same in demo mode) — no demo-specific branching.
   - Zero external requests; no API calls added.
   - Don't break the existing report polling/log streaming (Step4Report has active polling — your change is UI-only).
   - Match the component's existing styling conventions (check Step4Report.scoped.css / inline styles for the button look; the app has `.tool-btn` patterns in GraphPanel).

## Gates (run and report results)
1. `cd frontend && npx vitest run` → 69 tests pass (no regressions).
2. `npm run lint` → clean.
3. `VITE_DEMO_MODE=1 npm run build` → succeeds.

## Report
Write to .superpowers/swarm/reports/P1-report.md — what you added (file:line), how fullscreen fallback works, how print isolation works, gate results.
Return ONLY: status (DONE/BLOCKED), one-line summary, changed files, gate results, report path.
