import { describe, it, expect } from 'vitest'
import { createRouter, createWebHistory } from 'vue-router'

const publicPaths = ['/login', '/signup', '/pricing', '/feed', '/landing', '/terms', '/privacy', '/health']
const authPaths = ['/dashboard', '/compare']

describe('Router configuration', () => {
  it('exports a router with routes', async () => {
    const { default: router } = await import('./index.js')
    expect(router).toBeDefined()
    expect(router.getRoutes().length).toBeGreaterThan(0)
  })

  it('has public routes marked correctly', async () => {
    const { default: router } = await import('./index.js')
    for (const path of publicPaths) {
      const route = router.resolve(path)
      expect(route.meta.public).toBe(true)
    }
  })

  it('has auth routes marked correctly', async () => {
    const { default: router } = await import('./index.js')
    for (const path of authPaths) {
      const route = router.resolve(path)
      expect(route.meta.requiresAuth).toBe(true)
    }
  })
})
