import { describe, it, expect, beforeAll } from 'vitest'
import { createRouter, createWebHistory } from 'vue-router'

const publicPaths = ['/login', '/signup', '/pricing', '/feed', '/landing', '/terms', '/privacy', '/health']
const authPaths = ['/dashboard', '/compare']

// The router pulls in the whole component graph (several 1-2.5k-line SFCs);
// import it once in a long-timeout hook rather than once per test, so a cold
// Vue-compiler cache on slow runners doesn't trip the default 5s test timeout.
let router
beforeAll(async () => {
  ;({ default: router } = await import('./index.js'))
}, 60000)

describe('Router configuration', () => {
  it('exports a router with routes', () => {
    expect(router).toBeDefined()
    expect(router.getRoutes().length).toBeGreaterThan(0)
  })

  it('has public routes marked correctly', () => {
    for (const path of publicPaths) {
      const route = router.resolve(path)
      expect(route.meta.public).toBe(true)
    }
  })

  it('has auth routes marked correctly', () => {
    for (const path of authPaths) {
      const route = router.resolve(path)
      expect(route.meta.requiresAuth).toBe(true)
    }
  })
})
