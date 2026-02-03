# Contributing to Beeper

Thank you for your interest in contributing to Beeper! This document provides guidelines and instructions for contributing.

## Code of Conduct

By participating in this project, you agree to maintain a respectful and inclusive environment for everyone.

## Getting Started

1. Fork the repository
2. Clone your fork locally
3. Set up your development environment (see [README.md](README.md))
4. Create a feature branch from `main`

## Development Workflow

### Branch Naming

Use descriptive branch names:
- `feature/description` - New features
- `fix/description` - Bug fixes
- `docs/description` - Documentation changes
- `refactor/description` - Code refactoring

### Commit Messages

Write clear, concise commit messages:
- Use the imperative mood ("Add feature" not "Added feature")
- Keep the first line under 72 characters
- Reference issues when applicable

Example:
```
Add Prometheus metric source adapter

Implements the adapter pattern for ingesting Prometheus metrics
into the investigation pipeline.

Closes #123
```

### Code Style

#### Rust (Operator)

- Run `cargo fmt` before committing
- Ensure `cargo clippy` passes with no warnings
- Follow Rust API Guidelines

#### Python (Investigator & UI)

- Format code with `ruff format`
- Run `ruff check` before committing
- Use type hints for function signatures
- Follow PEP 8 conventions

### Testing

- Write tests for new functionality
- Ensure all existing tests pass
- Maintain test coverage for critical paths

```bash
# Rust
cd operator && cargo test

# Python
cd investigator && poetry run pytest
cd ui && poetry run pytest
```

## Pull Request Process

1. Update documentation if needed
2. Ensure CI checks pass
3. Request review from maintainers
4. Address review feedback
5. Squash commits if requested

### PR Description

Include:
- Summary of changes
- Related issues
- Testing performed
- Screenshots (for UI changes)

## Reporting Issues

### Bug Reports

Include:
- Beeper version
- Environment details (K8s version, Python version, etc.)
- Steps to reproduce
- Expected vs actual behavior
- Relevant logs

### Feature Requests

Include:
- Use case description
- Proposed solution
- Alternatives considered

## Questions?

- Open a GitHub Discussion for questions
- Check existing issues and discussions first

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.
