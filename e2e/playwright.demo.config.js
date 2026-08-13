import { defineConfig } from '@playwright/test'

// Config for the static demo build only. The main playwright.config.js targets
// the backend-backed docker stack and testIgnores demo.spec.js; this config is
// its mirror image — it runs demo.spec.js and nothing else. Two configs rather
// than one are required because testIgnore takes precedence over a path named
// explicitly on the command line.
export default defineConfig({
  testDir: './tests',
  testMatch: '**/demo.spec.js',
  timeout: 30000,
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
