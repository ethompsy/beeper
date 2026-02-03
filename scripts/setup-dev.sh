#!/bin/bash
set -e

echo "=== Beeper Development Environment Setup ==="
echo

# Check for required tools
check_tool() {
    if ! command -v "$1" &> /dev/null; then
        echo "Error: $1 is not installed"
        exit 1
    fi
    echo "✓ $1 found"
}

echo "Checking required tools..."
check_tool "cargo"
check_tool "python3"
check_tool "poetry"
check_tool "docker"
echo

# Set up Rust operator
echo "Setting up Rust operator..."
cd operator
cargo build
echo "✓ Operator built"
cd ..
echo

# Set up Python investigator
echo "Setting up Python investigator..."
cd investigator
poetry install
echo "✓ Investigator dependencies installed"
cd ..
echo

# Set up Python UI
echo "Setting up Python UI..."
cd ui
poetry install
echo "✓ UI dependencies installed"
cd ..
echo

# Start Qdrant
echo "Starting Qdrant..."
docker-compose up -d qdrant
echo "✓ Qdrant started"
echo

echo "=== Setup Complete ==="
echo
echo "To run each component:"
echo "  Operator:     cd operator && cargo run"
echo "  Investigator: cd investigator && poetry run python -m beeper_investigator.main"
echo "  UI:           cd ui && poetry run flask run"
echo
echo "Qdrant is available at http://localhost:6333"
