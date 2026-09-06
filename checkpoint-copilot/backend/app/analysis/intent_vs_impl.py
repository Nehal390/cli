"""Intent vs Implementation analysis.

Compares what the user asked for (from transcript prompts) against what the
agent actually changed (from checkpoint file lists and commit messages).
"""
from dataclasses import dataclass

from app.adapter.models import Session, TranscriptEntry, looks_redacted


@dataclass
class IntentVsImplResult:
    """Result of comparing user intent to actual implementation."""

    intent: str  # The user's original request
    implementation_summary: str  # What the agent actually did
    alignment_score: float  # 0.0–1.0: how well they match
    gaps: list[str]  # Things asked for but not delivered
    surprises: list[str]  # Things done that weren't in the intent
    context_complete: bool = True
    context_status: str = "complete"
    context_warnings: list[str] | None = None


def extract_intent(transcript: list[TranscriptEntry]) -> str:
    """Pull the first user prompt from a transcript."""
    for entry in transcript:
        if entry.role == "user" and entry.content:
            if isinstance(entry.content, str) and entry.content.strip():
                return entry.content.strip()
    return ""


def extract_file_actions(transcript: list[TranscriptEntry]) -> dict[str, list[str]]:
    """Infer file actions from transcript tool calls.

    Returns dict with keys: 'created', 'modified', 'deleted', 'read'
    """
    created: list[str] = []
    modified: list[str] = []
    deleted: list[str] = []
    read: list[str] = []

    for entry in transcript:
        if entry.is_tool_use and entry.tool_name in ("Write", "Edit", "Bash"):
            tool_input = entry.tool_input or {}
            if isinstance(tool_input, dict):
                if entry.tool_name == "Write" and "file_path" in tool_input:
                    created.append(tool_input["file_path"])
                elif entry.tool_name == "Bash":
                    cmd = str(tool_input.get("command", ""))
                    if "rm " in cmd and ".go" in cmd:
                        deleted.append(cmd.split("rm ")[-1].split()[0])

        if entry.is_tool_result and entry.tool_name == "Read":
            tool_input = entry.tool_input or {}
            if isinstance(tool_input, dict) and "file_path" in tool_input:
                read.append(tool_input["file_path"])

    return {"created": created, "modified": modified, "deleted": deleted, "read": read}


def keyword_overlap(intent: str, message: str, files: list[str]) -> float:
    """Simple keyword overlap score between intent and implementation."""
    if not intent or not (message or files):
        return 0.5  # Unknown

    intent_words = set(intent.lower().split())
    impl_words = set()
    if message:
        impl_words.update(message.lower().split())
    for f in files:
        impl_words.update(f.lower().replace("/", " ").replace("_", " ").split())

    # Remove common stopwords
    stopwords = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will", "would",
        "should", "could", "can", "may", "might", "must", "i", "you", "we",
        "they", "it", "this", "that", "these", "those", "my", "your", "our",
    }
    intent_words -= stopwords
    impl_words -= stopwords

    if not intent_words:
        return 0.5

    overlap = len(intent_words & impl_words)
    return min(1.0, overlap / len(intent_words))


def compare_intent_vs_impl(session: Session) -> IntentVsImplResult:
    """Compare what the user asked for against what the agent delivered."""
    intent = extract_intent(session.transcript)
    if not intent:
        intent = session.description
    if looks_redacted(intent):
        intent = ""

    all_files = list(session.all_files_changed)
    message_parts = [
        cp.message
        for cp in session.checkpoints
        if cp.message and not looks_redacted(cp.message)
    ]
    impl_summary = "; ".join(message_parts[:3]) if message_parts else ""

    gaps: list[str] = []
    surprises: list[str] = []
    context_warnings = list(session.context_warnings)
    if not session.context_complete:
        context_warnings.append(
            "Intent analysis is based on limited checkpoint context."
        )

    # Simple heuristic: look for common request patterns in intent
    intent_lower = intent.lower()
    file_actions = extract_file_actions(session.transcript)

    # Check for creation requests vs actual creates
    if "add" in intent_lower or "new" in intent_lower or "create" in intent_lower:
        expected_action = "create"
    elif "fix" in intent_lower or "bug" in intent_lower:
        expected_action = "fix"
    elif "remove" in intent_lower or "delete" in intent_lower:
        expected_action = "delete"
    elif "update" in intent_lower or "change" in intent_lower:
        expected_action = "update"
    else:
        expected_action = "explore"

    # Check alignment
    if not intent:
        context_warnings.append("Original user intent is unknown or redacted.")
    elif expected_action == "create" and not session.transcript:
        context_warnings.append(
            "Cannot verify requested file creation because transcript tool calls are unavailable."
        )
    elif expected_action == "create" and not file_actions["created"]:
        gaps.append("User requested creation but no files were created")
    elif expected_action == "fix" and not all_files and session.context_complete:
        gaps.append("User requested a fix but no files were modified")
    elif expected_action == "fix" and not all_files:
        context_warnings.append(
            "Cannot verify modified files because checkpoint file lists are unavailable."
        )

    # Check for unexpected file changes
    unexpected_dirs = ["test", "tests", "docs", "migrations", "scripts"]
    if intent:
        unexpected = [
            f for f in all_files
            if any(f.startswith(d + "/") for d in unexpected_dirs)
            and f"{d}/" not in intent_lower
        ]
        if unexpected:
            surprises.append(f"Modified support files not mentioned in intent: {', '.join(unexpected[:5])}")

    alignment = keyword_overlap(intent, impl_summary, all_files)
    if not intent and not session.context_complete:
        alignment = 0.5

    return IntentVsImplResult(
        intent=(intent or "Unknown: original intent is unavailable or redacted.")[:500],
        implementation_summary=impl_summary,
        alignment_score=alignment,
        gaps=gaps,
        surprises=surprises,
        context_complete=session.context_complete,
        context_status=session.context_status,
        context_warnings=list(dict.fromkeys(context_warnings)),
    )
