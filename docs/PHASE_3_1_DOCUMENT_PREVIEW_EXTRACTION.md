# Phase 3.1 Document Preview, Extraction, And Reconciliation

Branch: `feature/phase-3-1-document-preview-extraction-reconciliation`

Linear source of truth: FSA-16

## 1. Summary

Phase 3.1 extends the existing Phase 3 partner document vault with secure inline preview, controlled metadata extraction, and human reconciliation.

This phase preserves the existing Flask/Replit app, public routes, authentication, subscriber/export flows, admin upload/publish flow, payments, subscriptions, licensed packs, partner actor/batch portal, reference options, actor quality scoring, Phase 3 upload/version/download behavior, private file storage security, and Phase 3.0 actor consent controls.

No subscriber document access, paid document add-on, OCR provider, AI extraction provider, bounding-box highlighting, redaction workflow, or automatic metadata overwrite is added.

## 2. Models Added

### `DocumentExtractionRun`

Table: `document_extraction_runs`

Purpose: records each controlled extraction attempt against an `ActorDocument` and its current `ActorDocumentVersion`.

Key fields:

- `actor_document_id`
- `actor_document_version_id`
- `status`
- `extractor_type`
- `document_type_code`
- `template_profile_code`
- `source_filename`
- `extracted_fields_json`
- `confidence_json`
- `field_evidence_json`
- `provenance_json`
- `metadata_mismatches_json`
- `risk_flags_json`
- `expiry_renewal_json`
- `quality_score`
- `document_intelligence_status`
- `manual_correction_notes`
- `raw_text_excerpt`
- `error_message`
- `created_by_user_id`
- timestamps

### `DocumentFieldReconciliation`

Table: `document_field_reconciliations`

Purpose: stores field-level current value, extracted value, evidence/provenance placeholder, review decision, and decision history.

Key fields:

- `actor_document_id`
- `extraction_run_id`
- `field_name`
- `field_label`
- `current_value`
- `extracted_value`
- `accepted_value`
- `confidence`
- `status`
- `evidence_json`
- `provenance_json`
- `risk_flags_json`
- `decision_history_json`
- `manual_correction_notes`
- `reviewed_by_user_id`
- `reviewed_at`
- timestamps

## 3. Preview Route

Route added:

| Route | Methods | Purpose |
| --- | --- | --- |
| `/partner/documents/<int:document_id>/preview` | GET | Streams the current private document version inline for permitted partner users. |

Preview behavior:

- Requires login.
- Requires an active partner profile.
- Reuses `get_partner_document_or_404()` so cross-organization access returns `404`.
- Reuses `current_document_version()` and `resolve_document_storage_path()`.
- Uses `send_file(..., as_attachment=False)` so supported files are rendered inline.
- Adds `Cache-Control: private, no-store`.
- Does not expose `storage_path` or private filesystem roots in templates or route output.

Supported inline preview extensions:

- `pdf`
- `png`
- `jpg`
- `jpeg`
- `csv`

Unsupported files remain stored and downloadable according to the Phase 3 download rules, but the preview panel shows a metadata-only message.

## 4. Preview Access Rules

Partner roles:

| Role | Preview |
| --- | --- |
| `partner_admin` | Yes for supported file types. |
| `data_editor` | Yes for supported file types. |
| `data_reviewer` | Yes for supported file types. |
| `partner_viewer` | Yes for non-sensitive supported file types; metadata-only for sensitive document types. |
| Ordinary subscriber | No partner preview access. |

Consent context:

- Internal partner preview and extraction are allowed for permitted partner roles so partners can review their own uploaded records.
- The preview policy still computes subscriber shareability through `actor_can_share_documents(actor, "subscriber_portal", document_category)`.
- The route returns `X-FieldSight-External-Shareable` so validation can confirm the consent helper was evaluated.
- External subscriber sharing, API exposure, buyer due diligence, and document intelligence output remain blocked unless active actor consent exists and the relevant document category/channel is permitted.

## 5. Extraction Foundation

Route added:

| Route | Methods | Purpose |
| --- | --- | --- |
| `/partner/documents/<int:document_id>/extract` | POST | Creates an extraction run and field reconciliation rows for the current document version. |

Access:

- `partner_admin` and `data_editor` only.
- Same organization guard as all document vault routes.
- Ordinary subscribers and read-only partner viewers cannot run extraction.

Implementation:

- Reads a short private-file text excerpt from the current version.
- Parses deterministic `field: value` or `field=value` lines for known fields.
- Stores extracted values, per-field confidence, evidence placeholders, provenance placeholders, mismatch metadata, risk flags, expiry readiness, and a quality score.
- Does not call OCR, AI, or external APIs.
- Does not automatically change `ActorDocument` metadata.

## 6. Template/Profile Foundation

The first structured profile is:

`certificate_of_origin_v1`

Fields:

- `document_reference_number`
- `issuing_body`
- `issued_at`
- `expires_at`
- `exporter_name`
- `consignee_name`
- `origin_country`
- `destination_country`
- `crop_or_commodity`
- `quantity`
- `port_of_exit`
- `certificate_type`

