import { test, expect } from '@playwright/test'

// Per-test timeout: raised for the replay test so the polling loop has time to
// see the completed state even on slow CI runners. The global config timeout
// (30 s) governs all other tests and is intentionally left unchanged.
const REPLAY_TIMEOUT_MS = 120_000

test('demo makes no third-party requests', async ({ page, baseURL }) => {
  const external = []
  // Derive the expected origin from the Playwright baseURL fixture — a single
  // source of truth shared with playwright.config.js. Using process.env directly
  // here would diverge from the config when BASE_URL is unset, because the
  // config defaults to :3000 (dev server) while the env var would still be
  // undefined. page.url() cannot be used before navigation as it returns
  // 'about:blank', whose origin is the string 'null'.
  const ownOrigin = new URL(baseURL).origin

  page.on('request', (req) => {
    const url = new URL(req.url())
    if (url.origin !== ownOrigin) {
      external.push(req.url())
    }
  })

  // Enter through the landing-page demo box so the manifest fetch, the tape.json
  // fetch and the simulation route all fall inside the assertion window (covers
  // the full demo flow, not just the landing page).
  await page.goto('/landing')
  await page.waitForLoadState('networkidle')

  // Launch the e2e fixture scenario explicitly by id so this test cannot
  // silently switch to a real scenario when the manifest grows more boxes.
  await page.locator('[data-test="demo-box"][data-scenario-id="demo-e2e"]').click()
  // Wait for the simulation run page to load, then assert no external origins.
  await page.waitForLoadState('networkidle')

  expect(external, `demo requested external origins:\n${external.join('\n')}`).toEqual([])
})

test('demo replays a scenario through to a rendered report', async ({ page }) => {
  // Per-test timeout — see comment at top of file.
  test.setTimeout(REPLAY_TIMEOUT_MS)

  // Navigate to the landing page and wait for the demo boxes to load.
  await page.goto('/landing')
  await page.waitForLoadState('networkidle')

  // The banner must NOT appear on /landing: it is scoped to walkthrough routes
  // (SimulationRun/Report/Interaction), and landing is outside that set.
  await expect(page.locator('[data-test="demo-banner"]')).toHaveCount(0)

  // Launch the e2e fixture scenario from its landing box. The box mints the
  // session at click-time and pushes straight into the walkthrough.
  await page.locator('[data-test="demo-box"][data-scenario-id="demo-e2e"]').click()
  await page.waitForLoadState('networkidle')

  // The banner appears only once we are inside the walkthrough — this proves
  // demo scoping is on during the replay, not just that demo mode is active.
  await expect(page.locator('[data-test="demo-banner"]')).toBeVisible()

  // Step 3: Assert the simulation replayed to completion. The "Generate Report"
  // button carries data-test="simulation-complete" and is only enabled when
  // phase===2 (the completed state set by Step3Simulation). Asserting
  // :not([disabled]) confirms the simulation actually reached completion, not
  // just that the button exists.
  const generateBtn = page.locator('[data-test="simulation-complete"]:not([disabled])')
  await expect(generateBtn).toBeVisible({ timeout: REPLAY_TIMEOUT_MS })

  // Negative assertions at Step 3: watchdog overlays must never appear.
  // toBeVisible() alone is insufficient because the overlay is position:fixed,
  // inset:0, z-index:9999 — an element underneath it would still pass
  // toBeVisible(). We assert count===0 instead: if the overlay rendered at all,
  // the demo has a fixture gap or a tape-load failure.
  await expect(page.locator('[data-test="watchdog-tape-failed"]')).toHaveCount(0)
  await expect(page.locator('[data-test="watchdog-not-recorded"]')).toHaveCount(0)
  await expect(page.locator('[data-test="picker-error"]')).toHaveCount(0)

  // Step 4: Click "Generate Report" and wait for the report view to complete.
  // This exercises POST /api/report/generate, GET /api/report/:id, and the
  // cursor-based agent-log polling (the path that tape.js was recently fixed
  // to key separately per from_line value).
  await generateBtn.click()

  // Wait for the "Proceed to Deep Interaction" button — it only renders when
  // Step4Report.vue sets isComplete=true, which happens only after the tape
  // delivers a report_complete log entry.
  await expect(
    page.locator('[data-test="report-complete"]'),
  ).toBeVisible({ timeout: REPLAY_TIMEOUT_MS })

  // Cursor-regression assertion: verify that the agent log has exactly 3
  // entries (report_start, planning_complete, report_complete) — one from the
  // from_line=0 poll and one from the from_line=2 poll. If the cursor keying
  // regressed and both polls returned the same entries, we would see 5 or more
  // (the from_line=0 entries would be appended again). If they collapsed into
  // one entry, we would see fewer than 3.
  await expect(page.locator('[data-test="agent-log-entry"]')).toHaveCount(3)

  // Negative assertions at Step 4: watchdog overlays must still not appear.
  await expect(page.locator('[data-test="watchdog-tape-failed"]')).toHaveCount(0)
  await expect(page.locator('[data-test="watchdog-not-recorded"]')).toHaveCount(0)

  // Verify the report title rendered from the planning_complete outline entry —
  // this proves the tape content was actually consumed, not just that the page
  // loaded.
  await expect(
    page.getByText('Pharmacy First Commissioning: Stakeholder Impact Analysis'),
  ).toBeVisible()
})

