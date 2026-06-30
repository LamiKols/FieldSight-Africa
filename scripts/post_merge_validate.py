"""Run post-merge validation for the FieldSight Africa Replit runtime."""

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

COMMANDS = [
    {
        "label": "Run all phase validations",
        "command": [sys.executable, "scripts/validate_all_phases.py"],
    },
    {
        "label": "Compile core application modules",
        "command": [
            sys.executable,
            "-m",
            "compileall",
            "app.py",
            "models.py",
            "routes",
            "scripts",
            "intelligence_insights.py",
        ],
    },
    {
        "label": "Check git diff whitespace",
        "command": ["git", "diff", "--check"],
    },
]


def run_command(label, command):
    print("", flush=True)
    print("=" * 78, flush=True)
    print(label, flush=True)
    print("$ " + " ".join(command), flush=True)
    print("=" * 78, flush=True)
    result = subprocess.run(command, cwd=REPO_ROOT, check=False)
    if result.returncode:
        print(f"FAILED: {label} exited with {result.returncode}", file=sys.stderr, flush=True)
        return result.returncode
    print(f"PASSED: {label}", flush=True)
    return 0


def main():
    print("FieldSight Africa post-merge validation", flush=True)
    for item in COMMANDS:
        exit_code = run_command(item["label"], item["command"])
        if exit_code:
            return exit_code
    print("", flush=True)
    print("=" * 78, flush=True)
    print("Post-merge validation passed.", flush=True)
    print("=" * 78, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
