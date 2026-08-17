/**
 * http.test.ts (Task 8.4)
 *
 * Coverage for the shared `apiFetch` seam (`src/api/http.ts`) — the ADR
 * 0002 §8 "frontend seam" every `src/api/*.ts` client is migrated onto.
 * Mocks `global.fetch` via `vi.stubGlobal`, matching this codebase's
 * established convention (`investigation-detail.test.ts` et al.); the
 * navigation side effect is intercepted through `__setNavigateForTest`
 * rather than `window.location` (jsdom does not implement real navigation).
 *
 * AC coverage:
 *  - `[T]` apiFetch 401 -> mode-aware redirect (all three modes tested)
 *  - `[T]` apiFetch 403 -> typed PermissionDeniedError, no redirect
 *  - `[T]` same-origin credentials default
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  __resetApiFetchForTest,
  __setNavigateForTest,
  apiFetch,
  fetchCurrentUser,
  PermissionDeniedError,
  recheckAuthAfterStreamFailure,
} from '../http'

const AUTH_REQUIRED_TYPE = 'https://beeper.dev/errors/authentication-required'

function problemResponse(
  body: Record<string, unknown>,
  status: number,
  contentType = 'application/problem+json',
): Response {
  const payload = { ...body }
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers({ 'content-type': contentType }),
    clone() {
      return problemResponse(payload, status, contentType)
    },
    json: async () => payload,
  } as unknown as Response
}

function okResponse(body: unknown = {}): Response {
  return {
    ok: true,
    status: 200,
    json: async () => body,
  } as unknown as Response
}

function meResponse(body: Record<string, unknown>): Response {
  return {
    ok: true,
    status: 200,
    clone() {
      return meResponse(body)
    },
    json: async () => body,
  } as unknown as Response
}

/**
 * Installs a `global.fetch` mock that special-cases `/api/v1/auth/me`
 * (`apiFetch`'s internal mode-probe endpoint) and otherwise defers to
 * `otherwise` for the actual request under test.
 */
function stubFetchWithMe(meBody: Record<string, unknown>, otherwise: () => Response) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString()
    if (url.startsWith('/api/v1/auth/me')) {
      return meResponse(meBody)
    }
    return otherwise()
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

beforeEach(() => {
  __resetApiFetchForTest()
})

afterEach(() => {
  vi.unstubAllGlobals()
  __resetApiFetchForTest()
})

describe('apiFetch — same-origin credentials default', () => {
  it('injects credentials: same-origin by default', async () => {
    const fetchMock = vi.fn().mockResolvedValue(okResponse({ ok: true }))
    vi.stubGlobal('fetch', fetchMock)

    await apiFetch('/api/v1/investigations/')

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/investigations/', {
      credentials: 'same-origin',
    })
  })

  it('lets an explicit credentials value in init override the default', async () => {
    const fetchMock = vi.fn().mockResolvedValue(okResponse({ ok: true }))
    vi.stubGlobal('fetch', fetchMock)

    await apiFetch('/api/v1/investigations/', { credentials: 'omit' })

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/investigations/', { credentials: 'omit' })
  })

  it('passes an AbortSignal through untouched', async () => {
    const fetchMock = vi.fn().mockResolvedValue(okResponse({ ok: true }))
    vi.stubGlobal('fetch', fetchMock)
    const controller = new AbortController()

    await apiFetch('/api/v1/investigations/', { signal: controller.signal })

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/investigations/', {
      credentials: 'same-origin',
      signal: controller.signal,
    })
  })

  it('2xx/404/500 responses pass through untouched (no interception)', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 503 })
    vi.stubGlobal('fetch', fetchMock)

    const response = await apiFetch('/api/v1/investigations/')
    expect(response.status).toBe(503)
  })
})

