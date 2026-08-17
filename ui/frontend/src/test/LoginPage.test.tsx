/**
 * LoginPage.test.tsx (Task 8.6 — ADR 0002 §6, FR59).
 *
 * AC [T]: "/app/login renders (form, error, loading states — vitest/RTL)".
 * Mocks `global.fetch` (matching this codebase's established convention)
 * and intercepts navigation via `__setNavigateForTest` (jsdom does not
 * implement real navigation) — same pattern `src/api/test/http.test.ts`
 * uses for the OTHER direction of this same login/logout handoff.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { LoginPage } from '../routes/LoginPage'
import { __resetApiFetchForTest, __setNavigateForTest } from '../api/http'

function mockFetchOnce(body: unknown, opts: { ok?: boolean; status?: number } = {}) {
  const { ok = true, status = 200 } = opts
  const fetchMock = vi.fn().mockResolvedValue({ ok, status, json: async () => body })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function renderLoginPage(initialEntry = '/app/login') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/app/login" element={<LoginPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

let navigated: string[] = []

beforeEach(() => {
  navigated = []
  __setNavigateForTest((url: string) => navigated.push(url))
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  __resetApiFetchForTest()
})

describe('LoginPage', () => {
  it('renders the login form with a heading', () => {
    renderLoginPage()
    expect(screen.getByRole('heading', { name: 'Sign in to Beeper' })).toBeInTheDocument()
    expect(screen.getByLabelText('Username')).toBeInTheDocument()
    expect(screen.getByLabelText('Password')).toBeInTheDocument()
  })

  it('shows a loading state while the login request is in flight', async () => {
    const user = userEvent.setup()
    let resolveFetch!: (value: unknown) => void
    const fetchMock = vi.fn().mockReturnValue(
      new Promise((resolve) => {
        resolveFetch = resolve
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    renderLoginPage()
    await user.type(screen.getByLabelText('Username'), 'alice')
    await user.type(screen.getByLabelText('Password'), 'hunter22222')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(screen.getByRole('button')).toHaveTextContent('Signing in…')
    expect(screen.getByLabelText('Username')).toBeDisabled()

    resolveFetch({ ok: true, status: 200, json: async () => ({}) })
    await waitFor(() => expect(navigated.length).toBe(1))
  })

  it('a 401 (invalid credentials) response renders the uniform error message and stops loading', async () => {
    const user = userEvent.setup()
    mockFetchOnce(
      {
        type: 'https://beeper.dev/errors/invalid-credentials',
        title: 'Invalid Credentials',
        status: 401,
        detail: 'Invalid username or password.',
        instance: '/api/v1/auth/login',
      },
      { ok: false, status: 401 },
    )

    renderLoginPage()
    await user.type(screen.getByLabelText('Username'), 'nobody')
    await user.type(screen.getByLabelText('Password'), 'wrongpassword')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Invalid username or password.')
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeEnabled()
    expect(navigated).toEqual([])
  })

  it('a network failure renders a generic error, not a crash', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    renderLoginPage()
    await user.type(screen.getByLabelText('Username'), 'alice')
    await user.type(screen.getByLabelText('Password'), 'hunter22222')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Something went wrong. Please try again.')
    expect(navigated).toEqual([])
  })

  it('success with no next= param navigates to /app/investigations', async () => {
    const user = userEvent.setup()
    mockFetchOnce({ authenticated: true, auth_mode: 'local', user: { user_name: 'alice' } })

    renderLoginPage('/app/login')
    await user.type(screen.getByLabelText('Username'), 'alice')
    await user.type(screen.getByLabelText('Password'), 'hunter22222')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => expect(navigated).toEqual(['/app/investigations']))
  })

  it('success with a valid next= param navigates there instead', async () => {
    const user = userEvent.setup()
    mockFetchOnce({ authenticated: true, auth_mode: 'local', user: { user_name: 'alice' } })

    renderLoginPage('/app/login?next=%2Fapp%2Fknowledge')
    await user.type(screen.getByLabelText('Username'), 'alice')
    await user.type(screen.getByLabelText('Password'), 'hunter22222')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => expect(navigated).toEqual(['/app/knowledge']))
  })

  it('an unsafe next= param (open-redirect attempt) falls back to the default', async () => {
    const user = userEvent.setup()
    mockFetchOnce({ authenticated: true, auth_mode: 'local', user: { user_name: 'alice' } })

    renderLoginPage('/app/login?next=' + encodeURIComponent('https://evil.example.com'))
    await user.type(screen.getByLabelText('Username'), 'alice')
    await user.type(screen.getByLabelText('Password'), 'hunter22222')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => expect(navigated).toEqual(['/app/investigations']))
  })

  it('sends the credentials as JSON POST to /api/v1/auth/login', async () => {
    const user = userEvent.setup()
    const fetchMock = mockFetchOnce({ authenticated: true, auth_mode: 'local', user: null })

    renderLoginPage()
    await user.type(screen.getByLabelText('Username'), 'alice')
    await user.type(screen.getByLabelText('Password'), 'hunter22222')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/auth/login')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({ username: 'alice', password: 'hunter22222' })
  })
})
