import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import unplugin from 'unplugin-dts'
import { resolve } from 'node:path'

const dts = unplugin.vite

/**
 * Library-mode build config (Task 1.4) — separate from `vite.config.ts`
 * (the app build) by design, so Task 1.5's dev-proxy addition to the app
 * config never collides with this one.
 *
 * Builds `src/lib/index.ts` → `dist-lib/` as an ESM bundle + `.d.ts`
 * declarations. This is the bundle `/design-sync` ingests (see
 * DESIGN_SYNC.md for the full layout + export inventory).
 *
 * react / react-dom are externalized (peer deps) — the library ships code,
 * not a copy of React, matching the shadcn-style "copied-in primitives"
 * approach (D3): consumers bring their own React.
 */
export default defineConfig({
  // Library dist has no static assets of its own — do not copy the app's
  // public/ (favicon, sidebar icons) into it.
  publicDir: false,
  plugins: [
    tailwindcss(),
    react(),
    dts({
      tsconfigPath: './tsconfig.app.json',
      entryRoot: 'src/lib',
      include: ['src/lib/**/*.ts', 'src/lib/**/*.tsx'],
      exclude: ['src/lib/**/*.stories.tsx'],
      outDir: 'dist-lib',
      insertTypesEntry: true,
      bundleTypes: false,
    }),
  ],
  build: {
    outDir: 'dist-lib',
    emptyOutDir: true,
    cssMinify: true,
    lib: {
      entry: resolve(__dirname, 'src/lib/index.ts'),
      formats: ['es'],
      fileName: () => 'index.js',
    },
    rollupOptions: {
      external: ['react', 'react-dom', 'react/jsx-runtime'],
    },
  },
})
