/**
 * SpendingPage — route scaffolding placeholder (Task 5.0b).
 *
 * Placeholder — Task 5.3 replaces this file's implementation with the real
 * LLM Spending view (`/app/spending`, per
 * docs/design/route-parity-targets.md §4b). Renders only an honest
 * "not yet migrated" notice inside the shell — nothing here should be
 * mistaken for the finished feature.
 */
export function SpendingPage() {
  return (
    <div data-testid="spending-page" className="flex flex-col gap-2">
      <h1 className="text-2xl font-semibold text-text-primary">Spending</h1>
      <p className="text-sm text-text-secondary">This view has not been migrated to React yet.</p>
    </div>
  )
}
