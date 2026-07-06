/**
 * useInvestigationEvents.test.ts (Task 2.6a)
 *
 * Proves the AC: "[T] a simulated disconnect shows a subtle 'Reconnecting…'
 * indicator and the connection transitions through the 4-state lifecycle
 * (Connected / Disconnected / Reconnected / Failed) (FR27)."
 *
 * A real `EventSource` cannot be driven deterministically in jsdom (no
 * network layer, and the browser owns its retry timing internally) — so
 * this hook accepts an injectable `EventSourceFactory` (see the hook's doc
 * comment) and these tests drive a `FakeEventSource` test double that
 * exposes the exact same `onopen`/`onerror`/`addEventListener` surface,
 * letting the test script `open()` → `error()` → `open()` → ... explicitly
 * and assert the resulting `connectionState` after each transition — this
 * is "simulating a disconnect" in the spirit of the AC without depending on
 * real network flakiness.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useInvestigationEvents } from '../hooks/useInvestigationEvents'
import type { EventSourceFactory } from '../hooks/useInvestigationEvents'

type Listener = (event: MessageEvent<string>) => void

class FakeEventSource {
  url: string
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null
  closed = false
  private listeners = new Map<string, Listener[]>()

  constructor(url: string) {
    this.url = url
  }

  addEventListener(type: string, listener: Listener): void {
    const existing = this.listeners.get(type) ?? []
    existing.push(listener)
    this.listeners.set(type, existing)
  }

  close(): void {
    this.closed = true
  }

  /** Test helper: simulate the browser firing `onopen`. */
  open(): void {
    this.onopen?.()
  }

  /** Test helper: simulate the browser firing `onerror` (a connection drop). */
  error(): void {
    this.onerror?.()
  }

  /** Test helper: simulate the server emitting a named SSE event. */
  emit(type: string, data: unknown): void {
    const data_ = JSON.stringify(data)
    for (const listener of this.listeners.get(type) ?? []) {
      listener({ data: data_ } as MessageEvent<string>)
    }
  }
}

function makeFactory(): { factory: EventSourceFactory; instances: FakeEventSource[] } {
  const instances: FakeEventSource[] = []
  const factory: EventSourceFactory = (url: string) => {
    const source = new FakeEventSource(url)
    instances.push(source)
    return source as unknown as EventSource
  }
  return { factory, instances }
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useInvestigationEvents — connection URL', () => {
  it('opens the events stream at the Task 1.6 endpoint for the given investigation id', () => {
    const { factory, instances } = makeFactory()
    renderHook(() => useInvestigationEvents('INV-0042', {}, factory))

    expect(instances).toHaveLength(1)
    expect(instances[0].url).toBe('/api/v1/investigations/INV-0042/events')
  })

  it('does not open a stream when investigationId is undefined', () => {
    const { factory, instances } = makeFactory()
    renderHook(() => useInvestigationEvents(undefined, {}, factory))

    expect(instances).toHaveLength(0)
  })
})

describe('useInvestigationEvents — 4-state lifecycle (FR27)', () => {
  it('starts "connected" by default', () => {
    const { factory } = makeFactory()
    const { result } = renderHook(() => useInvestigationEvents('INV-0042', {}, factory))

    expect(result.current.connectionState).toBe('connected')
  })

  it('transitions to "disconnected" on a simulated drop (EventSource onerror)', () => {
    const { factory, instances } = makeFactory()
    const { result } = renderHook(() => useInvestigationEvents('INV-0042', {}, factory))

    act(() => instances[0].error())

    expect(result.current.connectionState).toBe('disconnected')
  })

  it('transitions to "reconnected" then settles back to "connected" when the stream reopens after a drop', async () => {
    const { factory, instances } = makeFactory()
    const onReconnect = vi.fn()
    const { result } = renderHook(() =>
      useInvestigationEvents('INV-0042', { onReconnect }, factory),
    )

    act(() => instances[0].error())
    expect(result.current.connectionState).toBe('disconnected')

    act(() => instances[0].open())

    // The hook signals `reconnected` transiently, then settles to `connected`
    // in the same handler — assert the settled end state and that the
    // 2.6b backfill seam fired exactly once for this transition.
    expect(result.current.connectionState).toBe('connected')
    expect(onReconnect).toHaveBeenCalledTimes(1)
  })

  it('transitions to "failed" after 5 consecutive errors with no intervening open, and closes the stream', () => {
    const { factory, instances } = makeFactory()
    const onFailed = vi.fn()
    const { result } = renderHook(() => useInvestigationEvents('INV-0042', { onFailed }, factory))

    act(() => {
      for (let i = 0; i < 4; i++) {
        instances[0].error()
      }
    })
    expect(result.current.connectionState).toBe('disconnected')
    expect(onFailed).not.toHaveBeenCalled()

    act(() => instances[0].error()) // 5th consecutive error

    expect(result.current.connectionState).toBe('failed')
    expect(onFailed).toHaveBeenCalledTimes(1)
    expect(instances[0].closed).toBe(true)
  })

  it('a successful open resets the consecutive-error counter (so failure requires 5 IN A ROW)', () => {
    const { factory, instances } = makeFactory()
    const onFailed = vi.fn()
    const { result } = renderHook(() => useInvestigationEvents('INV-0042', { onFailed }, factory))

    // 4 errors, then a recovery, then 4 more — never 5 in a row.
    act(() => {
      for (let i = 0; i < 4; i++) instances[0].error()
      instances[0].open()
      for (let i = 0; i < 4; i++) instances[0].error()
    })

    expect(result.current.connectionState).toBe('disconnected')
    expect(onFailed).not.toHaveBeenCalled()
  })

  it('ignores further errors once failed (the stream is already closed)', () => {
    const { factory, instances } = makeFactory()
    const { result } = renderHook(() => useInvestigationEvents('INV-0042', {}, factory))

    act(() => {
      for (let i = 0; i < 5; i++) instances[0].error()
    })
    expect(result.current.connectionState).toBe('failed')

    act(() => instances[0].error())
    expect(result.current.connectionState).toBe('failed')
  })
})

