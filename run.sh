#!/usr/bin/env bash
# Start the Routiqo AI Sales Agent.
# This script does not install packages. If something is missing, it prints the setup commands.

set -euo pipefail

cd "$(dirname "$0")"

if [ -d ".venv" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
  PYTHON=python
else
  PYTHON=python3
fi

if ! "$PYTHON" -c "import fastapi, uvicorn, dotenv, pydantic" >/dev/null 2>&1; then
  echo "Dependencies are missing. This script will not install them for you."
  echo
  echo "From this folder, run:"
  echo "  python3 -m venv .venv"
  echo "  source .venv/bin/activate"
  echo "  pip install -r requirements.txt"
  echo
  echo "Optional, for live Gemini replies:"
  echo "  cp .env.example .env"
  echo "  Then edit GEMINI_API_KEY and GEMINI_MODEL."
  echo
  echo "Start again with:"
  echo "  ./run.sh"
  exit 1
fi

echo "Routiqo AI Sales Agent"
echo "Open http://127.0.0.1:8000"
echo "API docs: http://127.0.0.1:8000/docs"
echo "Press Ctrl+C to stop."
echo

exec "$PYTHON" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
