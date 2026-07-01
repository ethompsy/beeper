import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    tailwindcss(),
    react(),
  ],
  // NOTE: dev-proxy block (Task 1.5) belongs here as a `server.proxy` key — kept clean for that addition.
})
