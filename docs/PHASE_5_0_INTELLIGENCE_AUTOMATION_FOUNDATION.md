# Phase 5.0 Intelligence Automation Foundation

Branch: `feature/phase-5-0-intelligence-automation-foundation`

Linear source of truth: FSA-25

## Summary

Phase 5.0 starts the intelligence automation layer for FieldSight Africa by adding admin-only document intelligence run tracking, safe run orchestration, confidence summaries, retry/cancellation controls, manual queueing for eligible documents, and audit-safe event logging.

This phase preserves the existing Flask/Replit app, public routes, authentication, subscriber/export behavior, payment flows, partner portal, document vault, consent controls, extraction/reconciliation, admin document review, redaction controls, publish-readiness controls, entitlement checks, API metadata gates, commercial workflows, due diligence workflows, commercial reporting, subscriptions, licensed packs, and Replit configuration.

This phase does not call an external OCR or AI provider. It records automation state and safe summaries only.

## Model Added

### `DocumentAutomationRun`

Table: `document_automation_runs`

Purpose: durable tracking for document intelligence automation jobs.

Fields:

- `actor_document_id`
- `actor_document_version_id`
- `extraction_run_id`
- `retry_of_run_id`
- `job_type`
- `trigger_source`
- `status`
- `eligibility_checks_json`
- `confidence_summary_json`
- `event_log_json`
- `notes`
- `error_message`
- `queued_at`
- `started_at`
- `completed_at`
- `cancelled_at`
- `requested_by_user_id`
- `cancelled_by_user_id`
- timestamps from `TimestampMixin`

Supported statuses:

- `queued`
- `running`
- `completed`
- `failed`
- `needs_review`
- `cancelled`

## Admin Routes

| Route | Method | Purpose |
| --- | --- | --- |
| `/admin/intelligence-automation` | GET | Admin dashboard for automation status mix, confidence health, and recent runs. |
| `/admin/intelligence-automation/runs` | GET | Filterable admin run list. |
| `/admin/intelligence-automation/runs/<int:run_id>` | GET | Safe run detail with confidence, eligibility, event, review, and publish-control separation. |
| `/admin/intelligence-automation/runs/<int:run_id>/retry` | POST | Queues a new safe retry run for failed, needs-review, or cancelled runs. |
| `/admin/intelligence-automation/runs/<int:run_id>/cancel` | POST | Cancels queued or running runs only. |
| `/admin/documents/<int:document_id>/automation/run` | POST | Queues a manual run for eligible documents only. |

All routes use the existing `login_required` and `admin_required` guards.

## Eligibility Rules

Manual and retry queueing require:

- document is not archived;
- document is not rejected;
- current document version exists;
- active document type exists;
- active actor consent permits internal review or extraction-quality use;
- no queued or running automation run already exists for the document.

Consent is checked before queueing automation. Missing or insufficient consent blocks new automation runs.

## Confidence Summary

Confidence is summarized from the existing Phase 3.1 data:

- latest extraction run ID;
- latest extraction status;
- document intelligence status;
- quality score;
- average field confidence;
- field count;
- accepted/rejected/pending/manual override counts;
- mismatch count;
- risk flag count;
- low-confidence count.

The summary is advisory and does not alter document metadata, human review, redaction, publish readiness, subscriber access, API access, buyer access, or payment state.

## Separation Of Concerns

Automation pages deliberately separate:

- automation run state;
- automated extraction status;
- human review and verification state;
- publish-readiness target status.

Queueing, retrying, or cancelling an automation run does not:

- approve a document;
- verify a document;
- change redaction status;
- mark publish targets ready;
- publish metadata;
- expose files;
- grant subscriber/API/buyer access.

## Safe Event And Audit Logging

Each run stores `event_log_json` with safe event type, timestamp, message, and non-sensitive metadata.

Audit rows are written for:

- `admin_document_automation_run_queued`
- `admin_document_automation_run_blocked`
- `admin_document_automation_retry_requested`
- `admin_document_automation_retry_blocked`
- `admin_document_automation_run_cancelled`
- `admin_document_automation_cancel_blocked`

Audit payloads explicitly record that:

- files were not exposed;
- storage paths were not exposed;
- source filenames were not exposed;
- raw extraction text was not exposed;
- API secrets were not exposed;
- no data was auto-published;
- no external access was created.

## Filters

The run list supports admin filters for:

- status;
- document type;
- actor public ID or actor type;
- partner organization;
- date window;
- explicit start date;
- confidence minimum;
- confidence maximum.

Supported date windows:

- last 7 days;
- last 30 days;
- last 90 days;
- all time.

## Restricted Data Boundaries

The automation dashboard, run list, and run detail do not render:

- storage paths;
- source files;
- original filenames;
- stored filenames;
- hashes;
- contact fields;
- raw extracted text;
- restricted document fields;
- API secrets;
- API key hashes.

Automation surfaces use safe identifiers such as document IDs, document type names, actor public IDs, partner organization names, statuses, and aggregate confidence counts.

## Validation

Added:

```bash
python scripts/validate_phase_5_0_intelligence_automation.py
```

The validation covers:

- dashboard is admin-only;
- run list and detail are admin-only;
- run statuses persist correctly;
- retry creates a new queued safe run;
- cancellation works only for queued/running runs;
- manual run trigger works only for eligible documents;
- blocked manual runs write audit logs and do not create runs;
- confidence summary renders;
- automation pages do not render private paths, filenames, hashes, contact fields, raw extraction text, restricted fields, or secrets;
- admin dashboard links to automation.

## Manual Replit Steps

Phase 5.0 adds the `document_automation_runs` table.

After deployment, restart the Replit app so the existing `db.create_all()` startup path can create the new table.

Recommended smoke checks:

1. Log in as admin.
2. Visit `/admin/intelligence-automation`.
3. Open `/admin/intelligence-automation/runs`.
4. Open a document review detail page.
5. Queue automation for a consent-eligible document.
6. Open the queued run and confirm the automation, extraction, human review, and publish readiness sections stay separate.
7. Cancel a queued run.
8. Retry a failed or needs-review run.
9. Confirm no file path, filename, hash, contact field, raw extraction text, secret, subscriber access, API output, buyer access, or public link appears.
