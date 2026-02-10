# Build stage
FROM rust:1.85-bookworm AS builder

WORKDIR /app

# Copy manifests
COPY Cargo.toml ./

# Create dummy source to cache dependencies
RUN mkdir src && \
    echo "fn main() {}" > src/main.rs && \
    echo "// dummy" > src/lib.rs

# Build dependencies only
RUN cargo build --release && \
    rm -rf src

# Copy actual source
COPY src ./src

# Build the application
RUN touch src/main.rs src/lib.rs && \
    cargo build --release

# Runtime stage
FROM debian:bookworm-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        libssl3 && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -r -u 1000 beeper

WORKDIR /app

# Copy binary from builder
COPY --from=builder /app/target/release/beeper-operator /app/beeper-operator

# Use non-root user
USER beeper

ENTRYPOINT ["/app/beeper-operator"]
