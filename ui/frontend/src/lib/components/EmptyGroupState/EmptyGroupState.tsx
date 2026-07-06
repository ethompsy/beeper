/**
 * EmptyGroupState — the FR22 "waiting state" shown when a status group has
 * no investigations (Task 2.2).
 *
 * Per docs/specs/ux-design-specification.md "Loading & Empty" /
 * "Empty states": "Never blank... Investigation list shows a waiting state
 * before first detection. Absence is always explained." Mirrors the legacy
 * Jinja `empty_state()` macro's title+description shape
 * (`ui/beeper_ui/templates/investigations/_list_content.html`).
 */
export interface EmptyGroupStateProps {
  title: string
  description: string
}

export function EmptyGroupState({ title, description }: EmptyGroupStateProps) {
  return (
    <div
      data-slot="empty-group-state"
      role="status"
      className="flex flex-col items-center gap-2 rounded-md border border-surface-overlay bg-surface-raised p-8 text-center"
    >
      <svg
        viewBox="0 0 48 48"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
        className="h-10 w-10 text-text-muted"
      >
        <circle cx="24" cy="24" r="20" stroke="currentColor" strokeWidth="2" />
        <path d="M24 14v12M24 34v.5" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
      </svg>
      <p className="text-base font-semibold text-text-primary">{title}</p>
      <p className="text-sm text-text-secondary">{description}</p>
    </div>
  )
}
