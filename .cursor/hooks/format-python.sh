#!/bin/bash
set -euo pipefail

input=$(cat)
file=$(echo "$input" | jq -r '.path // empty')

if [[ -z "$file" || ! -f "$file" || "$file" != *.py ]]; then
  exit 0
fi

if command -v ruff &>/dev/null; then
  ruff format "$file" 2>/dev/null || true
elif command -v poetry &>/dev/null; then
  poetry run ruff format "$file" 2>/dev/null || true
fi

exit 0
