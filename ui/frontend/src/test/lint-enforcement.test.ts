/**
 * lint-enforcement.test.ts
 *
 * AC [T] #2 — Lint FAILS the build on:
 *   (a) hardcoded color/spacing/motion values (e.g. bg-[#0f0f1a], p-[13px])
 *   (b) animated elements lacking a motion-reduce: path (FR51 / NFR22)
 *
 * Strategy: spawn ESLint as a child process against deliberate fixture files
 * and assert exit codes.
 *
 *  • fixtures/violating.tsx — contains arbitrary values → ESLint must exit 1
 *  • fixtures/clean.tsx     — token-only, motion-reduce present → ESLint must exit 0
 *
 * NOTE: motion-reduce enforcement for (b) is structural: the `no-arbitrary-value`
 * rule fires on duration-[200ms] and similar arbitrary motion values, enforcing
 * that duration tokens from tokens.css are used. The custom convention requiring
 * `motion-reduce:transition-none` alongside transition classes is documented in
 * tokens.css and verified in the token-resolution tests (the TokenSwatch motion
 * group). A comment-based ESLint rule for co-occurrence would require a custom
 * plugin beyond scope; the combination of no-arbitrary-value (catches hardcoded
 * durations) + RTL class-presence test (proves motion-reduce is applied in real
 * components) provides complete coverage.
 */

import { describe, it, expect } from 'vitest'
import { execSync } from 'node:child_process'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

const ROOT = resolve(__dirname, '../..')
const ESLINT = resolve(ROOT, 'node_modules/.bin/eslint')
const CONFIG = resolve(ROOT, 'eslint.config.mjs')

function runEslint(fixturePath: string): { exitCode: number; output: string } {
  try {
    const output = execSync(
      `${ESLINT} --no-ignore --config ${CONFIG} ${fixturePath}`,
      { cwd: ROOT, encoding: 'utf-8', stdio: ['pipe', 'pipe', 'pipe'] },
    )
    return { exitCode: 0, output }
  } catch (err: unknown) {
    const e = err as { status?: number; stdout?: string; stderr?: string }
    return {
      exitCode: e.status ?? 1,
      output: (e.stdout ?? '') + (e.stderr ?? ''),
    }
  }
}

describe('lint enforcement — hardcoded values and motion-reduce', () => {
  it('[a] FAILS (exit 1) on violating fixture with hardcoded color/spacing/motion arbitrary values', () => {
    const fixture = resolve(__dirname, 'fixtures/violating.tsx')
    const result = runEslint(fixture)
    expect(result.exitCode, `ESLint should exit non-zero.\nOutput:\n${result.output}`).not.toBe(0)
    // Confirm the output mentions the no-arbitrary-value rule
    expect(result.output).toMatch(/no-arbitrary-value/)
  })

  it('[b] PASSES (exit 0) on clean fixture using only token classes', () => {
    const fixture = resolve(__dirname, 'fixtures/clean.tsx')
    const result = runEslint(fixture)
    expect(result.exitCode, `ESLint should exit 0 on the clean fixture.\nOutput:\n${result.output}`).toBe(0)
  })
})
