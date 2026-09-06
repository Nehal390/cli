## Original Product Goal

Checkpoint Copilot: a developer dashboard that uses real Entire Checkpoint
context to assess implementation vs intent, identify unfinished work, surface
risk, and generate handoff/resume materials.

## Current Architecture

Entire Checkpoint -> Checkpoint Adapter (CliCheckpointReader, calls entire CLI)
-> Analysis Engine (risk scoring, intent alignment, handoff readiness)
-> REST API (FastAPI: /api/sessions, /api/checkpoints, /api/dashboard,
/api/handoff/{session_id}) -> Frontend Dashboard (static HTML/CSS/JS)

## Completed Functionality

- Adapter reads real checkpoints via `entire checkpoint list --json`; `entire checkpoint explain --json` is available in the CLI and verified manually, but is not yet wired into the adapter for file-level enrichment
- Analysis engine computes risk score, intent alignment %, handoff blockers,
  work signals (checkpoint count, files changed, TODOs)
- REST API fully working, tested via /docs
- Dashboard UI: dark theme, stat cards, filterable session list, detail view
- Generate Handoff feature: produces summary + resume prompt
- Verified live: checkpoint count updates in real time as new commits are made

## Unresolved Issues / Known Gaps

- Single active repo at a time; repo switching is process-local, not a persisted multi-repo workspace model
- Analysis is based on session metadata/prompts, checkpoint messages, and available file lists, not deep code-semantic analysis
- No dedicated standalone visual Timeline page yet; checkpoint data exists via /api/checkpoints and is shown in the selected-session detail view
- `files_changed` is still empty from `entire checkpoint list --json`; adapter needs `entire checkpoint explain --json` wired in to populate file-level details
- CLI-backed transcript loading is not implemented, so first prompt and intent can be sparse when session metadata is abbreviated

## Technical Risks

- `CliCheckpointReader` shells out to `entire`; missing binaries, command timeouts, or CLI JSON shape changes currently degrade to empty results
- `entire checkpoint list --json` can return overlapping committed/pending/log-style checkpoint records, so consumers need to tolerate duplicates or sparse file data
- Session status mapping is simple (`idle` maps to `ended`; unknown statuses become `unknown`)
- Handoff and intent analysis are heuristic and can under-score alignment when prompts or file lists are incomplete
- Frontend state is purely in-memory/localStorage; API base and generated handoff text are not persisted server-side
- Backend repo switching updates the running app state only; restarting the backend falls back to `ENTIRE_REPO_PATH` or the default repo path
- Static frontend and FastAPI backend are separate dev servers unless served through the backend `/dashboard` mount

## How to Start the App

Start the backend:

```bash
cd /Users/nehalagrawal/cli/checkpoint-copilot/backend
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Start the static frontend:

```bash
cd /Users/nehalagrawal/cli/checkpoint-copilot/frontend
python3 -m http.server 5173 --bind 127.0.0.1
```

Open the frontend:

```bash
open http://127.0.0.1:5173
```

Open the API docs:

```bash
open http://127.0.0.1:8000/docs
```

## Entire Checkpoint Flow

Entire enabled via `entire enable --agent claude-code` / codex on this repo.
Checkpoints created automatically on each commit. Adapter currently reads them
via `entire checkpoint list --json`. `entire checkpoint explain --json` returns
file-level checkpoint detail and should be wired into the adapter next for
accurate `files_changed` data.
