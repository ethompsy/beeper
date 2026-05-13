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
RUN poetry install --only main --no-root --no-interaction --no-ansi

# Tailwind CSS build stage
FROM alpine:3.19 AS tailwind
WORKDIR /build
ADD https://github.com/tailwindlabs/tailwindcss/releases/download/v4.3.0/tailwindcss-linux-x64 /usr/local/bin/tailwindcss
RUN chmod +x /usr/local/bin/tailwindcss \
    && echo "73f0e5459054e5cfaa8ab6f3b940f3fbe0f13cc7fd83bc24e7c655033c203400  /usr/local/bin/tailwindcss" | sha256sum -c
COPY beeper_ui/static/css/input.css ./input.css
COPY beeper_ui/templates/ ./beeper_ui/templates/
COPY beeper_ui/static/js/ ./beeper_ui/static/js/
RUN tailwindcss --minify -i input.css -o tailwind.css

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

# Copy generated Tailwind CSS from build stage
COPY --from=tailwind /build/tailwind.css ./beeper_ui/static/css/tailwind.css

# Use non-root user
USER beeper

# Flask configuration
ENV FLASK_APP=beeper_ui.app
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_RUN_PORT=5000

EXPOSE 5000

ENTRYPOINT ["flask", "run"]
