"""Unfinished work detection.

Looks for patterns in transcripts and file changes that suggest incomplete work:
- TODO/FIXME comments
- Empty function bodies
- Failed tool calls
- Repeated retries on the same tool
- Partial file writes
"""
import re
from dataclasses import dataclass

from app.adapter.models import Session


@dataclass
class UnfinishedWorkResult:
    """Result of unfinished work analysis."""

    todos: list[str]  # TODO/FIXME comments found
    retries: list[str]  # Tool calls that were retried
    abandoned: list[str]  # Files that were started but not committed
    partial: list[str]  # Functions/methods that may be incomplete
    confidence: float  # 0.0–1.0: confidence that work is incomplete
    context_complete: bool = True
    context_status: str = "complete"
    context_warnings: list[str] | None = None


def detect_todos(transcript_text: str) -> list[str]:
    """Extract TODO/FIXME/HACK comments from transcript content."""
    patterns = [
        r"#\s*TODO[:\s].*",
        r"#\s*FIXME[:\s].*",
        r"#\s*HACK[:\s].*",
        r"#\s*XXX[:\s].*",
        r"//\s*TODO[:\s].*",
        r"//\s*FIXME[:\s].*",
    ]

    todos: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, transcript_text, re.IGNORECASE | re.MULTILINE):
            todos.append(match.group(0).strip()[:200])

    return list(dict.fromkeys(todos))[:20]  # Dedupe and limit


def detect_retries(transcript) -> list[str]:
    """Find tool calls that were retried multiple times."""
    if not transcript:
        return []

    # Count tool uses by name
    tool_counts: dict[str, int] = {}
    for entry in transcript:
        if entry.is_tool_use and entry.tool_name:
            tool_counts[entry.tool_name] = tool_counts.get(entry.tool_name, 0) + 1

    # Tools called 3+ times suggest retry loops
    retries: list[str] = []
    for tool, count in tool_counts.items():
        if count >= 3:
            retries.append(f"{tool} called {count} times (possible retry loop)")

    return retries


def detect_partial_impls(transcript) -> list[str]:
    """Look for tool calls that may indicate partial implementations.

    Patterns:
    - Write/Edit calls with TODO comments in the content
    - Functions with 'pass' or '...' as body
    """
    partial: list[str] = []
    for entry in transcript:
        if entry.is_tool_use and entry.tool_name in ("Write", "Edit"):
            tool_input = entry.tool_input or {}
            content = ""
            if isinstance(tool_input, dict):
                content = str(tool_input.get("content", ""))

            if "..." in content and "def " in content:
                # Python: def foo(): ...
                partial.append("Python function with '...' body")
                break
            if re.search(r"func\s+\w+\(.*\)\s*\{\s*\}", content):
                # Go: empty function
                partial.append("Empty Go function body")
                break

    return partial


def detect_unfinished_work(session: Session) -> UnfinishedWorkResult:
    """Analyze a session for signs of incomplete work."""
    context_warnings = list(session.context_warnings)
    if not session.transcript and not session.context_complete:
        context_warnings.append(
            "Transcript is unavailable or redacted; TODOs, retries, and partial edits may be unknown."
        )

    # Collect all text content from transcript
    transcript_text = ""
    for entry in session.transcript:
        if isinstance(entry.content, str):
            transcript_text += entry.content + "\n"
        elif entry.is_tool_use and entry.tool_input:
            transcript_text += str(entry.tool_input) + "\n"

    todos = detect_todos(transcript_text)
    retries = detect_retries(session.transcript)
    partial = detect_partial_impls(session.transcript)

    # Detect abandoned files: started but not in any checkpoint
    abandoned: list[str] = []
    if session.transcript:
        files_in_transcript = set()
        for entry in session.transcript:
            if entry.is_tool_use and entry.tool_input:
                path = entry.tool_input.get("file_path")
                if path:
                    files_in_transcript.add(path)

        committed_files = set(session.all_files_changed)
        abandoned = list(files_in_transcript - committed_files)[:10]

    # Confidence: how sure are we this is unfinished?
    confidence = 0.0
    if todos:
        confidence += 0.4
    if retries:
        confidence += 0.3
    if partial:
        confidence += 0.2
    if abandoned:
        confidence += 0.1
    if session.status == "active":
        confidence += 0.1  # Still running, may be unfinished by definition

    confidence = min(1.0, confidence)

    return UnfinishedWorkResult(
        todos=todos,
        retries=retries,
        abandoned=abandoned,
        partial=partial,
        confidence=confidence,
        context_complete=session.context_complete,
        context_status=session.context_status,
        context_warnings=list(dict.fromkeys(context_warnings)),
    )
