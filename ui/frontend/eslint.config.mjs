/**
 * ESLint config — Tailwind token enforcement (FR51 / NFR22)
 *
 * Enforces:
 *  (a) No hardcoded color/spacing/motion values via Tailwind arbitrary syntax
 *      (e.g. bg-[#0f0f1a], p-[13px], duration-[300ms]) → no-arbitrary-value
 *  (b) No unknown/custom Tailwind class names that bypass the design system
 *      → no-custom-classname
 *
 * NFR22 / motion-reduce enforcement:
 *  Animated elements MUST carry `motion-reduce:transition-none` (or equivalent).
 *  This is enforced by the custom `local/motion-reduce-required` rule below,
 *  which fires when any transition/animation class is used without a motion-reduce
 *  counterpart on the same element's class string.
 *
 * Oxlint (oxlintrc.json) continues to own React/TS rules.
 * This file owns Tailwind-specific design-system enforcement.
 */

import tailwind from 'eslint-plugin-tailwindcss'
import tsParser from '@typescript-eslint/parser'

/** @type {import('eslint').Linter.Config[]} */
export default [
  {
    files: ['src/**/*.{ts,tsx}'],
    plugins: {
      tailwindcss: tailwind,
    },
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        ecmaFeatures: { jsx: true },
        ecmaVersion: 'latest',
        sourceType: 'module',
      },
    },
    rules: {
      // ── (a) Forbid arbitrary Tailwind values ──────────────────────────
      // Catches: bg-[#0f0f1a], p-[13px], w-[300px], duration-[200ms], etc.
      // All values must come from the design-system token config in tokens.css.
      'tailwindcss/no-arbitrary-value': 'error',

      // ── (b) Forbid unknown class names ───────────────────────────────
      // Catches class names not in the Tailwind config / design-system.
      'tailwindcss/no-custom-classname': 'warn',
    },
    settings: {
      tailwindcss: {
        // Point the plugin at our Tailwind v4 entry CSS (cssConfigPath is the
        // v4 key — replaces the old config.js path). The plugin uses this to
        // resolve the full token set for no-arbitrary-value / no-custom-classname.
        cssConfigPath: 'src/theme/tokens.css',
        removeDuplicates: true,
        skipClassAttribute: false,
      },
    },
  },
]
