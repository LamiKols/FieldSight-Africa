# Phase 5.2 Scheduled Processing And Alerts

Branch: `feature/phase-5-2-scheduled-processing-alerts`

Linear source of truth: FSA-27

## Summary

Phase 5.2 adds a controlled scheduling layer around the deterministic Phase 5.1 document automation processor. Admin users can configure whether scheduled processing is enabled, set bounded processing and stale-run controls, run the configured cycle manually, and monitor operational alerts.

The schedule does not call external OCR or AI providers and does not publish data. Existing consent, review, redaction, publish-readiness, entitlement, subscriber/API/buyer access, Stripe, and Paystack behavior remains authoritative and unchanged.

## Data Model

### AutomationScheduleConfig

Table: `automation_schedule_configs`

The single `document_intelligence` configuration stores:

- enabled state, defaulting to disabled;
- bounded batch limit;
- stale-run threshold in minutes;
- stale-run action: `requeue` or `fail`;
- operator-facing processing frequency label;
- internal admin notes;
- last run timestamp and status;
- the admin user that last updated the configuration.

Batch limits and stale thresholds use the Phase 5.1 clamps. Invalid stale actions fall back to `requeue`. The frequency label and notes are length-limited before persistence.

### AutomationScheduledRunLog

Table: `automation_scheduled_run_logs`

Each attempted scheduled cycle stores only safe operational metadata:

- trigger source and lifecycle status;
- requesting admin ID when manually invoked;
- start and completion timestamps;
- queue count before processing;
- stale, selected, processed, completed, needs-review, failed, and skipped counts;
- a controlled summary and safe error code.

Supported log statuses are:

- `running`;
- `completed`;
- `completed_with_attention`;
- `skipped_disabled`;
- `failed`.

Run logs do not store storage paths, filenames, hashes, contact fields, raw extraction text, restricted document fields, API credentials, or exception text.

## Scheduler Module

Added:

`automation_scheduler.py`

Responsibilities:

- load or create the disabled-by-default schedule configuration;
- update validated configuration values and write an audit entry;
- create and finalize safe scheduled-run logs;
- reuse Phase 5.1 `recover_stale_runs()` and `process_queued_runs()` helpers;
- report safe operational metrics and alert summaries;
- convert unexpected failures into a controlled error code and message.

`execute_scheduled_processing()` always checks the persisted enabled state. This includes the admin Run Now action: when the schedule is disabled, it creates a `skipped_disabled` log and does not recover or process any automation run.

When enabled, one cycle first applies the configured stale-run action and then processes at most the configured batch limit. A cycle is marked `completed_with_attention` when processing produces failed or needs-review outcomes, or stale runs are failed.

## Admin Routes

| Route | Method | Purpose |
| --- | --- | --- |
| `/admin/intelligence-automation/schedule` | GET | Shows configuration, monitoring metrics, alerts, repeated failures, and recent safe run logs. |
| `/admin/intelligence-automation/schedule/update` | POST | Persists validated schedule settings and writes an audit entry. |
| `/admin/intelligence-automation/schedule/run-now` | POST | Executes one configured scheduled-processing cycle when enabled. |

All routes use the existing `login_required` and `admin_required` guards.

The main intelligence automation dashboard now links to schedule controls and displays the same operational alert summary without restricted document content.

## Operational Alerts

The monitoring summary reports:

- **Failed Runs:** automation runs currently in `failed` state;
- **Stale Running:** running jobs older than the configured threshold;
- **Needs Review:** outcomes awaiting human review;
- **Repeated Failures:** documents with two or more failed automation runs;
- **Queue Backlog:** queued jobs exceeding one configured batch.

Alert payloads contain counts and controlled messages only. Repeated failures show document IDs and failure counts, not document metadata or file information.

Additional metrics include queued and running counts plus completed and failed counts from the previous 24 hours.

## Scheduled Runner

Added:

`scripts/run_scheduled_document_automation.py`

Example:

```bash
python scripts/run_scheduled_document_automation.py
```

The command executes one cycle using the persisted schedule configuration and prints a safe JSON summary. It is suitable for a Replit Scheduled Deployment or another trusted scheduler. Scheduling frequency is deliberately configured outside application code; the stored frequency label documents the intended cadence but does not create a background thread or cron process.

## Governance And Audit

Audit actions include:

- `admin_automation_schedule_updated`;
- `automation_scheduled_run_started`;
- `automation_scheduled_run_skipped_disabled`;
- `automation_scheduled_run_completed`;
- `automation_scheduled_run_failed`.

The scheduler delegates individual run events and confidence updates to the Phase 5.1 processor. It does not change:

- document review or verification status;
- redaction status;
- publish-control status;
- actor consent records;
- subscriptions, licences, or entitlements;
- subscriber, API, or buyer access;
- Stripe or Paystack records.

No processing cycle automatically publishes data or creates external access.

## Validation

Added:

```bash
python scripts/validate_phase_5_2_scheduled_processing_alerts.py
```

Coverage includes:

- admin-only schedule page, update action, and Run Now action;
- safe configuration persistence and value clamping;
- disabled schedules process no queued runs;
- enabled schedules reuse the Phase 5.1 processor with the configured batch limit;
- stale-run handling through the configured action;
- safe scheduled-run log creation;
- failed, stale, needs-review, repeated-failure, and backlog alert rendering;
- scheduler script execution;
- restricted/private content omission;
- unchanged blocked publish controls and no automatic publishing.

## Manual Replit Steps

After deployment:

1. Restart the Replit app so `db.create_all()` creates `automation_schedule_configs` and `automation_scheduled_run_logs` and the new routes load.
2. Open `/admin/intelligence-automation/schedule`, review the defaults, and leave processing disabled until the settings are approved.
3. Set the intended batch limit, stale threshold/action, frequency label, and operational notes.
4. Enable the schedule only when processing is operationally approved.
5. Use Run Now for a controlled smoke test and inspect the safe log and alert counts.
6. If recurring execution is required, configure the trusted Replit scheduler to run `python scripts/run_scheduled_document_automation.py` at the approved cadence.
7. Confirm document review, redaction, publish targets, entitlements, external access, and payment records remain unchanged.
