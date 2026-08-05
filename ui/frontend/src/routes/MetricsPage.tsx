/**
 * MetricsPage — route scaffolding placeholder (Task 5.0b).
 *
 * Placeholder — Task 5.4 replaces this file's implementation with the real
 * Metrics (MTTR dashboard) view (`/app/metrics`, per
 * docs/design/route-parity-targets.md §5). Renders only an honest
 * "not yet migrated" notice inside the shell — nothing here should be
 * mistaken for the finished feature.
 */
export function MetricsPage() {
  return (
    <div data-testid="metrics-page" className="flex flex-col gap-2">
      <h1 className="text-2xl font-semibold text-text-primary">Metrics</h1>
      <p className="text-sm text-text-secondary">This view has not been migrated to React yet.</p>
    </div>
  )
}
