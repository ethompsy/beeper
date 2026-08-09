/**
 * login-next-path.test.ts (Task 8.6 — ADR 0002 §2, client-side `next=`
 * safety check for `/app/login`).
 */
import { describe, it, expect } from 'vitest'
import { resolveSafeNextPath, DEFAULT_NEXT } from '../login-next-path'

describe('resolveSafeNextPath', () => {
  it('returns the default when raw is null', () => {
    expect(resolveSafeNextPath(null)).toBe(DEFAULT_NEXT)
  })

  it('returns the default when raw is an empty string', () => {
    expect(resolveSafeNextPath('')).toBe(DEFAULT_NEXT)
  })

  it('accepts a plain /app/... path', () => {
    expect(resolveSafeNextPath('/app/investigations')).toBe('/app/investigations')
  })

  it('accepts a /app/... path with a nested id', () => {
    expect(resolveSafeNextPath('/app/investigations/inv-123')).toBe('/app/investigations/inv-123')
  })

  it('accepts the bare /app path', () => {
    expect(resolveSafeNextPath('/app')).toBe('/app')
  })

  it('percent-decodes before validating', () => {
    expect(resolveSafeNextPath('%2Fapp%2Finvestigations')).toBe('/app/investigations')
  })

  it('rejects an absolute URL to another origin', () => {
    expect(resolveSafeNextPath('https://evil.example.com')).toBe(DEFAULT_NEXT)
  })

  it('rejects a protocol-relative URL', () => {
    expect(resolveSafeNextPath('//evil.example.com')).toBe(DEFAULT_NEXT)
  })

  it('rejects an encoded protocol-relative URL', () => {
    expect(resolveSafeNextPath('%2F%2Fevil.example.com')).toBe(DEFAULT_NEXT)
  })

  it('rejects a path outside /app', () => {
    expect(resolveSafeNextPath('/other/path')).toBe(DEFAULT_NEXT)
  })

  it('rejects a bare "app" with no leading slash', () => {
    expect(resolveSafeNextPath('app/investigations')).toBe(DEFAULT_NEXT)
  })

  it('rejects a scheme embedded after decoding', () => {
    expect(resolveSafeNextPath('javascript:alert(1)')).toBe(DEFAULT_NEXT)
  })

  it('falls back to the default on a malformed percent-encoding', () => {
    expect(resolveSafeNextPath('/app/%')).toBe(DEFAULT_NEXT)
  })
})
