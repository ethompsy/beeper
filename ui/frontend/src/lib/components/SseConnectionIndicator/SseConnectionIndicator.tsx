import { cn } from '../../utils/cn'
import type { InvestigationEventsConnectionState } from '../../hooks/useInvestigationEvents'

/**
 * SseConnectionIndicator — the subtle inline indicator below the last
 * investigation step reflecting the SSE 4-state lifecycle (Task 2.6a, FR27;
 * spec "SSE Lifecycle State Pattern" + "12. SSE Reconnecting Indicator").
 *
 * | State          | Visual                                                        |
 * |----------------|------------------------------------------------------------------|
 * | connected      | nothing (spec: "No indicator (default)")                         |
 * | disconnected   | "Reconnecting…" in `text-secondary`, pulsing ellipsis             |
 * | reconnected    | nothing — transient, the hook settles back to connected          |
 * | failed         | "Live updates unavailable — refresh to sync" (Task 2.6b, spec    |
 * |                | "SSE Lifecycle State Pattern" Failed row) with a manual reload   |
 * |                | link — the detail already rendered stays fully viewable; this   |
 * |                | is purely an additive notice, never a replacement for content   |
 *
 * `prefers-reduced-motion`: `animate-pulse` → `motion-reduce:animate-none`,
 * the same pattern used by `RelatedKbPanel`/skeletons — text still reads
 * "Reconnecting…", just without the pulse.
 */
export interface SseConnectionIndicatorProps {
  connectionState: InvestigationEventsConnectionState
  className?: string
}

export function SseConnectionIndicator({ connectionState, className }: SseConnectionIndicatorProps) {
  if (connectionState === 'connected' || connectionState === 'reconnected') {
    return null
  }

  if (connectionState === 'failed') {
    return (
      <p
        data-slot="sse-connection-indicator"
        data-connection-state={connectionState}
        role="status"
        className={cn('text-sm text-status-critical', className)}
      >
        Live updates unavailable — refresh to sync
        {/*
          Spec ("SSE Lifecycle State Pattern", Failed row): "show static
          message with manual location.reload() link". A full reload (not
          client-side navigation) re-runs both the Task 2.5 one-shot fetch
          and re-opens the Task 2.6a stream from scratch — the simplest,
          most reliable way to fully resync once the lifecycle has locked
          into `failed`.
        */}
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="ml-1 text-primary underline hover:no-underline"
        >
          Refresh
        </button>
      </p>
    )
  }

  return (
    <p
      data-slot="sse-connection-indicator"
      data-connection-state={connectionState}
      role="status"
      className={cn(
        'text-sm text-text-secondary animate-pulse motion-reduce:animate-none',
        className,
      )}
    >
      Reconnecting…
    </p>
  )
}
