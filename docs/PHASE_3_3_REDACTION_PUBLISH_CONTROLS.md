# Phase 3.3 Redaction And Publish Controls

Branch: `feature/phase-3-3-redaction-publish-controls`

Linear source of truth: FSA-19

## 1. Summary

Phase 3.3 adds admin-only redaction status management and controlled publish-readiness gates for actor documents and document-derived metadata.

This phase preserves the existing Flask/Replit app, public routes, authentication, subscriber/export flows, admin CSV upload/publish flow, payment flows, partner actor/batch portal, reference options, actor quality scoring, Phase 3 document vault behavior, Phase 3.0 consent controls, Phase 3.1 preview/extraction/reconciliation behavior, Phase 3.2 admin review behavior, subscriptions, licensed packs, and Replit configuration.

This phase does not publish documents or metadata externally. It only records readiness, blocked, or waived status for later controlled publishing phases.

## 2. Model Added

### `DocumentPublishControl`

Table: `document_publish_controls`

Purpose: stores durable readiness status for a specific `ActorDocument` and publish target.

Fields:

- `actor_document_id`
- `publish_target`
- `status`
- `readiness_checks_json`
- `blocking_reasons_json`
- `admin_decision`
- `notes`
- `decided_by_user_id`
- `decided_at`
- `last_evaluated_at`
- `created_at`
- `updated_at`

Uniqueness:

- `actor_document_id` plus `publish_target`

No existing document, payment, subscriber, export, or partner models were removed or replaced.

## 3. Publish Targets

Supported targets:

- `verified_metadata`
- `licensed_data_pack_metadata`
- `live_intelligence_metadata`
- `subscriber_portal_metadata`
- `api_metadata`
- `redacted_document_candidate`
- `full_document_restricted_candidate`

Target channel mapping:

| Target | Consent sharing channel |
| --- | --- |
| `verified_metadata` | `admin_review` |
| `licensed_data_pack_metadata` | `licensed_data_pack` |
| `live_intelligence_metadata` | `live_intelligence` |
| `subscriber_portal_metadata` | `subscriber_portal` |
| `api_metadata` | `api` |
| `redacted_document_candidate` | `subscriber_portal` |
| `full_document_restricted_candidate` | `approved_buyer_due_diligence` |

## 4. Readiness Checks

Each target evaluation calculates and stores checks for:

- Active actor consent.
- Consent allowing the document category.
- Consent allowing the target sharing channel.
- Admin review and document status being approved.
- Verification status being `verified`.
- Expiry readiness.
- Extraction and reconciliation completion.
- Redaction status.
- Private file existence where file access is relevant.
- Unresolved high-risk flags.

High-risk flags currently treated as blockers:

- `expired_document`
- `metadata_mismatch`
- `missing_reference_number`
- `missing_issuing_body`
- `no_fields_extracted`

`renewal_due_soon` is visible through extraction context but is not treated as a hard Phase 3.3 high-risk blocker.

## 5. Redaction Controls

Route added:

| Route | Methods | Purpose |
| --- | --- | --- |
| `/admin/documents/<int:document_id>/redaction` | GET, POST | Shows and updates redaction status for an actor document. |

Phase 3.3 reuses `ActorDocument.redaction_status` rather than adding a separate redaction table.

Supported admin redaction statuses:

- `not_required`
- `required`
- `in_progress`
- `completed`
- `waived`
- `failed`
- `not_redacted`
- `redaction_required`

The last two values are retained for compatibility with earlier document vault/admin review behavior. The Phase 3.2 `require_redaction` decision still writes `redaction_required`, so prior validation and existing records remain valid.

Updating redaction status writes:

- `ActorDocument.redaction_status`
- `ActorDocument.reviewed_by_user_id`
- `ActorDocument.reviewed_at`
- optional `ActorDocument.review_comments`
- a `DocumentReview` history row
- an `AuditLog` row with action `admin_document_redaction_updated`

## 6. Publish-Control Routes

Routes added:

