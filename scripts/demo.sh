#!/usr/bin/env bash
# Start all dependencies and the Beeper UI for local demos.
#
# Usage: ./scripts/demo.sh
#
# Prerequisites: docker (or podman), poetry

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${BEEPER_UI_PORT:-5050}"

# ── Helpers ──────────────────────────────────────────────────────────────────

info()  { printf '\033[1;34m▸ %s\033[0m\n' "$*"; }
ok()    { printf '\033[1;32m✔ %s\033[0m\n' "$*"; }
fail()  { printf '\033[1;31m✘ %s\033[0m\n' "$*" >&2; exit 1; }

check_cmd() {
  command -v "$1" &>/dev/null || fail "$1 is required but not installed"
}

# ── Prerequisites ────────────────────────────────────────────────────────────

info "Checking prerequisites..."
check_cmd poetry

# Detect docker-compose variant (plugin vs standalone)
if docker compose version &>/dev/null; then
  DC="docker compose"
elif command -v docker-compose &>/dev/null; then
  DC="docker-compose"
else
  fail "docker compose (or docker-compose) is required but not installed"
fi
ok "Prerequisites OK"

# ── Qdrant ───────────────────────────────────────────────────────────────────

info "Starting Qdrant..."
$DC -f "$ROOT_DIR/docker-compose.yaml" up -d

info "Waiting for Qdrant to be healthy..."
retries=0
until curl -sf http://localhost:6333/healthz >/dev/null 2>&1; do
  retries=$((retries + 1))
  if [ "$retries" -ge 30 ]; then
    fail "Qdrant did not become healthy after 30 seconds"
  fi
  sleep 1
done
ok "Qdrant is healthy"

# ── Python deps ──────────────────────────────────────────────────────────────

info "Installing Python dependencies..."
cd "$ROOT_DIR/ui"
poetry install --quiet
ok "Dependencies installed"

# ── Seed KB (only if collection missing) ─────────────────────────────────────

collection_exists=$(curl -sf http://localhost:6333/collections/knowledge 2>/dev/null | grep -c '"status":"ok"' || true)
if [ "$collection_exists" -eq 0 ]; then
  info "Seeding knowledge base..."
  poetry run python "$ROOT_DIR/scripts/init-collections.py"
  poetry run python "$ROOT_DIR/scripts/seed_kb.py"
  ok "KB seeded"
else
  ok "KB collection already exists — skipping seed"
fi

# ── Start Flask ──────────────────────────────────────────────────────────────

cleanup() {
  echo ""
  info "Shutting down..."
  # Leave Qdrant running — it's cheap and reusable between sessions.
  # To stop everything: docker-compose -f "$ROOT_DIR/docker-compose.yaml" down
  ok "Flask stopped. Qdrant is still running (use docker-compose down to stop it)."
}
trap cleanup INT TERM

info "Starting Flask on port $PORT..."
echo ""
ok "Open http://localhost:$PORT/knowledge/ in your browser"
echo ""

FLASK_APP=beeper_ui.app poetry run flask run --port "$PORT"
