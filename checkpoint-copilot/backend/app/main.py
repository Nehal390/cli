"""Checkpoint Copilot backend — FastAPI application."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.adapter import CliCheckpointReader
from app.api.routes import checkpoints, health, sessions
from app.config import get_repo_path


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the CLI-based checkpoint reader on startup."""
    repo_path = get_repo_path()
    reader = CliCheckpointReader(repo_path)
    # Store in app state so routes can access it
    app.state.reader = reader
    yield
    # Cleanup on shutdown (if needed)


app = FastAPI(
    title="Checkpoint Copilot API",
    description="Developer dashboard for Entire Checkpoint analysis. "
                "Reads checkpoint data from an Entire-enabled git repository "
                "and exposes analysis endpoints.",
    version="0.1.0",
    lifespan=lifespan,
)

# Allow frontend to call the API during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(sessions.router)
app.include_router(checkpoints.router)
app.include_router(health.router)


@app.get("/")
def root():
    """Root redirects to /docs for OpenAPI UI."""
    return {
        "message": "Checkpoint Copilot API",
        "docs": "/docs",
        "health": "/api/health",
        "dashboard": "/api/dashboard",
        "sessions": "/api/sessions",
    }
