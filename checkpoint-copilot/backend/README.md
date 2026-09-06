# Checkpoint Copilot — Backend

FastAPI service that reads Entire Checkpoint data from disk and exposes it as a
REST API for the dashboard.

## Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run

```bash
# Point at a real Entire repo (e.g. this one)
export ENTIRE_REPO_PATH=/Users/nehalagrawal/cli

uvicorn app.main:app --reload --port 8000
```

OpenAPI docs at <http://localhost:8000/docs>.

## Architecture

The adapter layer (`app/adapter/`) is the only code that touches the
filesystem. Everything above it is pure logic on parsed data.

```
app/
├── adapter/      ← reads .entire/, git refs (NO repo imports)
├── analysis/     ← pure logic: risk, intent-vs-impl, handoff
├── api/          ← FastAPI routes
└── main.py       ← app entrypoint
```
