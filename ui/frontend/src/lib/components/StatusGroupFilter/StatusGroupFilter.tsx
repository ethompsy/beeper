import { cn } from '../../utils/cn'

/**
 * StatusGroupFilter — the FR22 status-group filter control
 * (active/resolved/failed) for the investigation list (Task 2.2).
 *
 * Presentational + controlled: the page owns which group is selected (local
 * component state for now — Task 3.1 lifts this into the URL query string).
 * Deliberately generic over the group id/label pairs passed in rather than
 * importing `StatusGroup` from `src/lib/investigations/status-group.ts`
 * directly, so this library primitive has no dependency on the app's
 * investigation-domain module (keeps `src/lib` a general-purpose component
 * library per the barrel's extraction-boundary contract).
 */
export interface StatusGroupFilterOption {
  id: string
  label: string
  /** Optional count badge (e.g. "Active (3)") — omitted when not provided. */
  count?: number
}

export interface StatusGroupFilterProps {
  options: StatusGroupFilterOption[]
  selectedId: string
  onSelect: (id: string) => void
}

export function StatusGroupFilter({ options, selectedId, onSelect }: StatusGroupFilterProps) {
  return (
    <div
      data-slot="status-group-filter"
      role="tablist"
      aria-label="Filter investigations by status group"
      className="flex items-center gap-1"
    >
      {options.map((option) => {
        const isSelected = option.id === selectedId
        return (
          <button
            key={option.id}
            type="button"
            role="tab"
            aria-selected={isSelected}
            data-state={isSelected ? 'selected' : 'unselected'}
            onClick={() => onSelect(option.id)}
            className={cn(
              'rounded-md px-3 py-1.5 text-sm font-medium transition-colors motion-reduce:transition-none',
              isSelected
                ? 'bg-primary/10 text-primary'
                : 'text-text-secondary hover:bg-surface-overlay hover:text-text-primary',
            )}
          >
            {option.label}
            {option.count != null ? (
              <span className="ml-1 text-text-muted">({option.count})</span>
            ) : null}
          </button>
        )
      })}
    </div>
  )
}
