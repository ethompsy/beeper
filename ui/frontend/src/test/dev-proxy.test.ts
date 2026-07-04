/**
 * dev-proxy.test.ts
 *
 * AC [T] (Task 1.5) — `vite dev` proxies `/api/*` and the JSON event endpoint
 * (`/api/v1/investigations/{id}/events`) to the Flask BFF, with SSE/streaming
 * buffering disabled so the event stream flows through the proxy in real time.
 *
 * Strategy (matches this repo's static-source-assertion convention, see e.g.
 * lint-enforcement.test.ts / token-resolution.test.tsx): rather than booting a
 * real dev server + stub BFF in the Vitest process (slow, flaky across CI
 * runners, and duplicative — this was verified manually against a live `vite
 * dev` + stub SSE server during development), resolve the *actual*
 * `vite.config.ts` via Vite's own `resolveConfig` API and assert on the
 * resulting `server.proxy` object. This proves the config Vite will actually
 * use at dev-server boot time — not a hand-parsed re-implementation of it.
 *
 * What "no buffering" means here and how it's asserted:
 *   - The events-path proxy entry must NOT set `selfHandleResponse: true`.
 *     `selfHandleResponse: true` suppresses http-proxy's automatic per-chunk
 *     pipe-through and requires the response to be written manually — the
 *     easy way to accidentally buffer a whole SSE response before forwarding
 *     it. Leaving it `false` (or unset) is exactly what preserves streaming.
 *   - The `configure` hook must be present and, when invoked against a mock
 *     proxy/req/res, must set `Cache-Control: no-cache` and
 *     `X-Accel-Buffering: no` on the proxied response — the two headers that
 *     tell any intermediary (and the BFF's own response, defensively) not to
 *     buffer the stream. This is exercised directly (not just grepped for in
 *     source) by invoking `configure()` with fake EventEmitter-like proxy
 *     objects and checking the header side effects.
 */

import { describe, it, expect, vi } from 'vitest'
import { resolveConfig } from 'vite'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)
const CONFIG_FILE = resolve(__dirname, '../../vite.config.ts')

type ProxyOptions = {
  target?: string
  changeOrigin?: boolean
  ws?: boolean
  selfHandleResponse?: boolean
  configure?: (proxy: FakeProxy, options: unknown) => void
}

/** Minimal fake of http-proxy's event-emitter interface for exercising `configure`. */
class FakeProxy {
  private handlers: Record<string, Array<(...args: unknown[]) => void>> = {}
  on(event: string, handler: (...args: unknown[]) => void): void {
    (this.handlers[event] ??= []).push(handler)
  }
  emit(event: string, ...args: unknown[]): void {
    for (const handler of this.handlers[event] ?? []) handler(...args)
  }
}

async function getProxyConfig(): Promise<Record<string, ProxyOptions>> {
  const resolved = await resolveConfig({ configFile: CONFIG_FILE }, 'serve')
  const proxy = resolved.server?.proxy as Record<string, ProxyOptions> | undefined
  expect(proxy, 'expected server.proxy to be defined in vite.config.ts').toBeDefined()
  return proxy!
}

describe('vite dev proxy → Flask BFF (Task 1.5)', () => {
  it('proxies the JSON event stream endpoint to the BFF origin with changeOrigin', async () => {
    const proxy = await getProxyConfig()
    const eventsKey = Object.keys(proxy).find((k) => k.includes('events'))
    expect(eventsKey, 'expected a proxy entry targeting the /events path').toBeDefined()

    const entry = proxy[eventsKey!]
    expect(entry.target).toMatch(/^https?:\/\//)
    expect(entry.changeOrigin).toBe(true)
  })

  it('the events-path proxy entry keeps the default streaming pipe-through (no selfHandleResponse)', async () => {
    const proxy = await getProxyConfig()
    const eventsKey = Object.keys(proxy).find((k) => k.includes('events'))!
    const entry = proxy[eventsKey]

    // selfHandleResponse: true would suppress http-proxy's automatic
    // per-chunk pipe and require writing the response manually — the
    // classic way SSE ends up buffered. It must be falsy here.
    expect(entry.selfHandleResponse).toBeFalsy()
  })

  it('the events-path proxy entry disables buffering via its configure hook', async () => {
    const proxy = await getProxyConfig()
    const eventsKey = Object.keys(proxy).find((k) => k.includes('events'))!
    const entry = proxy[eventsKey]

    expect(typeof entry.configure).toBe('function')

    const fakeProxy = new FakeProxy()
    entry.configure!(fakeProxy, {})

    // Exercise the proxyReq hook.
    const fakeProxyReq = { setHeader: vi.fn() }
    fakeProxy.emit('proxyReq', fakeProxyReq)
    expect(fakeProxyReq.setHeader).toHaveBeenCalledWith('Cache-Control', 'no-cache')

    // Exercise the proxyRes hook.
    const fakeProxyRes = { headers: {} as Record<string, string> }
    fakeProxy.emit('proxyRes', fakeProxyRes)
    expect(fakeProxyRes.headers['cache-control']).toBe('no-cache')
    expect(fakeProxyRes.headers['x-accel-buffering']).toBe('no')
  })

  it('a general /api rule proxies list/detail JSON endpoints to the same BFF origin', async () => {
    const proxy = await getProxyConfig()
    const apiKey = Object.keys(proxy).find((k) => k === '/api')
    expect(apiKey, 'expected a general /api proxy entry for list/detail JSON routes').toBeDefined()

    const entry = proxy[apiKey!]
    expect(entry.target).toMatch(/^https?:\/\//)
    expect(entry.changeOrigin).toBe(true)

    // Both entries must point at the same BFF origin.
    const eventsKey = Object.keys(proxy).find((k) => k.includes('events'))!
    expect(entry.target).toBe(proxy[eventsKey].target)
  })

  it('the events proxy key matches the real endpoint path and does not match the list/detail paths', async () => {
    const proxy = await getProxyConfig()
    const eventsKey = Object.keys(proxy).find((k) => k.includes('events'))!

    // Vite treats a proxy key starting with `^` as a RegExp source; anything
    // else is a literal prefix match. Reconstruct the same matching Vite uses.
    const matcher = eventsKey.startsWith('^') ? new RegExp(eventsKey) : null
    const test = (path: string) =>
      matcher ? matcher.test(path) : path.startsWith(eventsKey)

    expect(test('/api/v1/investigations/abc-123/events')).toBe(true)
    expect(test('/api/v1/investigations')).toBe(false)
    expect(test('/api/v1/investigations/abc-123')).toBe(false)
  })
})
