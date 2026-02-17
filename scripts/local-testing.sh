#!/bin/bash
# Local testing script for Beeper
# Runs the same checks as CI plus integration tests with Qdrant

# Don't use set -e as we handle errors manually with print_result

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track results
PASSED=0
FAILED=0
SKIPPED=0

print_header() {
    echo ""
    echo "=============================================="
    echo -e "${YELLOW}$1${NC}"
    echo "=============================================="
}

print_result() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓ PASSED${NC}: $2"
        ((PASSED++))
    else
        echo -e "${RED}✗ FAILED${NC}: $2"
        ((FAILED++))
        if [ "$FAIL_FAST" = "true" ]; then
            exit 1
        fi
    fi
}

skip_test() {
    echo -e "${YELLOW}⊘ SKIPPED${NC}: $1"
    ((SKIPPED++))
}

wait_for_qdrant() {
    echo "Waiting for Qdrant to be ready..."
    local max_attempts=30
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        if curl -s http://localhost:6333/healthz > /dev/null 2>&1; then
            echo "Qdrant is ready!"
            return 0
        fi
        echo "  Attempt $attempt/$max_attempts - waiting..."
        sleep 2
        ((attempt++))
    done

    echo "Qdrant failed to become ready"
    return 1
}

# Parse arguments
RUN_INTEGRATION=false
START_QDRANT=false
FAIL_FAST=false
LINT_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --integration|-i)
            RUN_INTEGRATION=true
            START_QDRANT=true
            shift
            ;;
        --start-qdrant|-q)
            START_QDRANT=true
            shift
            ;;
        --fail-fast|-f)
            FAIL_FAST=true
            shift
            ;;
        --lint-only|-l)
            LINT_ONLY=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  -i, --integration   Run integration tests (starts Qdrant)"
            echo "  -q, --start-qdrant  Start Qdrant but don't run integration tests"
            echo "  -f, --fail-fast     Exit on first failure"
            echo "  -l, --lint-only     Only run linting checks"
            echo "  -h, --help          Show this help"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Get project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║          Beeper Local Testing Suite          ║"
echo "╚══════════════════════════════════════════════╝"

# =============================================================================
# INFRASTRUCTURE
# =============================================================================

if [ "$START_QDRANT" = "true" ]; then
    print_header "Starting Infrastructure"

    echo "Starting Qdrant via docker-compose..."
    docker-compose up -d

    if wait_for_qdrant; then
        print_result 0 "Qdrant started"

        echo "Seeding KB with sample data..."
        if ./scripts/seed-kb.sh > /dev/null 2>&1; then
            print_result 0 "KB seeded"
        else
            print_result 1 "KB seeding"
        fi
    else
        print_result 1 "Qdrant startup"
        RUN_INTEGRATION=false
    fi
fi

# =============================================================================
# LINTING
# =============================================================================

print_header "Linting Checks"

# Rust formatting
echo "Checking Rust formatting..."
cd "$PROJECT_ROOT/operator"
if cargo fmt --check > /dev/null 2>&1; then
    print_result 0 "Rust formatting (cargo fmt)"
else
    print_result 1 "Rust formatting (cargo fmt)"
fi

# Rust clippy
echo "Running Clippy..."
cargo clippy -- -D warnings > /dev/null 2>&1
if [ $? -eq 0 ]; then
    print_result 0 "Rust linting (cargo clippy)"
else
    print_result 1 "Rust linting (cargo clippy)"
fi

# Python investigator
echo "Checking investigator Python..."
cd "$PROJECT_ROOT/investigator"
if poetry run ruff check . > /dev/null 2>&1; then
    print_result 0 "Investigator linting (ruff)"
else
    print_result 1 "Investigator linting (ruff)"
fi

# Python UI
echo "Checking UI Python..."
cd "$PROJECT_ROOT/ui"
if poetry run ruff check . > /dev/null 2>&1; then
    print_result 0 "UI linting (ruff)"
else
    print_result 1 "UI linting (ruff)"
fi

# Helm lint
echo "Checking Helm chart..."
cd "$PROJECT_ROOT"
if helm lint ./helm/beeper > /dev/null 2>&1; then
    print_result 0 "Helm lint"
else
    if command -v helm &> /dev/null; then
        print_result 1 "Helm lint"
    else
        skip_test "Helm lint (helm not installed)"
    fi
fi

if [ "$LINT_ONLY" = "true" ]; then
    echo ""
    echo "Lint-only mode, skipping tests."
else

# =============================================================================
# UNIT TESTS
# =============================================================================

print_header "Unit Tests"

# Rust tests
echo "Running Rust tests..."
cd "$PROJECT_ROOT/operator"
RUST_OUTPUT=$(cargo test 2>&1)
RUST_EXIT=$?
# Extract the summary line
echo "$RUST_OUTPUT" | grep -E "^test result:" | head -1
if [ $RUST_EXIT -eq 0 ]; then
    print_result 0 "Rust operator tests"
else
    print_result 1 "Rust operator tests"
fi

# Python investigator tests
echo "Running investigator tests..."
cd "$PROJECT_ROOT/investigator"
PYTEST_OUTPUT=$(poetry run pytest -v --ignore=tests/test_kb_client.py 2>&1)
PYTEST_EXIT=$?
echo "$PYTEST_OUTPUT" | tail -10
if [ $PYTEST_EXIT -eq 0 ]; then
    print_result 0 "Investigator tests (unit)"
else
    print_result 1 "Investigator tests (unit)"
fi

# Python UI tests
echo "Running UI tests..."
cd "$PROJECT_ROOT/ui"
PYTEST_OUTPUT=$(poetry run pytest -v 2>&1)
PYTEST_EXIT=$?
echo "$PYTEST_OUTPUT" | tail -10
if [ $PYTEST_EXIT -eq 0 ]; then
    print_result 0 "UI tests"
else
    print_result 1 "UI tests"
fi

# =============================================================================
# INTEGRATION TESTS
# =============================================================================

if [ "$RUN_INTEGRATION" = "true" ]; then
    print_header "Integration Tests (with Qdrant)"

    echo "Running KB client integration tests..."
    cd "$PROJECT_ROOT/investigator"
    export QDRANT_HOST=localhost
    export QDRANT_PORT=6333

    PYTEST_OUTPUT=$(poetry run pytest tests/test_kb_client.py -v -m integration 2>&1)
    PYTEST_EXIT=$?
    echo "$PYTEST_OUTPUT" | tail -15
    if [ $PYTEST_EXIT -eq 0 ]; then
        print_result 0 "KB client integration tests"
    else
        print_result 1 "KB client integration tests"
    fi
else
    print_header "Integration Tests"
    skip_test "KB client integration tests (use --integration to run)"
fi

fi  # End of LINT_ONLY check

# =============================================================================
# SUMMARY
# =============================================================================

print_header "Summary"

echo ""
echo -e "  ${GREEN}Passed${NC}:  $PASSED"
echo -e "  ${RED}Failed${NC}:  $FAILED"
echo -e "  ${YELLOW}Skipped${NC}: $SKIPPED"
echo ""

if [ $FAILED -gt 0 ]; then
    echo -e "${RED}Some tests failed!${NC}"
    exit 1
else
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
fi
