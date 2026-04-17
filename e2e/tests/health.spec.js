import { test, expect } from '@playwright/test'

test.describe('Health checks', () => {
  test('backend API health endpoint returns ok', async ({ request }) => {
    // Must use absolute URL: global baseURL is the Vite dev server (:3000); relative /health returns SPA HTML.
    const backend = (process.env.API_BASE_URL || 'http://127.0.0.1:5001').replace(/\/$/, '')
    const resp = await request.get(`${backend}/health`)
    expect(resp.ok()).toBeTruthy()
    const body = await resp.json()
    expect(body.status).toBe('ok')
  })

  test('frontend serves index page', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveTitle(/.+/)
  })
})
