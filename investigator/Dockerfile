# Build stage
FROM python:3.11-slim-bookworm AS builder

WORKDIR /app

# Install poetry
RUN pip install poetry

# Copy dependency files
COPY pyproject.toml ./

# Configure poetry to not create virtual environment
RUN poetry config virtualenvs.create false

# Install dependencies (--only main replaces deprecated --no-dev)
RUN poetry install --only main --no-interaction --no-ansi

# Runtime stage
FROM python:3.11-slim-bookworm

# Create non-root user
RUN useradd -r -u 1000 beeper

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY beeper_investigator ./beeper_investigator

# Use non-root user
USER beeper

ENTRYPOINT ["python", "-m", "beeper_investigator.main"]
