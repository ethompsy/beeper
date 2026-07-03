# DESIGN_SYNC — `/design-sync` input contract for the Beeper component library

**Status:** produced by Task 1.4. The trial `/design-sync` ingest run itself is
**`[H]` PENDING** — it requires the main session's `/design-sync` tooling,
which is not available inside this worktree/agent. This document describes
what to feed it and what to expect, so the parent session can run the trial
and resolve Q3 (`docs/plans/react-ui.md`).

---

## 1. Build command

```sh
cd ui/frontend
npm install        # first time only
npm run build:lib
```

This runs `tsc -b && vite build --config vite.lib.config.ts` and produces the
`dist-lib/` directory described below. It is a **separate** build from the
app bundle (`npm run build` → `dist/`, unchanged from Task 1.1) — `dist-lib/`
is the artifact `/design-sync` should ingest, not `dist/`.

Re-run `npm run build:lib` any time library source under `src/lib/**`
changes; `emptyOutDir: true` means the directory is wiped and regenerated
each time (no stale files).

To browse the components interactively instead of / in addition to reading
the bundle:

```sh
npm run storybook        # dev server, http://localhost:6006
npm run build-storybook  # static export → storybook-static/
```

Every library component has at least one Storybook story (see §4); Storybook
is a convenient companion for a human or Claude Design reviewer, but the
`/design-sync` ingest contract described here is about `dist-lib/`, the
compiled bundle.

## 2. `dist-lib/` layout

```
dist-lib/
├── index.js                                    # single ESM bundle, all components + cn
├── index.d.ts                                   # barrel type declarations (re-exports below)
├── utils/
│   └── cn.d.ts
└── components/
    ├── InvestigationCard/
    │   ├── InvestigationCard.d.ts
    │   └── index.d.ts
    ├── StatusBadge/
    │   ├── StatusBadge.d.ts
    │   └── index.d.ts
    ├── InvestigationStep/
    │   ├── InvestigationStep.d.ts
    │   └── index.d.ts
    ├── SummaryHeader/
    │   ├── SummaryHeader.d.ts
    │   └── index.d.ts
    └── RelatedKbPanel/
        ├── RelatedKbPanel.d.ts
        └── index.d.ts
```

Notes on the shape:

- **One JS entry, many type-declaration files.** The runtime code is bundled
  into a single `index.js` (component internals are not meant to be imported
  individually at the JS level — always import from the package root). The
  `.d.ts` tree mirrors the source `src/lib/` structure because
  `bundleTypes: false` is set (declaration bundling via API Extractor was
  evaluated and skipped — see §5); this does not change the *import* contract
  (still import from the root), it only affects how the types are laid out on
  disk.