describe('apiFetch — 401 authentication-required -> mode-aware redirect', () => {
  it('oidc mode redirects to /auth/login?next=<current path>', async () => {
    const navigate = vi.fn()
    __setNavigateForTest(navigate)
    stubFetchWithMe({ authenticated: false, auth_mode: 'oidc', user: null }, () =>
      problemResponse({ type: AUTH_REQUIRED_TYPE, status: 401 }, 401),
    )
    Object.defineProperty(window, 'location', {
      value: { pathname: '/app/investigations', search: '?status=open', hash: '' },
      writable: true,
    })

    await apiFetch('/api/v1/investigations/')
    // The redirect is fired-and-forgotten (`void redirectToLogin()`); flush microtasks.
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(navigate).toHaveBeenCalledWith(
      '/auth/login?next=' + encodeURIComponent('/app/investigations?status=open'),
    )
  })

  it('local mode redirects to /app/login?next=<current path>', async () => {
    const navigate = vi.fn()
    __setNavigateForTest(navigate)
    stubFetchWithMe({ authenticated: false, auth_mode: 'local', user: null }, () =>
      problemResponse({ type: AUTH_REQUIRED_TYPE, status: 401 }, 401),
    )
    Object.defineProperty(window, 'location', {
      value: { pathname: '/app/knowledge', search: '', hash: '' },
      writable: true,
    })

    await apiFetch('/api/v1/knowledge/')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(navigate).toHaveBeenCalledWith(
      '/app/login?next=' + encodeURIComponent('/app/knowledge'),
    )
  })

  it('mode none never redirects, even if a 401 with the auth-required type somehow arrives', async () => {
    const navigate = vi.fn()
    __setNavigateForTest(navigate)
    stubFetchWithMe({ authenticated: false, auth_mode: 'none', user: null }, () =>
      problemResponse({ type: AUTH_REQUIRED_TYPE, status: 401 }, 401),
    )

    const response = await apiFetch('/api/v1/investigations/')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(navigate).not.toHaveBeenCalled()
    // Still returns the response — the client's own !response.ok handling proceeds.
    expect(response.status).toBe(401)
  })

  it('a 401 WITHOUT the authentication-required problem type does not redirect', async () => {
    const navigate = vi.fn()
    __setNavigateForTest(navigate)
    const fetchMock = vi.fn().mockResolvedValue(problemResponse({ type: 'something-else' }, 401))
    vi.stubGlobal('fetch', fetchMock)

    await apiFetch('/api/v1/investigations/')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(navigate).not.toHaveBeenCalled()
  })

  it('caches the resolved mode across repeated 401s (only one /me probe)', async () => {
    const navigate = vi.fn()
    __setNavigateForTest(navigate)
    const meMock = vi.fn().mockResolvedValue(
      meResponse({ authenticated: false, auth_mode: 'oidc', user: null }),
    )
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url.startsWith('/api/v1/auth/me')) return meMock()
      return problemResponse({ type: AUTH_REQUIRED_TYPE, status: 401 }, 401)
    })
    vi.stubGlobal('fetch', fetchMock)
    Object.defineProperty(window, 'location', {
      value: { pathname: '/app/x', search: '', hash: '' },
      writable: true,
    })

    await apiFetch('/api/v1/investigations/')
    await new Promise((resolve) => setTimeout(resolve, 0))
    await apiFetch('/api/v1/knowledge/')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(meMock).toHaveBeenCalledTimes(1)
    expect(navigate).toHaveBeenCalledTimes(2)
  })
})

