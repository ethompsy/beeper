# Beeper Design System — build conventions

Beeper is a **dark-first** SRE incident-triage UI. There is no light theme.

## Canvas setup (required)

Every screen must sit on the dark canvas or components will render on the
wrong background. Paint the app root with the tokens (they ship in
`styles.css` → `_ds_bundle.css`):

```jsx
<div style={{ minHeight: '100vh', backgroundColor: 'var(--color-surface-base)',
              color: 'var(--color-text-primary)', fontFamily: 'var(--font-sans)' }}>
  {/* your screen */}
</div>
```

A prebuilt wrapper `DarkCanvas` is exported (`window.BeeperDS.DarkCanvas`) that
does exactly this — `<DarkCanvas>…</DarkCanvas>` is the preferred root.
No other provider is required: components are self-contained (Sidebar embeds
its own tooltip provider), and none require React Router — `Sidebar`,
`AppShell`, and `InvestigationCard` take a `linkComponent` prop to integrate
any navigation; plain `<a>` is the default.

## Styling idiom — Tailwind utilities over CSS-variable tokens

Style ONLY with these token-backed utility families (all present in the
shipped CSS). Never hardcode hex colors, px paddings, or ms durations.

| Family | Names | Use |
|---|---|---|
| Surfaces | `bg-surface-base` `bg-surface-raised` `bg-surface-overlay` | page < card < popover elevation (shade, not shadow) |
| Text | `text-text-primary` `text-text-secondary` `text-text-muted` | content / labels / de-emphasis |
| Interactive | `text-primary` (indigo) | links, active nav, focus accents |
| Status | `--color-status-healthy/-warning/-critical/-muted` via `var()` | health & severity color |
| Step accents | `border-l-step-metric/-log/-kb/-correlation/-summary` | evidence-type left borders |
| Type | `font-mono` for ALL real data (metric values, log lines); `var(--font-sans)` elsewhere | evidence is always monospace |
| Motion | `transition-sidebar` + always pair `motion-reduce:transition-none` | 200ms; reduced-motion is mandatory |
| Breakpoints | `sm:` = 768px, `lg:` = 1200px | sidebar expands at `lg` |

Any utility not in the compiled sheet does not exist at runtime — when in
doubt, use an inline `style` with a `var(--color-*)`/`var(--font-*)` token
reference instead of inventing a class name.

## Where the truth lives

- `styles.css` (+ its `_ds_bundle.css` import) — the full compiled token +
  utility sheet. Read it before styling.
- `components/library/<Name>/<Name>.prompt.md` — per-component usage;
  `<Name>.d.ts` — the props contract.

## Idiomatic example (verified render)

```jsx
const { DarkCanvas, InvestigationCard, StatusGroupFilter } = window.BeeperDS;

<DarkCanvas>
  <main className="mx-auto max-w-4xl p-6 flex flex-col gap-4">
    <StatusGroupFilter
      options={[
        { id: 'active', label: 'Active', count: 3 },
        { id: 'resolved', label: 'Resolved', count: 12 },
        { id: 'failed', label: 'Failed', count: 1 },
      ]}
      selectedId="active" onSelect={() => {}} />
    <InvestigationCard variant="active" serviceName="checkout-service"
      severity="High" statusVariant="investigating" signalCount={3}
      timestamp="2m ago" href="#"
      problemState="HTTP 5xx error rate elevated (12%)" />
  </main>
</DarkCanvas>
```

Terminology: job-phase failure renders **"Analysis Failed"**; workflow failure
renders **"Failed"** — `StatusBadge` encodes this; don't relabel.
