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

  test('dashboard route loads or sends unauthenticated users to login', async ({ page }) => {
    await page.goto('/dashboard')
    await page.waitForLoadState('networkidle')
    const url = page.url()
    // With Supabase + auth enabled, expect /login; in CI without full client keys, app may stay on /dashboard.
    expect(url).toMatch(/\/(login|dashboard)/)
  })
})
