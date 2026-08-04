# ── Node build stage ─────────────────────────────────────────────────────────
# Task 1.1: build the Vite + React + TS bundle from ui/frontend/
# Produces /build/dist/ which is copied into the runtime image at /app/frontend/dist/
FROM node:24-slim AS node-builder

WORKDIR /build

# Copy package manifests first for layer-cache efficiency
COPY frontend/package.json frontend/package-lock.json ./

# Install deps (ci is faster + reproducible)
RUN npm ci

# Copy source
COPY frontend/ ./

# Build the production bundle; hashed assets land in dist/
RUN npm run build

# ── Python builder stage ─────────────────────────────────────────────────────
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
# Use a glibc base (matching the bookworm runtime stage) so the standalone
# tailwindcss binary's libstdc++/libgcc deps resolve. The previous Dockerfile
# hardcoded the linux-x64 binary on Alpine, which (a) fails on arm64 build hosts
# like Apple Silicon (exit 133, wrong arch) and (b) is the wrong libc for Alpine
# (musl). TARGETARCH (provided by buildx / the build host) selects the binary.
FROM debian:bookworm-slim AS tailwind
ARG TARGETARCH
WORKDIR /build
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
RUN set -eux; \
    case "${TARGETARCH:-amd64}" in \
      arm64) tw="tailwindcss-linux-arm64"; \
             sum="8f48dcb72be3b351c10563c5329b4638ba8516820dc3b3a1609625a166e87cbd" ;; \
      amd64) tw="tailwindcss-linux-x64"; \
             sum="73f0e5459054e5cfaa8ab6f3b940f3fbe0f13cc7fd83bc24e7c655033c203400" ;; \
      *) echo "unsupported TARGETARCH=${TARGETARCH}"; exit 1 ;; \
    esac; \
    curl -fsSL -o /usr/local/bin/tailwindcss \
      "https://github.com/tailwindlabs/tailwindcss/releases/download/v4.3.0/${tw}"; \
    chmod +x /usr/local/bin/tailwindcss; \
    echo "${sum}  /usr/local/bin/tailwindcss" | sha256sum -c -
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

# Copy React bundle from node build stage (Task 1.1)
# Served by Flask at /app/* via beeper_ui/routes/react_shell.py
COPY --from=node-builder /build/dist ./frontend/dist

# Use non-root user
USER beeper

# Flask configuration
ENV FLASK_APP=beeper_ui.app
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_RUN_PORT=5000

EXPOSE 5000

ENTRYPOINT ["flask", "run"]
