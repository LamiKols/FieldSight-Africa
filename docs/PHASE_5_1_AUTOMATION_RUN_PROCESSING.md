# Phase 5.1 Automation Run Processing

Branch: `feature/phase-5-1-automation-run-processing`

Linear source of truth: FSA-26

## Summary

Phase 5.1 processes queued `DocumentAutomationRun` records through an internal, deterministic, auditable document intelligence layer.

It preserves the existing Flask/Replit app, public routes, authentication, partner document vault, Phase 3 extraction/reconciliation behavior, consent controls, admin review, redaction, publish readiness, subscriber/API/buyer entitlement gates, payment flows, commercial workflows, Phase 5.0 queueing/retry/cancellation behavior, and Replit configuration.

No external OCR, AI, or paid provider is called. No data is automatically published.

## Processing Module

Added:

`document_automation.py`

Responsibilities:

- process one queued run;
- process a bounded queue batch;
- recover stale running runs;
- validate consent and document eligibility before extraction;
- reuse the existing deterministic extraction profile and reconciliation-row creation logic;
- persist safe status transitions, confidence summaries, events, and audits;
- convert failures into safe error codes/messages.

## Status Transitions

Supported transitions:

- `queued` to `running` when processing starts;
- `running` to `completed` when deterministic extraction finishes without extraction risk/mismatch flags;
- `running` to `needs_review` when extraction identifies mismatches/risks or governance requires human review;
- `running` to `failed` when the private version/file is unavailable or processing fails safely;
- `running` to `queued` when a stale run is explicitly recovered with the requeue action;
- `running` to `failed` when a stale run is explicitly recovered with the fail action;
- `queued` or `running` to `cancelled` through the existing Phase 5.0 admin cancellation control.

Non-queued runs are not reprocessed by the processor.

## Deterministic Extraction Reuse

The processor reuses existing Phase 3.1 helpers:

- `document_extraction_payload()`;
- `create_reconciliation_rows()`;
- `document_version_file_metadata()`;
- `resolve_document_storage_path()`.

Each successful processing attempt creates a new `DocumentExtractionRun` and field reconciliation rows linked to the automation run.

Automation-created extraction runs deliberately store:

- `extractor_type = automation_template`;
- `source_filename = null`;
- `raw_text_excerpt = null`.

Structured internal extraction/reconciliation data remains in the existing governed tables. Automation pages and event logs do not render extracted field values, evidence content, filenames, paths, hashes, or raw text.

## Governance Checks

Before file processing, the processor rechecks:

- linked document exists;
- document is not archived or rejected;
- active actor consent exists;
- consent permits extraction-quality use, internal review, or admin review;
- the version recorded on the automation run exists;
- the private storage reference resolves through the existing path guard;
- the private file exists.

Consent failure moves the run to `needs_review` without creating extraction output.

Processing does not change:

- document review status;
- document verification status;
- redaction status;
- publish-control status;
- subscriptions, licences, or entitlements;
- Stripe or Paystack records;
- subscriber, API, or buyer access.

## Confidence Summary Updates

After extraction/reconciliation rows are created, the processor refreshes:

- latest extraction run ID and status;
- document intelligence status;
- quality score;
- average confidence;
- field count;
- accepted, rejected, pending, and manual override counts;
- mismatch count;
- risk flag count;
- low-confidence count.

These are internal operational signals only.

## Safe Failures

Failed runs store only controlled messages such as:

- linked document unavailable;
- linked version unavailable;
- private file unavailable;
- private file reference could not be resolved safely;
- processing failed safely;
- stale running timeout.

Exception text, storage paths, source filenames, hashes, raw extraction text, contact details, and secrets are not copied into run errors, event metadata, or audit payloads.

## Stale Running Recovery

Runs are stale when their `started_at` (or fallback update/create timestamp) is older than the configured threshold.

Supported actions:

- `requeue`: returns the run to `queued`, clears running/completion/error state, and records safe event/audit history;
- `fail`: marks the run `failed` with the controlled stale-timeout message.

Default threshold: 30 minutes.

## Admin Routes

| Route | Method | Purpose |
| --- | --- | --- |
| `/admin/intelligence-automation/runs/<int:run_id>/process` | POST | Processes one queued run. |
| `/admin/intelligence-automation/process-queued` | POST | Recovers stale runs and processes a bounded queued batch. |

Both routes use the existing `login_required` and `admin_required` guards.

The automation dashboard now shows:

- queued;
- running;
- completed;
- needs review;
- failed;
- processed in the last 24 hours;
- stale running;
- average confidence.

## Batch Script

Added:

`scripts/process_document_automation_runs.py`

Example:

```bash
python scripts/process_document_automation_runs.py --limit 10 --stale-minutes 30 --stale-action requeue
```

Options:

- `--limit`: bounded number of queued runs, clamped to 1-100;
- `--stale-minutes`: stale threshold, clamped to 1-1440;
- `--stale-action`: `requeue` or `fail`.

The script prints a JSON summary containing safe counts and run IDs only.

## Event And Audit Logging

Safe event/audit actions include:

- `document_automation_run_started`;
- `document_automation_run_completed`;
- `document_automation_run_needs_review`;
- `document_automation_run_failed`;
- `document_automation_stale_run_requeued`;
- `document_automation_stale_run_failed`.

Payloads explicitly record:

- no file exposure;
- no storage path exposure;
- no source filename exposure;
- no raw extraction text exposure;
- no restricted field exposure;
- no API secret exposure;
- no automatic publishing;
- no external access creation.

## Validation

Added:

```bash
python scripts/validate_phase_5_1_automation_run_processing.py
```

Coverage includes:

- single process route is admin-only;
- batch process route is admin-only;
- batch CLI helper processes queued runs;
- queued to running to completed transition;
- queued to running to needs-review transition;
- safe failed transition for missing files;
- consent-blocked processing creates no extraction output;
- stale running requeue and completion;
- confidence summary updates;
- safe event and audit updates;
- source filename and raw text omission on automation extraction records;
- no private/restricted content renders;
- publish readiness, review, and redaction remain unchanged;
- non-queued runs are not reprocessed.

## Manual Replit Steps

No new Phase 5.1 table is added. Phase 5.1 uses the Phase 5.0 `document_automation_runs` table plus existing extraction/reconciliation/audit tables.

After deployment:

1. Restart the Replit app so the new processor module and admin routes load.
2. Confirm the Phase 5.0 `document_automation_runs` table already exists.
3. Queue an eligible document automation run.
4. Process the run from the admin detail page or bounded dashboard batch control.
5. Optionally run the batch script from the Replit shell.
6. Confirm no publish target, subscriber/API/buyer access, payment state, path, filename, hash, raw text, contact field, or secret changes.