test('demo banner is scoped to the walkthrough and skip-to-end reaches the report', async ({ page }) => {
  // Per-test timeout — see comment at top of file.
  test.setTimeout(REPLAY_TIMEOUT_MS)

  // Same entry path as the replay test: banner absent on /landing, present
  // once the box click drops us into the walkthrough.
  await page.goto('/landing')
  await page.waitForLoadState('networkidle')
  await expect(page.locator('[data-test="demo-banner"]')).toHaveCount(0)

  await page.locator('[data-test="demo-box"][data-scenario-id="demo-e2e"]').click()
  await page.waitForLoadState('networkidle')
  await expect(page.locator('[data-test="demo-banner"]')).toBeVisible()

  await expect(page.locator('[data-test="watchdog-tape-failed"]')).toHaveCount(0)
  await expect(page.locator('[data-test="watchdog-not-recorded"]')).toHaveCount(0)

  // Skip straight to the end of the tape. Skip-to-end (skipMs in tape.js) was
  // reset when the box minted the session, so this jump lands exactly on the
  // terminal snapshot instead of stacking on any earlier skip.
  await page.locator('[data-test="demo-skip-end"]').click()

  // Step 3: the Generate Report button enables only when phase===2, so the
  // fast-forwarded clock must reach the completed state immediately.
  const generateBtn = page.locator('[data-test="simulation-complete"]:not([disabled])')
  await expect(generateBtn).toBeVisible({ timeout: REPLAY_TIMEOUT_MS })

  await expect(page.locator('[data-test="watchdog-tape-failed"]')).toHaveCount(0)
  await expect(page.locator('[data-test="watchdog-not-recorded"]')).toHaveCount(0)

  // Step 4: the jump must carry through report generation — the report view
  // polls agent-log at the same (skipped) clock and completes straight away.
  await generateBtn.click()
  await expect(
    page.locator('[data-test="report-complete"]'),
  ).toBeVisible({ timeout: REPLAY_TIMEOUT_MS })

  await expect(page.locator('[data-test="watchdog-tape-failed"]')).toHaveCount(0)
  await expect(page.locator('[data-test="watchdog-not-recorded"]')).toHaveCount(0)

  // Reload mid-walkthrough: the adapter rehydrates the session from localStorage
  // and DemoBanner restores the persisted skip, so the banner must come straight
  // back rather than restarting the walk from the beginning.
  await page.reload()
  await expect(page.locator('[data-test="demo-banner"]')).toBeVisible()

  // Leaving the walkthrough hides the banner again even though the session still
  // exists in storage — scoping is route-driven, not session-driven.
  await page.goto('/landing')
  await page.waitForLoadState('networkidle')
  await expect(page.locator('[data-test="demo-banner"]')).toHaveCount(0)
})