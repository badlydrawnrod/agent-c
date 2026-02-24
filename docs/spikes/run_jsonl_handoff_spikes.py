from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def run_step(name: str, script_path: Path, env: dict[str, str]) -> None:
    print(f"\n=== {name} ===")
    print(f"Running: uv run {script_path}")

    completed = subprocess.run(
        ["uv", "run", str(script_path)],
        env=env,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"Step '{name}' failed with exit code {completed.returncode}.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run Pydantic JSONL persistence spike, then Copilot JSONL resume spike "
            "using the same session file and session ID."
        )
    )
    parser.add_argument(
        "--session-file",
        default="docs/spikes/session_history.jsonl",
        help="Path to JSONL session file shared by both spikes.",
    )
    parser.add_argument(
        "--session-id",
        default="spike-default",
        help="Session ID key used inside the JSONL file.",
    )
    parser.add_argument(
        "--persist-prompt",
        default="What is the project name?",
        help="Prompt for the Pydantic persistence step.",
    )
    parser.add_argument(
        "--resume-prompt",
        default="Continue the previous conversation and answer briefly.",
        help="Prompt for the Copilot resume step.",
    )
    parser.add_argument(
        "--skip-persist",
        action="store_true",
        help="Skip the Pydantic persistence step and only run the Copilot resume step.",
    )
    args = parser.parse_args()

    workspace_root = Path(__file__).resolve().parents[2]
    persist_script = workspace_root / "docs" / "spikes" / "minimal_inner_core_pydantic_jsonl_spike.py"
    resume_script = workspace_root / "docs" / "spikes" / "minimal_inner_core_copilot_jsonl_resume_spike.py"

    env = os.environ.copy()
    env["SPIKE_SESSION_FILE"] = args.session_file
    env["SPIKE_SESSION_ID"] = args.session_id

    print("JSONL handoff runner")
    print(f"Session file: {args.session_file}")
    print(f"Session id:   {args.session_id}")

    if not args.skip_persist:
        env["SPIKE_PROMPT"] = args.persist_prompt
        run_step("Persist with Pydantic/Ollama", persist_script, env)

    env["SPIKE_PROMPT"] = args.resume_prompt
    run_step("Resume with GitHub Copilot SDK", resume_script, env)

    print("\nDone: handoff sequence completed successfully.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)
