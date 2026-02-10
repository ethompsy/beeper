#!/bin/bash
# Seed Qdrant with sample KB entries for local development
#
# Usage:
#   ./scripts/seed-kb.sh [--host HOST] [--port PORT]
#
# Environment variables:
#   QDRANT_HOST: Qdrant server host (default: localhost)
#   QDRANT_PORT: Qdrant server port (default: 6333)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is required but not installed"
    exit 1
fi

# Check if qdrant-client is available
if ! python3 -c "import qdrant_client" 2>/dev/null; then
    echo "Error: qdrant-client package is required"
    echo "Install with: pip install qdrant-client"
    exit 1
fi

echo "=== Beeper KB Seeding ==="
echo

# First, ensure collections exist
echo "Step 1: Initializing collections..."
python3 "${SCRIPT_DIR}/init-collections.py" "$@"
echo

# Then, seed with sample data
echo "Step 2: Seeding sample KB entries..."
python3 "${SCRIPT_DIR}/seed_kb.py" "$@"
echo

echo "=== KB Seeding Complete ==="
