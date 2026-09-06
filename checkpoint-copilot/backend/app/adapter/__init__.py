"""Adapter layer: reads checkpoint data from disk or CLI.

Two readers:
- CliCheckpointReader: shells out to `entire` CLI commands (recommended)
- CheckpointReader: reads .entire/ directory directly (fallback)

All other code operates on the parsed Pydantic models defined here.
"""
from app.adapter.reader import CheckpointReader
from app.adapter.cli_reader import CliCheckpointReader
from app.adapter.models import (
    Checkpoint,
    Session,
    SessionCheckpoint,
    TranscriptEntry,
)

__all__ = [
    "CheckpointReader",
    "CliCheckpointReader",
    "Checkpoint",
    "Session",
    "SessionCheckpoint",
    "TranscriptEntry",
]
