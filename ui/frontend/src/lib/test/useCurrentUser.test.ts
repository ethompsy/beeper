/**
 * useCurrentUser.test.ts (Task 8.4)
 *
 * AC [T]: "useCurrentUser failure-tolerance (unreachable ⇒ mode none)".
 * Stubs `global.fetch` (matching this codebase's established convention,
 * e.g. `useInvestigationEvents.test.ts`, `src/api/test/http.test.ts`) —
 * `useCurrentUser` is a thin `useEffect` wrapper around
 * `src/api/http.ts`'s `fetchCurrentUser()`, so these tests exercise it
 * through the public hook surface a page would actually use.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { useCurrentUser } from '../hooks/useCurrentUser'

function meResponse(body: Record<string, unknown>): Response {
  return { ok: true, status: 200, json: async () => body } as unknown as Response
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('useCurrentUser', () => {
  it('starts in a loading state before the probe resolves', () => {
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => {}))) // never resolves
    const { result } = renderHook(() => useCurrentUser())

    expect(result.current.loading).toBe(true)
    expect(result.current).toMatchObject({ authenticated: false, auth_mode: 'none', user: null })
  })

  it('hydrates authenticated state from a successful /me response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        meResponse({
          authenticated: true,
          auth_mode: 'local',
          user: { user_name: 'alice', display_name: 'Alice Alpha', role: 'admin' },
        }),
      ),
    )
    const { result } = renderHook(() => useCurrentUser())

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current).toEqual({
      loading: false,
      authenticated: true,
      auth_mode: 'local',
      user: { user_name: 'alice', display_name: 'Alice Alpha', role: 'admin' },
    })
  })

  it('an unreachable /me (network failure) settles to auth_mode none, never throws', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const { result } = renderHook(() => useCurrentUser())

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current).toEqual({
      loading: false,
      authenticated: false,
      auth_mode: 'none',
      user: null,
    })
  })

  it('a non-JSON /me body settles to auth_mode none, never throws', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => {
          throw new SyntaxError('Unexpected token')
        },
      }),
    )
    const { result } = renderHook(() => useCurrentUser())

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.auth_mode).toBe('none')
    expect(result.current.authenticated).toBe(false)
  })

  it('a non-OK HTTP status settles to auth_mode none, never throws', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503 }))
    const { result } = renderHook(() => useCurrentUser())

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current).toEqual({
      loading: false,
      authenticated: false,
      auth_mode: 'none',
      user: null,
    })
  })

  it('unmounting before the probe resolves does not set state on the unmounted hook', async () => {
    let resolveFetch: (value: Response) => void = () => {}
    vi.stubGlobal(
      'fetch',
      vi.fn().mockReturnValue(
        new Promise<Response>((resolve) => {
          resolveFetch = resolve
        }),
      ),
    )
    const { unmount } = renderHook(() => useCurrentUser())
    unmount()

    // Resolving after unmount must not throw an act()/state-on-unmounted warning.
    resolveFetch(meResponse({ authenticated: true, auth_mode: 'local', user: null }))
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
})
