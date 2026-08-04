# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

## Component library

`src/lib/` is the shadcn-style component library (Radix primitives + Tailwind,
skinned to the Task 1.2 dark-first tokens in `src/theme/tokens.css`) — the
extraction boundary Milestone 1.2 views build against. Public API is the
single barrel `src/lib/index.ts`.

- `npm run build:lib` — builds the library to `dist-lib/` (see `DESIGN_SYNC.md`
  for the full layout + export inventory, used by `/design-sync`).
- `npm run storybook` — dev server with one story per component
  (`src/lib/components/*/*.stories.tsx`).
- `npm run build-storybook` — static Storybook export → `storybook-static/`.

## Testing

- `npm test` — Vitest + React Testing Library (unit/component; `src/**/*.test.{ts,tsx}`).
  Some suites (e.g. `src/lib/test/dist-import.test.ts`) assert against the
  built `dist-lib/` artifact — run `npm run build:lib` first if testing
  locally outside CI.
- `npm run e2e` — Playwright e2e (`e2e/**/*.spec.ts`), driven by
  `playwright.config.ts`. Its `webServer` serves the *production build* via
  `vite preview`, so run `npm run build` first:

  ```sh
  npm run build && npm run e2e
  ```

  First-time setup needs the browser binary: `npx playwright install --with-deps chromium`.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend enabling type-aware lint rules by installing `oxlint-tsgolint` and editing `.oxlintrc.json`:

```json
{
  "$schema": "./node_modules/oxlint/configuration_schema.json",
  "plugins": ["react", "typescript", "oxc"],
  "options": {
    "typeAware": true
  },
  "rules": {
    "react/rules-of-hooks": "error",
    "react/only-export-components": ["warn", { "allowConstantExport": true }]
  }
}
```

See the [Oxlint rules documentation](https://oxc.rs/docs/guide/usage/linter/rules) for the full list of rules and categories.
