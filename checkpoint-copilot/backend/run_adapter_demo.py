"""Demo: run the adapter against this repo and show one normalized session."""
import json
import sys
from pathlib import Path

# Add the app directory to path so we can run without a package install
sys.path.insert(0, str(Path(__file__).parent / "app"))

from app.adapter import CliCheckpointReader
from app.analysis.insights import generate_insights


def main():
    # This is the actual Entire repo
    repo_path = "/Users/nehalagrawal/cli"
    print(f"=== Checkpoint Copilot — Adapter Demo ===")
    print(f"Repo: {repo_path}")
    print()

    reader = CliCheckpointReader(repo_path)

    # List sessions
    sessions = reader.list_sessions()
    print(f"Found {len(sessions)} session(s)")
    print()

    if not sessions:
        print("No sessions found.")
        return

    # Show a session with checkpoints when available, so the demo exercises the
    # checkpoint parsing path as well as session metadata.
    s = next((session for session in sessions if session.checkpoints), sessions[0])
    session_number = sessions.index(s) + 1
    print(f"--- Session {session_number} of {len(sessions)} ---")
    print(f"ID:          {s.id}")
    print(f"Status:      {s.status}")
    print(f"Agent:       {s.agent_type or '(unknown)'}")
    print(f"Start:       {s.start_time}")
    print(f"End:         {s.end_time}")
    print(f"Checkpoints: {s.total_checkpoints}")
    print(f"Files:       {len(s.all_files_changed)} unique files")
    print(f"Transcript:  {len(s.transcript)} entries")
    print()

    if s.first_user_prompt:
        prompt_preview = s.first_user_prompt[:200]
        print(f"First prompt (truncated): {prompt_preview!r}")
        print()

    if s.checkpoints:
        print("Checkpoints:")
        for cp in s.checkpoints[:5]:
            files = ", ".join(cp.files_changed[:3]) if cp.files_changed else "(no files)"
            print(f"  - {cp.id} @ {cp.timestamp}")
            print(f"    {cp.message[:80] if cp.message else '(no message)'}")
            print(f"    files: {files}")
        print()

    # Run analysis
    print("--- Analysis ---")
    dashboard = generate_insights(sessions)
    print(f"Total sessions:     {dashboard.total_sessions}")
    print(f"Active:             {dashboard.active_sessions}")
    print(f"Ended:              {dashboard.ended_sessions}")
    print(f"Ready for handoff:  {dashboard.ready_for_handoff}")
    print(f"Needs review:       {dashboard.needs_review}")
    print(f"By risk:            {dashboard.sessions_by_risk}")
    print()

    # Show insights for first session
    if dashboard.sessions:
        ins = dashboard.sessions[0]
        print(f"Insights for: {ins.session_id}")
        print(f"  Risk level:        {ins.risk_level} ({ins.risk_score:.2f})")
        print(f"  Intent alignment:  {ins.intent_alignment:.2f}")
        print(f"  Handoff ready:     {ins.handoff_ready}")
        print(f"  Handoff:           {ins.handoff_summary}")
        print(f"  Blockers:          {ins.handoff_blockers}")
        print(f"  Suggestions:       {ins.handoff_suggestions}")
        print(f"  Unfinished work:   {ins.unfinished_work}")
        print(f"  Retry loops:       {ins.retry_loops}")
        print(f"  Abandoned files:   {ins.abandoned_files[:5]}")


if __name__ == "__main__":
    main()
