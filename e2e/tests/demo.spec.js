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

test('demo replays a scenario through to a report', async ({ page }) => {
  // Per-test timeout — see comment at top of file.
  test.setTimeout(REPLAY_TIMEOUT_MS)

  await page.goto('/')

  // Verify the demo banner is present (confirms demo mode is active).
  await expect(page.getByText('Demo — replaying a recorded simulation')).toBeVisible()

  // Select the e2e fixture scenario explicitly by id so this test cannot
  // silently switch to a real scenario when Task 3 adds more cards.
  await page.locator('[data-test="scenario-card"][data-scenario-id="demo-e2e"]').click()
  await page.getByRole('button', { name: /start engine/i }).click()

  // Assert the simulation replayed to completion. The "Generate Report" button
  // carries data-test="simulation-complete" and is only enabled when phase===2
  // (the completed state set by Step3Simulation). Asserting :not([disabled])
  // confirms the simulation actually reached completion, not just that the
  // button exists.
  await expect(
    page.locator('[data-test="simulation-complete"]:not([disabled])'),
  ).toBeVisible({ timeout: REPLAY_TIMEOUT_MS })

  // Negative assertions: the watchdog overlays must never appear.
  // toBeVisible() alone is insufficient because the overlay is position:fixed,
  // inset:0, z-index:9999 — an element underneath it would still pass
  // toBeVisible(). We assert count===0 instead: if the overlay rendered at
  // all, the demo has a fixture gap or a tape-load failure.
  await expect(page.locator('[data-test="watchdog-tape-failed"]')).toHaveCount(0)
  await expect(page.locator('[data-test="watchdog-not-recorded"]')).toHaveCount(0)
  await expect(page.locator('[data-test="picker-error"]')).toHaveCount(0)
})
