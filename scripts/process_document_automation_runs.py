"""Process queued FieldSight document automation runs in a bounded batch."""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app import app  # noqa: E402
from document_automation import (  # noqa: E402
    DEFAULT_BATCH_LIMIT,
    DEFAULT_STALE_MINUTES,
    process_queued_runs,
    recover_stale_runs,
)


def run_batch(limit=DEFAULT_BATCH_LIMIT, stale_minutes=DEFAULT_STALE_MINUTES, stale_action="requeue"):
    with app.app_context():
        stale_summary = recover_stale_runs(
            stale_minutes=stale_minutes,
            action=stale_action,
            actor_user_id=None,
        )
        processing_summary = process_queued_runs(limit=limit, actor_user_id=None)
        return {
            "stale": stale_summary,
            "processing": processing_summary,
            "auto_published": False,
            "external_access_created": False,
        }


def parse_args():
    parser = argparse.ArgumentParser(description="Process queued document intelligence automation runs.")
    parser.add_argument("--limit", type=int, default=DEFAULT_BATCH_LIMIT)
    parser.add_argument("--stale-minutes", type=int, default=DEFAULT_STALE_MINUTES)
    parser.add_argument("--stale-action", choices=["requeue", "fail"], default="requeue")
    return parser.parse_args()


def main():
    args = parse_args()
    summary = run_batch(
        limit=args.limit,
        stale_minutes=args.stale_minutes,
        stale_action=args.stale_action,
    )
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
