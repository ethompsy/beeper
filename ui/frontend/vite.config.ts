import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// The Flask BFF dev server (`poetry run flask run` / `flask run`) defaults to
// port 5000 (see ui/README.md). Overridable so a developer running Flask on
// a different port doesn't have to edit this file.
const BFF_ORIGIN = process.env.BFF_ORIGIN ?? 'http://localhost:5000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    tailwindcss(),
    react(),
  ],
  server: {
    proxy: {
      // JSON SSE event stream (Task 1.6): GET /api/v1/investigations/{id}/events.
      // Kept as its own entry (rather than folded into the blanket `/api` rule
      // below) so the no-buffering settings are explicit and scoped to the one
      // route that actually streams. Vite/http-proxy already pipes proxied
      // responses through as they arrive (verified: chunks land at the client
      // as soon as the BFF writes them, not batched at connection close) — the
      // settings below make that explicit and guard against buffering being
      // reintroduced by proxy config changes or an intermediary:
      //   - `selfHandleResponse: false` (the default) keeps http-proxy's
      //     automatic per-chunk pipe-through active; setting this to `true`
      //     would require res to be written manually and risks buffering the
      //     whole response before forwarding it.
      //   - `configure` re-asserts the no-buffering / no-cache headers the
      //     BFF already sends (`X-Accel-Buffering: no`, `Cache-Control:
      //     no-cache`) on both the outgoing proxied request and the response
      //     handed back to the browser, so streaming survives even if
      //     changeOrigin or a future header-rewrite would otherwise drop them.
      '^/api/v1/investigations/.*/events': {
        target: BFF_ORIGIN,
        changeOrigin: true,
        ws: false,
        selfHandleResponse: false,
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyReq) => {
            proxyReq.setHeader('Cache-Control', 'no-cache')
          })
          proxy.on('proxyRes', (proxyRes) => {
            proxyRes.headers['cache-control'] = 'no-cache'
            proxyRes.headers['x-accel-buffering'] = 'no'
          })
        },
      },
      // Remaining JSON API (Task 1.6): GET /api/v1/investigations, /{id}.
      '/api': {
        target: BFF_ORIGIN,
        changeOrigin: true,
      },
    },
  },
})
