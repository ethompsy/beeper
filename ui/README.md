# Beeper UI

The Beeper UI is a Flask web application that provides an interface for viewing investigations, managing the knowledge base, and monitoring observability sources.

## Features

- Real-time investigation tracking with HTMX
- Knowledge base wiki interface
- Source health monitoring
- SSE-based live updates

## Installation

```bash
poetry install
```

## Usage

```bash
poetry run flask run
```

The UI will be available at http://localhost:5000

## Development

```bash
# Run tests
poetry run pytest

# Lint code
poetry run ruff check .

# Type check
poetry run mypy .
```

## React frontend development

The React app (`frontend/`, served at `/app/*` in production) has its own fast
inner dev loop: `vite dev` gives instant HMR on the React/TS source while
Flask keeps serving the JSON API and everything else. This mirrors the
existing `make tailwind-watch` + `poetry run flask run` two-terminal pattern.

**Terminal 1 — Flask BFF (JSON API + HTML routes):**

```bash
cd ui
poetry run flask run
```

Runs on `http://localhost:5000` by default.

**Terminal 2 — Vite dev server (React app with HMR):**

```bash
cd ui/frontend
npm run dev
```

Runs on `http://localhost:5173` by default. Open the app at that URL during
development — `vite dev`'s dev server proxies `/api/*` (including the JSON
event stream at `/api/v1/investigations/{id}/events`) through to the Flask
BFF on `:5000`, so API calls made from the React app resolve without a CORS
dance and the event stream flows through unbuffered in real time. See the
`server.proxy` block in `frontend/vite.config.ts` for the exact routes.

If Flask is running on a non-default port, point Vite at it:

```bash
BFF_ORIGIN=http://localhost:5050 npm run dev
```

## License

Apache License 2.0
