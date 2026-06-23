# Phase 5.3 Intelligence Insight Generation And Review

Branch: `feature/phase-5-3-intelligence-insight-generation-review`

Linear source of truth: FSA-28

## Summary

Phase 5.3 adds reviewed internal intelligence insight generation for the Phase 5 automation pipeline. Admin users can generate a structured `IntelligenceInsight` from an eligible `DocumentAutomationRun`, review and edit the safe summary, approve or reject it, and mark a safe publishing-candidate status for future phases.

This phase preserves the existing Flask/Replit app, public routes, authentication, partner portal, document vault, consent controls, extraction/reconciliation, admin review, redaction controls, publish-readiness controls, entitlement checks, API metadata gates, commercial workflows, scheduled automation, subscriptions, licensed packs, Stripe, Paystack, and Replit configuration.

No external OCR, AI, or paid provider is called. No insight is automatically published.

## Data Model

### `IntelligenceInsight`

Table: `intelligence_insights`

Purpose: stores an internal admin-reviewable intelligence record derived from an automation outcome.

Fields:

- `automation_run_id`
- `actor_document_id`
- `extraction_run_id`
- `insight_type`
- `status`
- `title`
- `summary`
- `safe_summary_json`
- `key_findings_json`
- `governance_flags_json`
- `publishing_candidate_status`
- `review_notes`
- `generated_at`
- `reviewed_at`
- `archived_at`
- `generated_by_user_id`
- `reviewed_by_user_id`
- timestamps from `TimestampMixin`

Supported insight statuses:

- `draft`
- `generated`
- `in_review`
- `approved`
- `rejected`
- `archived`

Supported publishing-candidate statuses:

- `not_candidate`
- `candidate_pending_review`
- `approved_candidate`
- `blocked`

Publishing-candidate status is internal readiness only. It does not create subscriber access, API output, buyer access, public links, file access, or downloads.

## Helper Module

Added:

`intelligence_insights.py`

Responsibilities:

- validate whether an automation run can generate an insight;
- require active consent that permits internal review or extraction-quality use;
- summarize automation and extraction outcomes into safe internal metadata;
- omit private paths, filenames, hashes, contact fields, raw extraction text, extracted values, restricted fields, and API secrets;
- avoid duplicate active insights for the same automation run;
- write safe generation and review audit logs;
- support edit, approve, reject, and archive review actions.

Eligible automation runs must be `completed` or `needs_review`, linked to a document, linked to an extraction run, and still permitted by active internal consent.

## Safe Summary Shape

Insights store and render safe values such as:

- automation run ID and status;
- document ID;
- actor public ID;
- document type name;
- document review, verification, and redaction statuses;
- extraction status and document intelligence status;
- quality score;
- average confidence;
- field count;
- accepted, pending, rejected, and manual override counts;
- mismatch count and mismatch field names only;
- risk flag count and risk flag codes only;
- governance flags confirming no publication or external access.

The insight helper deliberately does not copy:

- storage paths;
- source files;
- original or stored filenames;
- file hashes;
- contact fields;
- raw extraction text;
- extracted field values;
- mismatch current/extracted values;
- restricted document fields;
- API secrets or key hashes.

## Admin Routes

| Route | Method | Purpose |
| --- | --- | --- |
| `/admin/intelligence-insights` | GET | Admin insight review queue with status filter. |
| `/admin/intelligence-insights/<int:insight_id>` | GET | Admin insight detail page with safe summary, findings, governance flags, review form, and audit trail. |
| `/admin/intelligence-insights/<int:insight_id>/review` | POST | Records edit, approve, reject, or archive decisions. |
| `/admin/intelligence-automation/runs/<int:run_id>/generate-insight` | POST | Generates or opens an active insight for an eligible automation run. |

All routes use the existing `login_required` and `admin_required` guards.

The automation run detail page now links to generated insights and offers a Generate Insight action only when the helper reports the run is eligible.

## Review Workflow

Generation creates an insight with:

- `status = generated`;
- `publishing_candidate_status = candidate_pending_review` only for clean completed runs with acceptable confidence and approved/verified documents;
- `publishing_candidate_status = blocked` for needs-review runs or runs with mismatches/risk flags;
- safe generation audit log.

Review actions:

- **Save Edits:** updates title/summary/review notes and moves the insight to `in_review`;
- **Approve:** moves the insight to `approved` and can mark `approved_candidate` only when the safe candidate checks pass;
- **Reject:** moves the insight to `rejected` and blocks candidate status;
- **Archive:** moves the insight to `archived`, sets `archived_at`, and blocks candidate status.

Every decision writes an `AuditLog` row with safe before/after snapshots.

## Governance Boundaries

This phase does not:

- auto-publish insights;
- expose document files;
- expose private storage paths;
- expose source or original filenames;
- expose file hashes;
- expose contact fields;
- expose raw extraction text;
- expose extracted values or restricted fields;
- expose API secrets;
- bypass consent checks;
- bypass document review;
- bypass redaction controls;
- bypass publish-readiness controls;
- bypass entitlement gates;
- change Stripe or Paystack flows;
- call external OCR, AI, or paid providers.

Approval means the insight is internally approved for future governed consideration. It does not grant subscriber, API, buyer, document, or file access.

## Audit Logging

Audit actions include:

- `intelligence_insight_generated`
- `intelligence_insight_updated`
- `intelligence_insight_approved`
- `intelligence_insight_rejected`
- `intelligence_insight_archived`

Audit payloads include safe IDs, statuses, candidate status, safe summaries, and explicit flags confirming no file exposure, no raw extraction text exposure, no automatic publishing, and no external access creation.

## Validation

Added:

```bash
python scripts/validate_phase_5_3_intelligence_insight_review.py
```

Coverage includes:

- insight list is admin-only;
- insight detail is admin-only;
- insight generation action is admin-only;
- insight review action is admin-only;
- insights can be generated from eligible automation runs;
- generated insights contain safe summaries only;
- consent-blocked automation runs cannot generate insights;
- insights can be edited, approved, rejected, and archived;
- audit logs are created for generation and review decisions;
- automation run detail links to generated insights;
- no private paths, filenames, hashes, contact fields, raw extraction text, restricted fields, or secrets render;
- no automatic publishing occurs.

## Manual Replit Steps

After deployment:

1. Restart the Replit app so `db.create_all()` creates the `intelligence_insights` table and the new routes load.
2. Visit `/admin/intelligence-automation/runs` and open a completed or needs-review run.
3. Generate an insight for an eligible run.
4. Review the insight at `/admin/intelligence-insights`.
5. Save edits, approve, reject, and archive test records as appropriate.
6. Confirm document review, redaction, publish targets, entitlements, external access, API output, files, and payment records remain unchanged.
