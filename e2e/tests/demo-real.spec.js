import fs from 'node:fs'
import path from 'node:path'
import { test, expect } from '@playwright/test'

// Step 5 answers recorded for the pharmacy tape (backend/scripts/build_demo_step5.py).
const PHARMACY_STEP5 = JSON.parse(
  fs.readFileSync(path.join(__dirname, '../../frontend/public/demo/pharmacy-first-caps/step5.json'), 'utf-8'),
)

// The start of an answer as the page shows it: first non-empty line, markdown marks gone.
function shownStart(markdown) {
  const line = markdown.split('\n').find((l) => l.trim())
  return line.replace(/^[\s>#*-]+/, '').replace(/[*_`]/g, '').trim().slice(0, 50)
}

// Per-test timeout: the real golden tapes are far larger than the synthetic
// demo-e2e fixture — the pharmacy tape is ~35 MB and simulates 23,025,840 ms of
// clock time — so the replay loop needs generous headroom on slow CI runners.
// The global config timeout (60 s) governs the non-replay tests.
const REPLAY_TIMEOUT_MS = 240_000

test('landing shows the golden-run simulations, not the static feed', async ({ page }) => {
  // Navigate to the landing page and wait for the demo boxes to load.
  await page.goto('/landing')
  await page.waitForLoadState('networkidle')

  // Both golden scenarios must surface as launch boxes. The box mints the
  // session at click-time and pushes straight into the walkthrough.
  await expect(
    page.locator('[data-test="demo-box"][data-scenario-id="pharmacy-first-caps"]'),
  ).toBeVisible()
  await expect(
    page.locator('[data-test="demo-box"][data-scenario-id="energy-price-cap"]'),
  ).toBeVisible()

  // The old hardcoded static feed must be gone from demo mode — the
  // "Latest Industry Intelligence" section renders manifest scenarios instead.
  await expect(page.getByText('Basel IV')).toHaveCount(0)

  // The banner is scoped to walkthrough routes (SimulationRun/Report/
  // Interaction); /landing is outside that set, so it must not appear.
  await expect(page.locator('[data-test="demo-banner"]')).toHaveCount(0)
})

test('Pharmacy First golden run plays end-to-end', async ({ page }) => {
  // Per-test timeout — see comment at top of file.
  test.setTimeout(REPLAY_TIMEOUT_MS)

  // Enter through the landing box for the real pharmacy tape, which drives all
  // of the SimulationRun + Report endpoints the demo adapter knows.
  await page.goto('/landing')
  await page.waitForLoadState('networkidle')
  await page.locator('[data-test="demo-box"][data-scenario-id="pharmacy-first-caps"]').click()
  await page.waitForLoadState('networkidle')

  // The banner appears once we are inside the walkthrough — this proves demo
  // scoping is on during the real replay.
  await expect(page.locator('[data-test="demo-banner"]')).toBeVisible()

  // Skip straight to the end of the tape. Skip-to-end (skipMs in tape.js) was
  // reset when the box minted the session, so this jump lands exactly on the
  // terminal snapshot instead of stacking on any earlier skip.
  await page.locator('[data-test="demo-skip-end"]').click()

  // Step 3: the Generate Report button enables only when phase===2 (the
  // completed state set by Step3Simulation), so the fast-forwarded clock must
  // reach the completed state immediately — even for the 23 M ms pharmacy tape.
  const generateBtn = page.locator('[data-test="simulation-complete"]:not([disabled])')
  await expect(generateBtn).toBeVisible({ timeout: REPLAY_TIMEOUT_MS })

  // Step 4: the jump must carry through report generation — the report view
  // polls agent-log at the same (skipped) clock and completes straight away.
  await generateBtn.click()
  await expect(
    page.locator('[data-test="report-complete"]'),
  ).toBeVisible({ timeout: REPLAY_TIMEOUT_MS })

  // Verify the report title rendered from the planning_complete outline entry —
  // this proves the real tape content was actually consumed, not just that the
  // page loaded.
  await expect(
    page.getByText('Second-Order Effects of NHS England Payment Caps on Pharmacy First: A Predictive Analysis'),
  ).toBeVisible()

  // Watchdog overlays must never appear. toBeVisible() alone is insufficient
  // because the overlay is position:fixed, inset:0, z-index:9999 — an element
  // underneath it would still pass toBeVisible(). We assert count===0 instead:
  // if any overlay rendered, the real tape has a gap or load failure.
  await expect(page.locator('[data-test="watchdog-tape-failed"]')).toHaveCount(0)
  await expect(page.locator('[data-test="watchdog-not-recorded"]')).toHaveCount(0)
  await expect(page.locator('[data-test="picker-error"]')).toHaveCount(0)

  // Step 5: the recorded questions answer with the recorded answers, for the
  // report agent, for one agent, and in a survey.
  await page.locator('[data-test="report-complete"]').click()
  const chatQuestions = page.locator('[data-test="demo-questions"] .demo-question')
  await expect(chatQuestions).toHaveCount(PHARMACY_STEP5.report_questions.length)
  await chatQuestions.first().click()
  await expect(page.getByText(shownStart(PHARMACY_STEP5.report_answers[0]))).toBeVisible()

  await page.locator('.agent-pill').click()
  await page.locator('.dropdown-item').nth(3).click()
  await expect(chatQuestions).toHaveCount(PHARMACY_STEP5.agent_questions.length)
  await chatQuestions.first().click()
  await expect(page.getByText(shownStart(PHARMACY_STEP5.agents['3'].answers[0]))).toBeVisible()
  await expect(page.getByText('Reconstructed from the recorded run').first()).toBeVisible()

  await page.locator('.survey-pill').click()
  await page.locator('.agent-checkbox').first().click()
  await page.locator('[data-test="demo-survey-questions"] .demo-question').nth(1).click()
  await page.locator('.survey-submit-btn').click()
  await expect(
    page.locator('.result-answer').getByText(shownStart(PHARMACY_STEP5.agents['0'].answers[1])),
  ).toBeVisible()

  await expect(page.locator('[data-test="watchdog-tape-failed"]')).toHaveCount(0)
  await expect(page.locator('[data-test="watchdog-not-recorded"]')).toHaveCount(0)
})

test('Energy Caps golden run plays end-to-end', async ({ page }) => {
  // Per-test timeout — see comment at top of file.
  test.setTimeout(REPLAY_TIMEOUT_MS)

  // Same full-walkthrough entry path as the pharmacy test, via the real energy
  // price cap tape (6,074,562 ms of simulated clock time).
  await page.goto('/landing')
  await page.waitForLoadState('networkidle')
  await page.locator('[data-test="demo-box"][data-scenario-id="energy-price-cap"]').click()
  await page.waitForLoadState('networkidle')

  await expect(page.locator('[data-test="demo-banner"]')).toBeVisible()

  await page.locator('[data-test="demo-skip-end"]').click()

  const generateBtn = page.locator('[data-test="simulation-complete"]:not([disabled])')
  await expect(generateBtn).toBeVisible({ timeout: REPLAY_TIMEOUT_MS })

  await generateBtn.click()
  await expect(
    page.locator('[data-test="report-complete"]'),
  ).toBeVisible({ timeout: REPLAY_TIMEOUT_MS })

  await expect(
    page.getByText('UK Retail Energy Price Cap 2027: Second-Order Effects Simulation Report'),
  ).toBeVisible()

  // Watchdog overlays must not appear at the end of the run either.
  await expect(page.locator('[data-test="watchdog-tape-failed"]')).toHaveCount(0)
  await expect(page.locator('[data-test="watchdog-not-recorded"]')).toHaveCount(0)
  await expect(page.locator('[data-test="picker-error"]')).toHaveCount(0)
})
