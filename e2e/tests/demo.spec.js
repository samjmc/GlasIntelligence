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

  // Navigate to the home page and wait for the scenario picker to load.
  await page.goto('/')
  await page.waitForLoadState('networkidle')

  // Click through the scenario so the tape.json fetch and the simulation route
  // also fall inside the assertion window (covers the full demo flow, not just
  // the landing page).
  await page.locator('[data-test="scenario-card"][data-scenario-id="demo-e2e"]').click()
  await page.getByRole('button', { name: /start engine/i }).click()
  // Wait for the simulation run page to load, then assert no external origins.
  await page.waitForLoadState('networkidle')

  expect(external, `demo requested external origins:\n${external.join('\n')}`).toEqual([])
})

test('demo replays a scenario through to a rendered report', async ({ page }) => {
  // Per-test timeout — see comment at top of file.
  test.setTimeout(REPLAY_TIMEOUT_MS)

  await page.goto('/')

  // Verify the demo banner is present (confirms demo mode is active).
  await expect(page.getByText('Demo — replaying a recorded simulation')).toBeVisible()

  // Select the e2e fixture scenario explicitly by id so this test cannot
  // silently switch to a real scenario when Task 3 adds more cards.
  await page.locator('[data-test="scenario-card"][data-scenario-id="demo-e2e"]').click()
  await page.getByRole('button', { name: /start engine/i }).click()

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
