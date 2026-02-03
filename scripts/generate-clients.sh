#!/bin/bash
set -e

echo "=== Beeper OpenAPI Client Generation ==="
echo

# Check for openapi-generator
if ! command -v openapi-generator &> /dev/null; then
    echo "Error: openapi-generator is not installed"
    echo "Install with: brew install openapi-generator"
    exit 1
fi

SPEC_FILE="openapi/beeper-api.yaml"

if [ ! -f "$SPEC_FILE" ]; then
    echo "Error: OpenAPI spec not found at $SPEC_FILE"
    exit 1
fi

echo "Generating Python client..."
openapi-generator generate \
    -i "$SPEC_FILE" \
    -g python \
    -o generated/python-client \
    --additional-properties=packageName=beeper_client

echo "✓ Python client generated in generated/python-client"
echo

echo "=== Client Generation Complete ==="
