# Checkpoint Copilot Frontend

Static dashboard for the FastAPI backend.

Run the backend:

```bash
cd checkpoint-copilot/backend
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Open <http://localhost:8000/dashboard>.

When serving this directory separately, set the API base in the UI or pass it as
a query parameter:

```text
http://localhost:5173/?api=http://localhost:8000
```
