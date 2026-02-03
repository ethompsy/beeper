# Build stage
FROM python:3.11-slim-bookworm AS builder

WORKDIR /app

# Install poetry
RUN pip install poetry

# Copy dependency files
COPY pyproject.toml ./

# Configure poetry to not create virtual environment
RUN poetry config virtualenvs.create false

# Install dependencies
RUN poetry install --no-dev --no-interaction --no-ansi

# Runtime stage
FROM python:3.11-slim-bookworm

# Create non-root user
RUN useradd -r -u 1000 beeper

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY beeper_ui ./beeper_ui

# Use non-root user
USER beeper

# Flask configuration
ENV FLASK_APP=beeper_ui.app
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_RUN_PORT=5000

EXPOSE 5000

ENTRYPOINT ["flask", "run"]
