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

## License

Apache License 2.0
