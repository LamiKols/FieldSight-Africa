"""Execute one configured FieldSight document automation schedule cycle."""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app import app  # noqa: E402
from automation_scheduler import execute_scheduled_processing  # noqa: E402


def run_scheduled_cycle(trigger_source="scheduler_script"):
    with app.app_context():
        return execute_scheduled_processing(
            trigger_source=trigger_source,
            actor_user_id=None,
        )


def main():
    summary = run_scheduled_cycle()
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