Other document types use:

`generic_document_metadata_v1`

Generic fields:

- `document_reference_number`
- `issuing_body`
- `issued_at`
- `expires_at`
- `crop_or_commodity`

## 7. Mismatch, Risk, And Quality Signals

Metadata mismatch detection compares extracted values against current `ActorDocument` metadata for mapped fields:

- `document_reference_number`
- `issuing_body`
- `issued_at`
- `expires_at`

Risk flags are stored in `DocumentExtractionRun.risk_flags_json`. Current flags include:

- `missing_reference_number`
- `missing_issuing_body`
- `metadata_mismatch`
- `expired_document`
- `renewal_due_soon`
- `no_fields_extracted`

Expiry readiness is stored in `expiry_renewal_json` with:

- `status`
- `expires_at`
- `days_until_expiry`

`quality_score` is advisory. It combines extraction coverage, confidence, mismatch count, and risk flag count. It does not block existing document workflows.

## 8. Reconciliation Workflow

Route added:

| Route | Methods | Purpose |
| --- | --- | --- |
| `/partner/documents/<int:document_id>/reconcile` | GET, POST | Lets editors review extracted fields and decide what to accept, reject, or override. |

Access:

- `partner_admin` and `data_editor` only.
- Same organization guard as the document detail route.

Supported decisions:

- `accepted`
- `rejected`
- `manually_overridden`

Mapped accepted/overridden fields can update `ActorDocument` metadata:

- `document_reference_number`
- `issuing_body`
- `issued_at`
- `expires_at`

Unmapped fields remain stored in reconciliation rows only. This keeps future OCR/AI expansion possible without silently changing core document metadata.

Every reviewed row stores:

- `accepted_value`
- `status`
- `manual_correction_notes`
- `reviewed_by_user_id`
- `reviewed_at`
- appended `decision_history_json`

## 9. Templates Updated

Updated:

- `templates/partner/document_detail.html`

Added:

- `templates/partner/document_reconcile.html`

The document detail page now includes:

- Preview panel.
- Consent/external-shareability warning.
- Document intelligence status.
- Extraction quality score.
- Risk flags.
- Extract Metadata action for editors.
- Review Extracted Fields link when a run exists.
- Extracted field summary.

The reconciliation page shows current value, extracted value, evidence placeholder, confidence, decision control, override field, and manual notes.

## 10. Audit And Access Logging

Access rows:

- `DocumentAccessLog.access_type = "preview"` for preview route usage.
- Existing `metadata_view` and `download` behavior is unchanged.

Audit rows:

- `partner_document_extraction_created`
- `partner_document_reconciliation_updated`

Audit rows include the current user, partner organization, document entity, and relevant before/after metadata.

## 11. Validation

New validation script:

```bash
python scripts/validate_phase_3_1_document_preview_extraction.py
```

The script validates:

- Partner editor can preview an owned document.
- Ordinary subscriber cannot preview.
- Cross-organization partner cannot preview.
- Preview route does not expose the private upload root.
- Consent helper is evaluated before shareability is marked.
- Partner viewer cannot run extraction or reconciliation.
- Partner editor can trigger extraction.
- `DocumentExtractionRun` row is created.
- `DocumentFieldReconciliation` rows are created.
- Extraction does not auto-update document metadata.
- Editor can accept a mapped field and update document metadata.
- Reconciliation writes decision history.
- Preview, extraction, and reconciliation write access/audit logs.

Expected SQLite validation warning: the existing Postgres-only `migrate_payment_plans_table()` helper prints a `DO $$` SQLite syntax warning during in-memory validation. This warning predates Phase 3.1 and is also noted in earlier validation docs.

## 12. Replit Runtime Notes

No Replit configuration changed.

Existing runtime remains:

- `.replit` runs `python app.py`.
- Deployment remains Gunicorn with `app:app`.
- Private document files continue to use `PRIVATE_UPLOAD_ROOT`.
- `DOCUMENT_STORAGE_BACKEND`, `MAX_DOCUMENT_UPLOAD_MB`, and existing payment environment variables are unchanged.

Manual Replit step after merge:

- Restart the Replit app so `db.create_all()` can create the two new Phase 3.1 tables in the configured database.

## 13. Deferred Scope

Deferred to future phases:

- Full OCR engine.
- AI extraction provider integration.
- Bounding-box highlighting.
- Redaction workflow.
- Subscriber document access.
- Paid document access add-ons.
- Automatic metadata overwrite without human review.
- Bulk extraction.
- S3-compatible object storage migration.

## 14. Safe Integration Approach

Future phases should:

- Continue using `get_partner_document_or_404()` for organization scoping.
- Continue using `resolve_document_storage_path()` before reading private files.
- Keep extraction/reconciliation as internal review until consent helpers allow the relevant external channel/category.
- Add new extraction profiles incrementally instead of assuming one document layout.
- Keep OCR/AI results in `DocumentExtractionRun` and `DocumentFieldReconciliation` until a human accepts mapped fields.
- Add migration handling before relying on altered existing tables in production.
