import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  // The demo spec requires a static demo build (VITE_DEMO_MODE=1 plus staged
  // tape fixtures) and cannot pass against the backend-backed stack this config
  // targets. It runs from playwright.demo.config.js in the demo-e2e workflow.
  // testIgnore also wins over an explicit path on the command line, which is
  // why the demo job needs its own config rather than just naming the file.
  testIgnore: '**/demo.spec.js',
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
