import { test, expect } from '@playwright/test'

/**
 * Full checks (request counts, refresh= only on button, graph_memory body, 429 backoff)
 * need an authenticated session and a project with graph_id. Follow docs/zep-footprint.md
 * (Verification checklist) when testing a real deploy.
 */
test.describe('Zep footprint (integrated)', () => {
  test('app shell reachable for manual HAR capture', async ({ page }) => {
    const res = await page.goto('/')
    expect(res?.ok() || res?.status() === 304).toBeTruthy()
    await expect(page.locator('body')).toBeVisible()
  })
})
