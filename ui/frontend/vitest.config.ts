/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import { configDefaults } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Vitest-specific config (separate from vite.config.ts to avoid polluting the
// production build config with test-only options).
export default defineConfig({
  plugins: [
    tailwindcss(),
    react(),
  ],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: true,
    // Playwright e2e specs (Task 1.7) live under e2e/ and use their own
    // test.describe/test runner — exclude them from Vitest's default
    // include glob so they aren't double-collected.
    exclude: [...configDefaults.exclude, 'e2e/**'],
    typecheck: {
      tsconfig: './tsconfig.test.json',
    },
  },
})