| Route | Methods | Purpose |
| --- | --- | --- |
| `/admin/documents/<int:document_id>/publish-controls` | GET | Shows computed and stored readiness for all targets. |
| `/admin/documents/<int:document_id>/publish-controls/evaluate` | POST | Evaluates and persists readiness for all targets. |
| `/admin/documents/<int:document_id>/publish-controls/decision` | POST | Saves an admin decision for one target. |

Admin decisions supported:

- Re-evaluate.
- Mark ready, only when all blocking checks pass.
- Mark blocked.
- Waive high-risk flags, only when high-risk flags are the only remaining blockers.

Consent, category, sharing channel, admin review, verification, expiry, redaction, extraction/reconciliation, and file-existence gates are not waivable in this phase.

## 7. Admin Review Integration

`templates/admin/document_review_detail.html` now links to:

- Admin preview.
- Redaction controls.
- Publish controls.

The Phase 3.2 review queue, review detail, preview, and review-decision behavior are otherwise unchanged.

## 8. Security And Non-Publishing Rules

All new routes are protected by the existing `login_required` plus `admin_required` decorators.

This phase does not add:

- Subscriber document pages.
- Public document links.
- Public download routes.
- API document output.
- Buyer due-diligence access.
- Paid document access.
- Automatic publishing.
- Redaction editor UI.

Templates do not expose `storage_path` or private upload root values. File existence checks use the existing private path guard from the partner document vault.

Approval or readiness in this phase remains an internal governance marker. Future phases must still use the persisted readiness controls plus consent helpers before creating any external output.

## 9. Audit Logging

Audit rows are written for:

- `admin_document_redaction_updated`
- `admin_document_publish_readiness_evaluated`
- `admin_document_publish_readiness_decision`

Audit rows include the current admin user, partner organization, document/target context, before/after values, IP address, and user agent.

## 10. Validation

New validation script:

```bash
python scripts/validate_phase_3_3_redaction_publish_controls.py
```

The script validates:

- Ordinary subscribers cannot access redaction or publish controls.
- Partner users cannot access admin publish controls.
- Admin users can access redaction and publish controls.
- Admin redaction updates persist and write audit logs.
- Publish readiness blocks before admin approval.
- Publish readiness passes after active consent, approval, verification, extraction/reconciliation, redaction, expiry, and file checks pass.
- All seven target rows persist.
- High-risk flags block readiness.
- High-risk-only blockers can be explicitly waived.
- Later refused consent blocks readiness.
- No unexpected public/API document routes exist.
- Route/model/script compile checks pass.

Recommended full validation stack:

```bash
python scripts/validate_phase_1_data_foundation.py
python scripts/validate_phase_2_partner_portal.py
python scripts/validate_phase_2_1_reference_quality.py
python scripts/validate_phase_3_document_vault.py
python scripts/validate_phase_3_0_actor_consent.py
python scripts/validate_phase_3_1_document_preview_extraction.py
python scripts/validate_phase_3_2_admin_document_review.py
python scripts/validate_phase_3_3_redaction_publish_controls.py
python -m compileall app.py models.py routes scripts
git diff --check
```

Expected SQLite validation warning: the existing Postgres-only `migrate_payment_plans_table()` helper prints a `DO $$` SQLite syntax warning during in-memory validation. This warning predates Phase 3.3.

## 11. Manual Replit Steps

After merge:

1. Restart the Replit app so `db.create_all()` can create `document_publish_controls`.
2. Log in as an admin.
3. Open `/admin/documents/review-queue`.
4. Open a reviewed actor document.
5. Use Redaction to set a test redaction status.
6. Use Publish Controls to evaluate targets.
7. Confirm blocked targets show concrete reasons and ready targets remain internal governance markers only.
8. Confirm no subscriber document page, API document output, buyer access, or public download route appears.

No new environment variables or Replit configuration changes are required.

## 12. Deferred Scope

Deferred to future phases:

- Subscriber document access.
- External publishing workflow.
- Paid document access.
- Buyer due-diligence portal.
- Public/API document output.
- Visual redaction editor.
- Redacted file generation.
- OCR/AI provider integration.
- Automatic publishing from readiness status.