- **No CSS file.** Every component is styled with Tailwind utility classes
  authored against the Task 1.2 tokens (`src/theme/tokens.css`) and compiled
  by whatever Tailwind pipeline is already running in the consuming app (in
  this repo, `ui/frontend`'s own Tailwind v4 build via `@tailwindcss/vite`).
  The library does not ship a separate compiled stylesheet — a consumer that
  is NOT already running Tailwind against these class names (e.g. a fully
  external tool ingesting only `dist-lib/`) will see the component tree
  structure and class names but unstyled output, unless it also has access
  to `src/theme/tokens.css` (Task 1.2) to compile the same utility classes.
  **This is the crux of Q3** — see §5 for what "ingest" likely means for
  `/design-sync` in practice.
- **No public assets.** `dist-lib/` intentionally excludes the app's
  `public/` directory (favicon, sidebar icon sprite) — those are app-shell
  concerns, not library concerns. (Vite's default lib-mode build copies
  `publicDir` into every output; this config disables that via
  `publicDir: false` in `vite.lib.config.ts`.)
- **react / react-dom externalized.** `dist-lib/index.js` imports `react` /
  `react-dom` / `react/jsx-runtime` as bare specifiers rather than bundling
  them (`rollupOptions.external` in `vite.lib.config.ts`) — matching the
  shadcn-style "copied-in primitives, bring your own React" approach (plan
  decision D3). A consumer must have `react`/`react-dom` ^19 available.

## 3. Export inventory (the `/design-sync` input surface)

All exports are importable from the single package root — i.e. an external
consumer does:

```ts
import { InvestigationCard, StatusBadge, InvestigationStep, SummaryHeader, RelatedKbPanel, cn } from '<path-to>/dist-lib/index.js'
```

| Export | Kind | Props (summary) | Notes |
|---|---|---|---|
| `InvestigationCard` | Component | `variant: 'active' \| 'completed' \| 'failed'`, `serviceName`, `severity`, `signalCount`, `timestamp`, `statusVariant`, `href`, ...`<a>` attrs | List-item primitive. One story per variant. |
| `StatusBadge` | Component | `variant: StatusBadgeVariant` (14-value union spanning job-phase / workflow-state / pipeline-health), `label?`, ...`<span>` attrs | Single component covers all status/phase/workflow variants per `docs/design/terminology-glossary.md`. Job-phase `Failed` → variant `analysis-failed` → label **"Analysis Failed"**; workflow-state `Failed` → variant `failed` → label **"Failed"** (glossary OD-1: two distinct variants, same underlying word, disambiguated by axis). |
| `InvestigationStep` | Component | `type: 'metric' \| 'log' \| 'deploy' \| 'kb' \| 'correlation' \| 'summary'`, `order`, `description`, `evidence?`, `isFirstEvidence?`, ...`<li>` attrs | Evidence-timeline primitive; `evidence` is a free-form `ReactNode` slot (rendering of monospace values/log excerpts is the caller's concern). |
| `SummaryHeader` | Component | `serviceName`, `severity`, `signalCount`, `statusVariant`, `timestamp?`, `problemState?`, ...`<header>` attrs | Investigation-detail hero; renders the page `<h1>`. No SSE dependency (renders from metadata). |
| `RelatedKbPanel` | Component | `state: 'loading' \| 'populated' \| 'zero'`, `entryCount`, `expanded?`, `onExpandedChange?`, `children?` | Built on `@radix-ui/react-collapsible` for accessible expand/collapse. Anchored-bar vs. inline-stack responsive placement is a layout concern (Milestone 1.2), not internal to this component. |
| `cn` | Utility function | `(...inputs: ClassValue[]) => string` | `clsx` + `tailwind-merge` composition helper — the one shared utility every component (and consumers extending them) is built on. |

Every component above also exports its **props type** (e.g.
`InvestigationCardProps`, `StatusBadgeVariant`) from the same root — these
are visible in `index.d.ts` and are part of the ingest surface for a
type-aware tool.

### Full variant/state inventory (for a renderer that wants to enumerate every visual state)

- **`InvestigationCard.variant`:** `active`, `completed`, `failed`
- **`StatusBadge.variant`:** `investigating`, `awaiting-confirmation`,
  `completed`, `analysis-failed`, `pending`, `detected`, `resolved`,
  `verified`, `failed`, `healthy`, `warning`, `critical`, `warming-up`,
  `no-data`
- **`InvestigationStep.type`:** `metric`, `log`, `deploy`, `kb`,
  `correlation`, `summary` (plus the boolean `isFirstEvidence` emphasis state)
- **`RelatedKbPanel.state`:** `loading`, `populated`, `zero` (plus the
  boolean `expanded`)

This matches the Task 4.4 design-sync inventory target: `InvestigationCard`
(active/completed/failed), `StatusBadge` (all variants), `InvestigationStep`,
`SummaryHeader`, `RelatedKbPanel`.

## 4. Storybook story map

One skeleton story file per component under
`src/lib/components/<Name>/<Name>.stories.tsx`:

| Component | Stories |
|---|---|
| `InvestigationCard` | `Active`, `Completed`, `Failed` |
| `StatusBadge` | `Default`, `JobPhaseVariants`, `WorkflowStateVariants`, `PipelineHealthVariants` |
| `InvestigationStep` | `MetricQuery`, `LogQuery`, `KbQuery`, `Correlation`, `Summary`, `FirstEvidence` |
| `SummaryHeader` | `Investigating`, `Completed`, `AnalysisFailed` |
| `RelatedKbPanel` | `Loading`, `Populated`, `PopulatedExpanded`, `ZeroEntries` |

## 5. Open items for the trial run (resolving Q3)

The trial `/design-sync` run should establish, concretely:

1. **Does `/design-sync` execute the bundle (needs React + a DOM), or does it
   statically analyze it (reads JS/types, renders nothing)?** If it executes
   the bundle, it will need a host page that also loads
   `src/theme/tokens.css` (or an equivalent compiled stylesheet) for the
   Tailwind utility classes referenced by `className` strings to have any
   visual effect — the bundle alone carries no CSS. Recommended trial input
   if execution is supported: point `/design-sync` at `ui/frontend`'s
   Storybook build (`storybook-static/`) instead of/in addition to raw
   `dist-lib/`, since Storybook already wires the tokens stylesheet per
   story (see `.storybook/preview.ts`).
2. **Whether `/design-sync` wants declaration-bundled types** (a single
   flattened `.d.ts` via `@microsoft/api-extractor`, `bundleTypes: true` in
   `vite.lib.config.ts`) **or is fine with the mirrored per-component `.d.ts`
   tree** shipped today. Flip `bundleTypes: true` (after adding
   `@microsoft/api-extractor` as a dev dependency) if the trial shows the
   tool wants one file.
3. **Whether `/design-sync` needs a `package.json` at the `dist-lib/` root**
   (name/version/exports map) to treat it as an installable package, or
   whether pointing it at the directory + `index.js`/`index.d.ts` directly is
   sufficient. None is shipped today since nothing in the plan asked for
   one; add one if the trial run indicates it's expected.

Record the resolution of these three questions as the Q3 answer in
`docs/plans/react-ui.md` after the trial run.
