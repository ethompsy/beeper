# Beeper Investigator

The Beeper Investigator is an AI-powered agent that correlates signals across observability layers and generates root cause hypotheses with resolution recommendations.

## Features

- Multi-source signal correlation
- LLM-powered root cause analysis
- Integration with Qdrant vector database for knowledge retrieval
- Support for multiple LLM providers via LiteLLM

## Installation

```bash
poetry install
```

## Usage

```bash
poetry run python -m beeper_investigator.main
```

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
