import { test, expect } from '@playwright/test'

test.describe('Health checks', () => {
  test('backend API health endpoint returns ok', async ({ request }) => {
    const resp = await request.get('/api/health', {
      baseURL: process.env.BASE_URL?.replace(':3000', ':5001') || 'http://localhost:5001',
    })
    expect(resp.ok()).toBeTruthy()
    const body = await resp.json()
    expect(body.status).toBe('ok')
  })

  test('frontend serves index page', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveTitle(/.+/)
  })
})
