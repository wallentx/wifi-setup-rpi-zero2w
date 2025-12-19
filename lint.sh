#!/bin/bash

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "Error: 'uv' is not installed or not in PATH."
    echo "Please install uv first: https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
fi

# Default behavior
FIX=false

# Parse arguments
while getopts "f" opt; do
  case ${opt} in
    f)
      FIX=true
      ;;
    \?)
      echo "Usage: $0 [-f]"
      exit 1
      ;;
  esac
done

if [ "$FIX" = true ]; then
    echo "Running Ruff with auto-fix and formatting..."
    uv run ruff check --fix .
    uv run ruff format .
else
    echo "Running Ruff lint check..."
    uv run ruff check .
    echo "Running Ruff format check..."
    uv run ruff format --check .
fi
