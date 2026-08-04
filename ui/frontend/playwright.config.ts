import { defineConfig, devices } from '@playwright/test'

// Task 1.7 AC: a minimal Playwright e2e test loads the *built* app (not the
// dev server) — `webServer` serves the `npm run build` output via
// `vite preview`, matching how the BFF ultimately serves the static bundle.
// CI runs `npm run build` immediately before `npm run e2e` (see
// .github/workflows/ci.yml, "Frontend UI" job).
const PORT = 4173

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  // html always runs (it's what CI's playwright-report artifact uploads —
  // without it that upload is an empty no-op); line is added for CI logs.
  reporter: process.env.CI
    ? [['line'], ['html', { open: 'never' }]]
    : [['html', { open: 'never' }]],
  use: {
    baseURL: `http://localhost:${PORT}`,
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: `npm run preview -- --port ${PORT} --strictPort`,
    url: `http://localhost:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
})
