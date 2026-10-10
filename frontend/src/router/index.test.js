import { describe, it, expect, beforeAll, afterEach } from 'vitest'
import { authState } from '../store/auth'

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

  it('sends unknown paths to a public Not Found page', () => {
    const route = router.resolve('/no/such/page')
    expect(route.name).toBe('NotFound')
    expect(route.meta.public).toBe(true)
  })

  it('gives every route a title', () => {
    const routes = router.getRoutes()
    expect(routes.length).toBeGreaterThan(15)
    expect(routes.filter((r) => !r.meta.title).map((r) => r.path)).toEqual([])
  })
})

describe('Router navigation', () => {
  afterEach(() => {
    authState.user = null
  })

  it('sets the page title per route', async () => {
    await router.push('/terms')
    expect(document.title).toBe('Terms of Service · Glas Intelligence')
  })

  it('sends a signed-in user away from login and signup', async () => {
    authState.user = { id: 'u1' }
    await router.push('/login')
    expect(router.currentRoute.value.path).toBe('/dashboard')
    await router.push('/signup')
    expect(router.currentRoute.value.path).toBe('/dashboard')
  })

  it('honours a same-site redirect for a signed-in user, and only that', async () => {
    authState.user = { id: 'u1' }
    await router.push('/login?redirect=/compare')
    expect(router.currentRoute.value.path).toBe('/compare')
    await router.push('/login?redirect=//evil.example')
    expect(router.currentRoute.value.path).toBe('/dashboard')
  })

  it('still shows login to a signed-out user', async () => {
    await router.push('/login')
    expect(router.currentRoute.value.path).toBe('/login')
  })
})
