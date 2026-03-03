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
            "Run spike handoff flows from one command. Supports JSONL cross-backend "
            "handoff, checkpoint branching demo, and native Pydantic history resume."
        )
    )
    parser.add_argument(
        "--flow",
        choices=[
            "jsonl-handoff",
            "jsonl-checkpoint-demo",
            "pydantic-native-resume",
            "copilot-native-resume",
        ],
        default="jsonl-handoff",
        help=(
            "Flow to run: 'jsonl-handoff' (Pydantic persist -> Copilot resume) or "
            "'jsonl-checkpoint-demo' (local checkpoint branching demonstration) or "
            "'pydantic-native-resume' (Pydantic persist native history -> Pydantic resume), "
            "or 'copilot-native-resume' (Copilot create with session_id -> Copilot resume_session)."
        ),
    )
    parser.add_argument(
        "--session-file",
        default="docs/spikes/session_history.jsonl",
        help="Path to JSONL session file for the jsonl-handoff flow.",
    )
    parser.add_argument(
        "--session-id",
        default="spike-default",
        help="Session ID key used inside the JSONL file.",
    )
    parser.add_argument(
        "--persist-prompt",
        default="What is the project name?",
        help="Prompt for first step in jsonl-handoff flow.",
    )
    parser.add_argument(
        "--resume-prompt",
        default="Continue the previous conversation and answer briefly.",
        help="Prompt for resume step in jsonl-handoff flow.",
    )
    parser.add_argument(
        "--skip-persist",
        action="store_true",
        help="Skip persist step in jsonl-handoff flow and run only Copilot resume.",
    )
    parser.add_argument(
        "--native-history-file",
        default="docs/spikes/pydantic_native_history.json",
        help="Path to native Pydantic history JSON file for pydantic-native-resume flow.",
    )
    parser.add_argument(
        "--native-first-prompt",
        default="What is the project name?",
        help="First prompt for pydantic-native-resume flow.",
    )
    parser.add_argument(
        "--native-second-prompt",
        default="Great. Remind me what project we are discussing.",
        help="Second prompt for pydantic-native-resume flow.",
    )
    parser.add_argument(
        "--copilot-session-id",
        default="spike-copilot-native",
        help="Session ID for copilot-native-resume flow.",
    )
    parser.add_argument(
        "--copilot-first-prompt",
        default="What is the project name?",
        help="First prompt for copilot-native-resume flow.",
    )
    parser.add_argument(
        "--copilot-second-prompt",
        default="Continue from our prior conversation and summarize what we decided.",
        help="Second prompt for copilot-native-resume flow.",
    )
    args = parser.parse_args()

    workspace_root = Path(__file__).resolve().parents[2]
    persist_script = (
        workspace_root / "docs" / "spikes" / "minimal_inner_core_pydantic_jsonl_spike.py"
    )
    resume_script = (
        workspace_root
        / "docs"
        / "spikes"
        / "minimal_inner_core_copilot_jsonl_resume_spike.py"
    )
    native_resume_script = (
        workspace_root
        / "docs"
        / "spikes"
        / "minimal_inner_core_pydantic_native_history_spike.py"
    )
    copilot_native_resume_script = (
        workspace_root
        / "docs"
        / "spikes"
        / "minimal_inner_core_copilot_native_persistence_spike.py"
    )

    env = os.environ.copy()
    print(f"Spike runner flow: {args.flow}")

    if args.flow == "jsonl-handoff":
        env["SPIKE_SESSION_FILE"] = args.session_file
        env["SPIKE_SESSION_ID"] = args.session_id
        env["SPIKE_SESSION_KEY"] = args.session_id

        print("JSONL handoff flow")
        print(f"Session file: {args.session_file}")
        print(f"Session id:   {args.session_id}")

        if not args.skip_persist:
            env["SPIKE_PROMPT"] = args.persist_prompt
            run_step("Persist with Pydantic/Ollama", persist_script, env)

        env["SPIKE_PROMPT"] = args.resume_prompt
        run_step("Resume with GitHub Copilot SDK", resume_script, env)
    elif args.flow == "jsonl-checkpoint-demo":
        env["SPIKE_SESSION_FILE"] = args.session_file
        env["SPIKE_SESSION_ID"] = args.session_id
        env["SPIKE_SESSION_KEY"] = args.session_id
        env["SPIKE_DEMO_MODE"] = "checkpoint-branching"

        print("JSONL checkpoint branching demo flow")
        print(f"Session file: {args.session_file}")
        print(f"Session id:   {args.session_id}")

        run_step("Run local checkpoint branching demo", persist_script, env)
    elif args.flow == "pydantic-native-resume":
        env["SPIKE_NATIVE_HISTORY_FILE"] = args.native_history_file
        env["SPIKE_FIRST_PROMPT"] = args.native_first_prompt
        env["SPIKE_SECOND_PROMPT"] = args.native_second_prompt

        print("Pydantic native resume flow")
        print(f"Native history file: {args.native_history_file}")

        run_step(
            "Persist and resume with Pydantic native history",
            native_resume_script,
            env,
        )
    else:
        env["SPIKE_COPILOT_SESSION_ID"] = args.copilot_session_id
        env["SPIKE_FIRST_PROMPT"] = args.copilot_first_prompt
        env["SPIKE_SECOND_PROMPT"] = args.copilot_second_prompt

        print("Copilot native resume flow")
        print(f"Session id: {args.copilot_session_id}")

        run_step(
            "Persist and resume with Copilot native session persistence",
            copilot_native_resume_script,
            env,
        )

    print("\nDone: handoff sequence completed successfully.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)
