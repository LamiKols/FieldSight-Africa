"""Run all FieldSight Africa phase validations in order."""

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

VALIDATION_SCRIPTS = [
    "scripts/validate_phase_1_data_foundation.py",
    "scripts/validate_phase_2_partner_portal.py",
    "scripts/validate_phase_2_1_reference_quality.py",
    "scripts/validate_phase_3_document_vault.py",
    "scripts/validate_phase_3_0_actor_consent.py",
    "scripts/validate_phase_3_1_document_preview_extraction.py",
    "scripts/validate_phase_3_2_admin_document_review.py",
    "scripts/validate_phase_3_3_redaction_publish_controls.py",
    "scripts/validate_phase_3_4_entitlement_controlled_access.py",
    "scripts/validate_phase_4_0_commercial_packaging.py",
    "scripts/validate_phase_4_1_api_productisation.py",
    "scripts/validate_phase_4_2_commercial_operations.py",
    "scripts/validate_phase_4_3_buyer_due_diligence.py",
    "scripts/validate_phase_4_4_commercial_reporting.py",
    "scripts/validate_phase_5_0_intelligence_automation.py",
    "scripts/validate_phase_5_1_automation_run_processing.py",
    "scripts/validate_phase_5_2_scheduled_processing_alerts.py",
    "scripts/validate_phase_5_3_intelligence_insight_review.py",
    "scripts/validate_intelligence_engine_release_1.py",
    "scripts/validate_commercial_demo_launch_readiness.py",
    "scripts/validate_partner_data_owner_onboarding.py",
]


def heading(script_path, index, total):
    print("", flush=True)
    print("=" * 78, flush=True)
    print(f"Validation {index}/{total}: {script_path}", flush=True)
    print("=" * 78, flush=True)


def run_validation(script_path, index, total):
    full_path = REPO_ROOT / script_path
    if not full_path.exists():
        print(f"Missing validation script: {script_path}", file=sys.stderr, flush=True)
        return 1

    heading(script_path, index, total)
    result = subprocess.run(
        [sys.executable, str(full_path)],
        cwd=REPO_ROOT,
        check=False,
    )
    if result.returncode:
        print("", flush=True)
        print(f"FAILED: {script_path} exited with {result.returncode}", file=sys.stderr, flush=True)
        return result.returncode

    print(f"PASSED: {script_path}", flush=True)
    return 0


def main():
    total = len(VALIDATION_SCRIPTS)
    print("FieldSight Africa phase validation runner", flush=True)
    print(f"Running {total} validation scripts in order.", flush=True)
    print("Known non-fatal migration warnings emitted by existing SQLite validators are preserved.", flush=True)

    for index, script_path in enumerate(VALIDATION_SCRIPTS, start=1):
        exit_code = run_validation(script_path, index, total)
        if exit_code:
            return exit_code

    print("", flush=True)
    print("=" * 78, flush=True)
    print("All phase validations passed.", flush=True)
    print("=" * 78, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
