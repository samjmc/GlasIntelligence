# P1 Report — Floating report actions: fullscreen + save as PDF

Status: **DONE**

## What was added

**`frontend/src/components/Step4Report.vue`**
- Line 6: `.left-panel.report-style` now also carries `report-print-area` (stable print target, alongside the existing `ref="leftPanel"`).
- Lines 2–5: `.report-panel` root binds `report-fullscreen-overlay` class when the CSS overlay fallback is active.
- Lines 1053–1087: floating action cluster `div.report-actions-cluster` (fixed bottom-right) with:
  - `[data-test="report-fullscreen"]` — toggles fullscreen (label Enter/Exit Fullscreen, driven by `isFullscreen` / `fullscreenOverlay` state).
  - `[data-test="report-pdf"]` — Save as PDF via `window.print()`.
  - `[data-test="report-fullscreen-close"]` — close button, rendered only while the overlay fallback is active.
- Script: `isFullscreen`, `fullscreenOverlay` refs; `toggleFullscreen`, `onFullscreenChange`, `closeFullscreenOverlay`, `removePrintMode`, `saveAsPdf`; `onMounted`/`onUnmounted` listener registration (fullscreenchange, afterprint) with teardown that also strips `report-print-mode` and exits overlay state. Polling/log streaming untouched.

**`frontend/src/components/Step4Report.scoped.css`** (appended)
- `.report-actions-cluster` — `position: fixed; right: 1.5rem; bottom: 1.5rem; z-index: 50; flex; gap: 10px`.
- `.report-action-btn` — matches the app's `.tool-btn` look (white bg, #E0E0E0 border, 6px radius, hover #F5F5F5).
- `.report-close-btn` — dark inverted variant, fixed top-right (viewport-fixed, so it escapes the bottom-right cluster).
- `.report-panel.report-fullscreen-overlay` — `position: fixed; inset: 0; z-index: 9999`; inner left panel goes full-width, right panel and console logs hidden (report-only view).

**`frontend/src/style.css`** (global)
- `@media print` block per brief: `body.report-print-mode *` hidden, `.report-print-area` (+descendants) visible and `position: absolute; inset: 0; overflow: visible`. Two additional safe-guard selectors (`body.report-print-mode .report-panel, .main-split-layout { overflow: visible; }`) because `.report-panel` has `overflow: hidden` which would otherwise clip the absolutely-positioned print area at the ancestor level.

## How fullscreen fallback works

`toggleFullscreen()`:
1. Overlay already active → close it (no-op toggle).
2. `document.fullscreenElement` set → `document.exitFullscreen()`.
3. `leftPanel` missing or `document.fullscreenEnabled` false (iframe context) → CSS overlay fallback.
4. Otherwise `leftPanel.value.requestFullscreen()` inside try/catch; the returned promise also `.catch()`-ed (async rejections don't hit a sync try/catch), both falling back to the overlay.

State sync: `document` `fullscreenchange` listener updates `isFullscreen` and clears the overlay when fullscreen exits. The button label derives from `isFullscreen || fullscreenOverlay` (Enter/Exit). Overlay close = dedicated ✕ Close button (`report-fullscreen-close`) shown only in overlay mode, plus the toggle button itself.

## How print isolation works

`saveAsPdf()` adds `report-print-mode` to `document.body`, calls `window.print()`, then removes the class on the global `afterprint` event (registered in `onMounted`); a `setTimeout(removePrintMode, 1000)` fallback covers browsers where `afterprint` doesn't fire. In print media, everything is `visibility: hidden` except `.report-print-area` (and descendants), which is re-positioned `absolute; inset: 0; overflow: visible` so multi-page content flows. The floating buttons are hidden by the visibility rule (they live inside the panel but outside `.report-print-area`).

## Gate results

1. `npx vitest run` — **PASS**: 8 files, 69 tests passed (no regressions).
2. `npm run lint` — **PASS**: exit 0; 0 errors. Warnings on Step4Report.vue unchanged from baseline (pre-existing `ref`/`class` attribute warnings on the left-panel div); no new warnings introduced.
3. `VITE_DEMO_MODE=1 npm run build` — **PASS**: built in ~4.6s (pre-existing chunk-size warning only).

## Constraints honored

- No new dependencies, no API calls, no demo-mode branching, zero external requests.
- Print uses the browser's native Save-as-PDF.
- Polling / log streaming code paths untouched.
