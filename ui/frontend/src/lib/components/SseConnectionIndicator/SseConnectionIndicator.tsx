import { cn } from '../../utils/cn'
import type { InvestigationEventsConnectionState } from '../../hooks/useInvestigationEvents'

/**
 * SseConnectionIndicator — the subtle inline indicator below the last
 * investigation step reflecting the SSE 4-state lifecycle (Task 2.6a, FR27;
 * spec "SSE Lifecycle State Pattern" + "12. SSE Reconnecting Indicator").
 *
 * | State          | Visual                                                     |
 * |----------------|-------------------------------------------------------------|
 * | connected      | nothing (spec: "No indicator (default)")                    |
 * | disconnected   | "Reconnecting…" in `text-secondary`, pulsing ellipsis        |
 * | reconnected    | nothing — transient, the hook settles back to connected     |
 * | failed         | plain "Live updates unavailable" notice (Task 2.6b owns the |
 * |                | full "— refresh to sync" copy + reload link; this task only |
 * |                | needs the lifecycle to be observably reachable)             |
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
        Live updates unavailable
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
