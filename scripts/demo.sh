#!/usr/bin/env bash
# Start the Beeper demo environment.
#
# This script starts the local dependencies (Qdrant, Beeper UI) and optionally
# deploys the OTel Astronomy Shop to Kubernetes.
#
# Usage:
#   ./scripts/demo.sh          # Local UI only (Qdrant + seed KB + Flask)
#   ./scripts/demo.sh --k8s    # Also deploy OTel demo to K8s
#
# Prerequisites: docker (or podman), poetry
# For --k8s: kubectl, helm

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${BEEPER_UI_PORT:-5050}"
DEPLOY_K8S=false

# Parse args
for arg in "$@"; do
  case "$arg" in
    --k8s) DEPLOY_K8S=true ;;
    *) echo "Unknown argument: $arg"; exit 1 ;;
  esac
done

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

if [ "$DEPLOY_K8S" = true ]; then
  check_cmd kubectl
  check_cmd helm
  check_cmd docker
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

# ── OTel Astronomy Shop (K8s) ───────────────────────────────────────────────

if [ "$DEPLOY_K8S" = true ]; then
  info "Setting up full K8s demo environment..."
  cd "$ROOT_DIR"

  # Check for LLM API key (required for investigations to complete)
  LLM_KEY="${ANTHROPIC_API_KEY:-${BEEPER_LLM_API_KEY:-}}"
  if [ -z "$LLM_KEY" ]; then
    fail "ANTHROPIC_API_KEY (or BEEPER_LLM_API_KEY) must be set. Export your key and re-run: export ANTHROPIC_API_KEY=sk-ant-..."
  fi

  info "Creating kind cluster + building images + deploying Beeper..."
  make demo-cluster
  make demo-build
  make demo-helm-repo
  make demo-beeper
  ok "Beeper deployed to K8s"

  info "Deploying OTel Astronomy Shop..."
  make demo-deploy
  ok "OTel demo deployed to K8s"

  echo ""
  ok "Full K8s demo is ready!"
  ok "OTel Shop:       http://localhost:8080  (run 'make demo-ui' to port-forward)"
  ok "Feature Flags:   http://localhost:8080/feature"
  ok "Jaeger:          http://localhost:16686"
  ok "Beeper UI:       http://localhost:5050"
fi

# ── Start Flask ──────────────────────────────────────────────────────────────

cleanup() {
  echo ""
  info "Shutting down..."
  # Leave Qdrant running — it's cheap and reusable between sessions.
  # To stop everything: docker-compose -f "$ROOT_DIR/docker-compose.yaml" down
  # To tear down K8s demo: make demo-teardown
  ok "Flask stopped. Qdrant is still running (use docker-compose down to stop it)."
  if [ "$DEPLOY_K8S" = true ]; then
    ok "OTel demo is still running in K8s (use 'make demo-teardown' to stop it)."
  fi
}
trap cleanup INT TERM

info "Starting Flask on port $PORT..."
echo ""
ok "Beeper UI: http://localhost:$PORT/knowledge/"
echo ""

cd "$ROOT_DIR/ui"
FLASK_APP=beeper_ui.app poetry run flask run --port "$PORT"