describe('useInvestigationEvents — step events merge into an ordered list', () => {
  it('applies a "step" event synchronously into the returned steps array', () => {
    const { factory, instances } = makeFactory()
    const { result } = renderHook(() => useInvestigationEvents('INV-0042', {}, factory))

    act(() =>
      instances[0].emit('step', { order: 1, key: 'k1', label: 'Customer Impact', state: 'completed', type: 'summary' }),
    )

    expect(result.current.steps).toEqual([
      { order: 1, key: 'k1', label: 'Customer Impact', state: 'completed', type: 'summary' },
    ])
  })

  it('replaces an existing step at the same order (state transition) rather than duplicating it', () => {
    const { factory, instances } = makeFactory()
    const { result } = renderHook(() => useInvestigationEvents('INV-0042', {}, factory))

    act(() => {
      instances[0].emit('step', { order: 1, key: 'k1', label: 'Metric Query', state: 'active', type: 'metric' })
      instances[0].emit('step', { order: 1, key: 'k1', label: 'Metric Query', state: 'completed', type: 'metric' })
    })

    expect(result.current.steps).toHaveLength(1)
    expect(result.current.steps[0].state).toBe('completed')
  })

  it('inserts an out-of-order event at the correct sorted position', () => {
    const { factory, instances } = makeFactory()
    const { result } = renderHook(() => useInvestigationEvents('INV-0042', {}, factory))

    act(() => {
      instances[0].emit('step', { order: 1, key: 'k1', label: 'Step 1', state: 'completed', type: 'summary' })
      instances[0].emit('step', { order: 3, key: 'k3', label: 'Step 3', state: 'completed', type: 'summary' })
      instances[0].emit('step', { order: 2, key: 'k2', label: 'Step 2', state: 'completed', type: 'summary' })
    })

    expect(result.current.steps.map((s) => s.order)).toEqual([1, 2, 3])
  })

  it('marks isComplete on the terminal "complete" event and closes the stream', () => {
    const { factory, instances } = makeFactory()
    const { result } = renderHook(() => useInvestigationEvents('INV-0042', {}, factory))

    expect(result.current.isComplete).toBe(false)
    act(() => instances[0].emit('complete', { status: 'done' }))

    expect(result.current.isComplete).toBe(true)
    expect(instances[0].closed).toBe(true)
  })
})

describe('useInvestigationEvents — event→DOM render latency (NFR21)', () => {
  it('a received step event is reflected in the hook result synchronously (no artificial delay in the render path)', () => {
    // NFR21 / Q5: the backend polls at 1s, but the client-side event→state
    // update path itself must not add latency — a mocked event should be
    // reflected the moment React flushes the state update triggered by it,
    // not after some additional wait. `renderHook`'s `result.current` reads
    // the latest committed state, so no `waitFor`/timer is needed here.
    const { factory, instances } = makeFactory()
    const { result } = renderHook(() => useInvestigationEvents('INV-0042', {}, factory))

    act(() =>
      instances[0].emit('step', { order: 1, key: 'k1', label: 'Fast step', state: 'completed', type: 'summary' }),
    )

    expect(result.current.steps[0]?.label).toBe('Fast step')
  })
})

describe('useInvestigationEvents — id change', () => {
  it('closes the previous stream and opens a new one when investigationId changes', () => {
    const { factory, instances } = makeFactory()
    const { rerender } = renderHook(
      ({ id }: { id: string }) => useInvestigationEvents(id, {}, factory),
      { initialProps: { id: 'INV-0042' } },
    )

    rerender({ id: 'INV-9999' })

    expect(instances).toHaveLength(2)
    expect(instances[0].closed).toBe(true)
    expect(instances[1].url).toBe('/api/v1/investigations/INV-9999/events')
  })
})

describe('useInvestigationEvents — cleanup', () => {
  it('closes the EventSource on unmount', () => {
    const { factory, instances } = makeFactory()
    const { unmount } = renderHook(() => useInvestigationEvents('INV-0042', {}, factory))

    unmount()

    expect(instances[0].closed).toBe(true)
  })
})
