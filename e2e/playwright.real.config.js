import { defineConfig } from '@playwright/test'

// Config for the static demo build running the REAL golden tapes (pharmacy
// first-caps + energy-price-cap) straight from frontend/public/demo/. The
// synthetic demo config (playwright.demo.config.js) runs the staged 6 s
// demo-e2e fixture; this config is the practical-use-case counterpart — it
// runs demo-real.spec.js and nothing else, against a build that does NOT stage
// the fixture, so the huge real tapes must replay end-to-end.
export default defineConfig({
  testDir: './tests',
  testMatch: '**/demo-real.spec.js',
  // Higher than the synthetic config: the real pharmacy tape is ~35 MB and
  // replays over minutes of simulated clock time, so per-test and global
  // timeouts both need headroom on slow CI runners.
  timeout: 60000,
  retries: 1,
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:3000',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
  ],
  reporter: [['html', { open: 'never' }]],
})
