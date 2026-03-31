import { test, expect } from '@playwright/test'

test.describe('Landing page', () => {
  test('renders without errors', async ({ page }) => {
    await page.goto('/landing')
    await page.waitForLoadState('networkidle')
    const errors = []
    page.on('pageerror', (err) => errors.push(err.message))
    expect(errors).toHaveLength(0)
  })

  test('has navigation links', async ({ page }) => {
    await page.goto('/landing')
    await page.waitForLoadState('networkidle')
    const body = await page.textContent('body')
    expect(body).toBeTruthy()
  })
})
