# design-sync notes — Beeper Design System

- Project: "Beeper Design System" (id 616ba082-ca5d-41b0-a272-5d015a613885) — created 2026-07-30, first sync.
- Config schema is strict: no extra keys (e.g. `projectName` is rejected) — keep human labels here, not in config.json.
- [GENERAL] 0 exports found on first build: `ui/frontend` is an app manifest with no `types` field, and the lib d.ts tree lives at `dist-lib/` (not in findTypesRoot's fallback list). Fixed by adding `"types": "dist-lib/index.d.ts"` to ui/frontend/package.json (inert for the Vite app). Converter entry is `--entry ui/frontend/dist-lib/index.js`.
- CSS: dist-lib ships no CSS by design (Tailwind tokens compiled at app level) — `[CSS_FROM_STORYBOOK]` correctly scrapes the compiled sheet from sb-reference. Expected on every build.
- [FONT_MISSING] "Cascadia Code"/"Fira Code"/"Ubuntu Mono": mono FALLBACK-stack members from tokens.css (`--font-mono: ui-monospace, 'SF Mono', …`). The DS deliberately uses system font stacks — no shipped webfont exists; substitutes accepted by design. Triaged; expect this warn every sync.
- SseConnectionIndicator: `Connected`/`Reconnected` stories render **null by design** (spec: "no indicator when connected") → skipped via overrides; Disconnected + Failed carry the card.
- StepEvidence: `Empty` story renders null by design (absent evidence) → skipped; `MetricValue` renders wide → cardMode "column".
- AppShell/Sidebar: fixed-position layout components → cardMode "single" (AppShell primary ExpandedPushing, Sidebar primary Expanded).
- StatusGroupFilter [RENDER_THIN] "variants identical": both stories emit identical TEXT (Active(3)Resolved(12)Failed(1)); the visual delta is the selected-tab highlight — verify in compare, don't author an owned preview for this alone.
- [GENERAL] Dark-first canvas: storybook paints #0f0f1a via the backgrounds addon and the app via tokens.css's LAYERED body rule — the sync harness's unlayered white body wins over both, so every preview rendered light-on-white. Fix: `src/lib/preview/DarkCanvas.tsx` (token-var canvas mirroring the body rule; NOT in the lib barrel) + `cfg.extraEntries` + `cfg.provider {"component":"DarkCanvas"}`. Do not delete that file — the provider names it.
- [GENERAL] DarkCanvas must have padding 0: AppShell/Sidebar use position:fixed (viewport-anchored), so canvas padding displaces flow content (top bar) against the fixed sidebar → overlap artifacts. Padding-0 costs only framing on normal components.
- InvestigationStep has 7 stories — run compare with `--max-stories 7` (default cap is 6; the 7th is a distinct variant).

## Re-sync risks (2026-07-30 first sync)

- `ui/frontend/package.json` `"types": "dist-lib/index.d.ts"` is load-bearing for export discovery — removing it returns the build to 0 components.
- `DarkCanvas.tsx` (provider) mirrors tokens.css's body rule with padding 0 — if tokens.css's body rule changes (colors/fonts), DarkCanvas follows via var()s automatically, but structural changes (new body padding) need a manual mirror. It ships via extraEntries; deleting it breaks `cfg.provider`.
- Verified partially: InvestigationStep graded at `--max-stories 7` (all 7); future story additions past the cap re-need the flag. SseConnectionIndicator Connected/Reconnected + StepEvidence Empty are skipped (null by design) — if those stories gain visible UI, unskip.
- Accepted warns every sync: [FONT_MISSING] (system mono fallback stack by design), [RENDER_THIN] StatusGroupFilter (stories differ only by interaction).
- SummaryHeader "Analysis Failed" story: Critical chip renders amber on BOTH sides — upstream component bug (severity-color hardcoded to warning), tracked as a repo follow-up chip; when fixed upstream, the story re-grades automatically (source change).
- Toolchain assumed: Node 24 / npm 11; sb-reference must be rebuilt whenever src/lib or stories change (driver warns [REFERENCE_STALE?]).