describe('apiFetch — 403 throws a typed PermissionDeniedError, never redirects', () => {
  it('throws PermissionDeniedError with the problem body detail', async () => {
    const navigate = vi.fn()
    __setNavigateForTest(navigate)
    const fetchMock = vi.fn().mockResolvedValue(
      problemResponse(
        {
          type: 'https://beeper.dev/errors/not-provisioned',
          detail: 'This account is authenticated but not provisioned for access.',
          status: 403,
        },
        403,
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(apiFetch('/api/v1/investigations/')).rejects.toBeInstanceOf(
      PermissionDeniedError,
    )
    await expect(apiFetch('/api/v1/investigations/')).rejects.toMatchObject({
      status: 403,
      detail: 'This account is authenticated but not provisioned for access.',
    })
    expect(navigate).not.toHaveBeenCalled()
  })

  it('falls back to a generic detail message when the body has none', async () => {
    const fetchMock = vi.fn().mockResolvedValue(problemResponse({}, 403))
    vi.stubGlobal('fetch', fetchMock)

    await expect(apiFetch('/api/v1/investigations/')).rejects.toMatchObject({
      message: 'You do not have permission to access this resource.',
    })
  })
})

describe('fetchCurrentUser — failure-tolerant probe', () => {
  it('resolves the parsed shape on a normal 200 response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        meResponse({
          authenticated: true,
          auth_mode: 'local',
          user: { user_name: 'alice', display_name: 'Alice', role: 'admin' },
        }),
      ),
    )

    const result = await fetchCurrentUser()
    expect(result).toEqual({
      auth_mode: 'local',
      authenticated: true,
      user: { user_name: 'alice', display_name: 'Alice', role: 'admin' },
    })
  })

  it('a network failure resolves to the none/unauthenticated fallback, never throws', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    const result = await fetchCurrentUser()
    expect(result).toEqual({ auth_mode: 'none', authenticated: false, user: null })
  })

  it('a non-OK HTTP response resolves to the fallback', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500 }))

    const result = await fetchCurrentUser()
    expect(result).toEqual({ auth_mode: 'none', authenticated: false, user: null })
  })

  it('a non-JSON body resolves to the fallback', async () => {
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

    const result = await fetchCurrentUser()
    expect(result).toEqual({ auth_mode: 'none', authenticated: false, user: null })
  })

  it('an unrecognized auth_mode value normalizes to none', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(meResponse({ authenticated: false, auth_mode: 'bogus', user: null })),
    )

    const result = await fetchCurrentUser()
    expect(result.auth_mode).toBe('none')
  })
})

describe('recheckAuthAfterStreamFailure — SSE terminal-failure auth discriminator', () => {
  it('redirects to login when /me confirms the session actually dropped', async () => {
    const navigate = vi.fn()
    __setNavigateForTest(navigate)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(meResponse({ authenticated: false, auth_mode: 'oidc', user: null })),
    )
    Object.defineProperty(window, 'location', {
      value: { pathname: '/app/investigations/inv-1', search: '', hash: '' },
      writable: true,
    })

    await recheckAuthAfterStreamFailure()

    expect(navigate).toHaveBeenCalledWith(
      '/auth/login?next=' + encodeURIComponent('/app/investigations/inv-1'),
    )
  })

  it('does NOT redirect when still authenticated (a real connectivity hiccup, not an auth drop)', async () => {
    const navigate = vi.fn()
    __setNavigateForTest(navigate)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        meResponse({
          authenticated: true,
          auth_mode: 'oidc',
          user: { user_name: 'alice', display_name: 'Alice', role: 'user' },
        }),
      ),
    )

    await recheckAuthAfterStreamFailure()

    expect(navigate).not.toHaveBeenCalled()
  })

  it('does NOT redirect in mode none', async () => {
    const navigate = vi.fn()
    __setNavigateForTest(navigate)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(meResponse({ authenticated: false, auth_mode: 'none', user: null })),
    )

    await recheckAuthAfterStreamFailure()

    expect(navigate).not.toHaveBeenCalled()
  })

  it('bypasses any cached mode from a prior apiFetch redirect — always probes fresh', async () => {
    const navigate = vi.fn()
    __setNavigateForTest(navigate)
    const meMock = vi.fn().mockResolvedValue(
      meResponse({ authenticated: true, auth_mode: 'local', user: null }),
    )
    vi.stubGlobal('fetch', meMock)

    await recheckAuthAfterStreamFailure()
    await recheckAuthAfterStreamFailure()

    expect(meMock).toHaveBeenCalledTimes(2)
    expect(navigate).not.toHaveBeenCalled()
  })
})
