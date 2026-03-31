import { test, expect } from '@playwright/test'

test.describe('Authentication flow', () => {
  test('login page loads', async ({ page }) => {
    await page.goto('/login')
    await page.waitForLoadState('networkidle')
    const body = await page.textContent('body')
    expect(body).toBeTruthy()
  })

  test('signup page loads', async ({ page }) => {
    await page.goto('/signup')
    await page.waitForLoadState('networkidle')
    const body = await page.textContent('body')
    expect(body).toBeTruthy()
  })

  test('unauthenticated user redirected from dashboard', async ({ page }) => {
    await page.goto('/dashboard')
    await page.waitForLoadState('networkidle')
    expect(page.url()).toContain('/login')
  })
})
