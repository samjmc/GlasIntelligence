import { test, expect } from '@playwright/test'

test('demo makes no third-party requests', async ({ page }) => {
  const external = []
  // Derive the expected origin from BASE_URL before any navigation so that
  // the comparison is stable even when page.url() still returns 'about:blank'.
  const ownOrigin = new URL(process.env.BASE_URL || 'http://localhost:4173').origin

  page.on('request', (req) => {
    const url = new URL(req.url())
    if (url.origin !== ownOrigin) {
      external.push(req.url())
    }
  })

  await page.goto('/')
  await page.waitForLoadState('networkidle')

  expect(external, `demo requested external origins:\n${external.join('\n')}`).toEqual([])
})

test('demo replays a scenario through to a report', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByText('Demo — replaying a recorded simulation')).toBeVisible()

  await page.locator('[data-test="scenario-card"]').first().click()
  await page.getByRole('button', { name: /start|run|begin/i }).first().click()

  // The tape is sped up to a 90s target, so allow generous headroom.
  await expect(page.getByText(/simulation complete/i)).toBeVisible({ timeout: 180000 })
})
