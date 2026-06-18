# Phase 3.2 Admin Document Review And Approval

Branch: `feature/phase-3-2-admin-document-review-approval`

Linear source of truth: FSA-18

## 1. Summary

Phase 3.2 adds an admin-facing review workflow for partner-submitted actor documents. Admins can inspect document metadata, actor and partner details, consent status, private preview, Phase 3.1 extraction output, reconciliation rows, risk flags, mismatch count, expiry readiness, review status, verification status, and sensitive document status before recording a decision.

This phase preserves the existing public pages, authentication, subscriber dashboard/export flows, admin CSV upload/publish flow, Stripe/Paystack payment flows, subscriptions, licensed packs, partner actor/batch portal, reference options, actor quality scoring, Phase 3 document vault upload/version/download behavior, private storage guards, Phase 3.0 consent controls, Phase 3.1 preview/extraction/reconciliation behavior, and Replit configuration.

No subscriber document access, external document publishing, paid document access, redaction editor, OCR/AI provider, actor self-service correction portal, email workflow, or document API exposure is added.

## 2. Admin Routes

Routes added to the existing `admin_bp` blueprint:

| Route | Methods | Purpose |
| --- | --- | --- |
| `/admin/documents/review-queue` | GET | Lists partner-submitted documents requiring admin attention, with practical filters. |
| `/admin/documents/<int:document_id>/review` | GET | Shows full admin review detail for one actor document. |
| `/admin/documents/<int:document_id>/preview` | GET | Streams the current private file inline for admin-only internal review. |
| `/admin/documents/<int:document_id>/review/decision` | POST | Records an admin decision and audit log. |

All routes use the existing `login_required` and `admin_required` decorators. Ordinary subscribers and partner users are redirected away from these routes.

## 3. Queue Behavior

The queue defaults to documents with review status:

- `pending`
- `needs_correction`
- `redaction_required`

Filters are available for:

- Review status.
- Verification status.
- Document type.
- Partner organization.
- Extraction status.
- Risk flag.
- Consent status.

Each queue row shows:

- Document title and type.
- Actor name.
- Partner organization.
- Review and verification status.
- Consent status.
- Extraction status.
- Mismatch count.
- Risk flag count.
- Expiry readiness.
- Updated date.
- Review action link.

## 4. Review Detail

The review detail page shows:

- Actor and partner summary.
- Consent panel with document category and external channel permissions.
- Document metadata.
- Admin-only inline preview.
- Current review, verification, redaction, sensitive, and subscriber-access state.
- Extraction/intelligence status.
- Quality score.
- Risk flags.
- Mismatch count.
- Expiry readiness.
- Reconciliation rows.
- Decision form.
- Review history.

## 5. Decision Actions

Supported actions:

- `approve`
- `reject`
- `request_correction`
- `require_redaction`
- `mark_verified`
- `mark_unverified`

Current state is stored on existing `ActorDocument` fields:

- `review_status`
- `document_status`
- `verification_status`
- `redaction_status`
- `reviewed_by_user_id`
- `reviewed_at`
- `review_comments`

Decision history is stored in the existing `DocumentReview` table. A row is written for every admin decision with the document, current version, reviewer, status, notes, and review timestamp.

Correction and rejection reasons are stored in `DocumentReview.notes` and copied to `ActorDocument.review_comments` so future partner correction workflows can display them.

## 6. Approval Meaning

Approval in this phase means admin-approved for internal review/verification use only.

Approval does not:

- Change `subscriber_access_level`.
- Change `visibility_level`.
- Publish the document externally.
- Add subscriber document access.
- Add API or buyer due-diligence access.
- Override actor consent.

External sharing remains governed by the Phase 3.0 consent helpers and future publishing/access workflows.

## 7. Consent-Aware Rules

Admins can review documents internally even when consent is missing or insufficient.

The UI warns when:

- No active actor consent exists.
- Active consent exists but does not allow all external document channels considered by this review surface.

External channels shown:

- `subscriber_portal`
- `api`
- `approved_buyer_due_diligence`

The document consent category is derived with `consent_document_category_for_document_type(document.document_type)`, matching Phase 3.0 behavior.

## 8. Preview And Security

The admin preview route:

- Requires admin access.
- Uses the current `ActorDocumentVersion`.
- Reuses Phase 3 private path resolution through `resolve_document_storage_path()`.
- Returns inline content for supported preview types.
- Sets `Cache-Control: private, no-store`.
- Sets `X-Content-Type-Options: nosniff`.
- Does not expose private storage paths in templates.

Supported preview extensions:

- `pdf`
- `png`
- `jpg`
- `jpeg`
- `csv`

Unsupported file types remain unavailable for inline preview in this phase.

## 9. Extraction And Reconciliation Relationship

The admin detail page reads Phase 3.1 records:

- `DocumentExtractionRun`
- `DocumentFieldReconciliation`

It displays:

- Extraction run status.
- Document intelligence status.
- Quality score.
- Risk flags.
- Metadata mismatch count.
- Expiry readiness.
- Reconciliation row status.

Admins do not run OCR, AI extraction, or reconciliation from the admin route in this phase. Partner Phase 3.1 extraction/reconciliation behavior is preserved.

## 10. Audit Logging

Each admin decision writes an `AuditLog` row:

- `admin_document_review_approved`
- `admin_document_review_rejected`
- `admin_document_correction_requested`
- `admin_document_redaction_required`
- `admin_document_verification_updated`

Audit logs include:

- Current admin user.
- Partner organization ID.
- Document ID.
- Actor ID in before/after payload.
- Partner organization ID in before/after payload.
- Before values.
- After values.
- Request IP and user agent.

Admin review detail and preview also write `DocumentAccessLog` rows with `access_channel = admin_review`.

## 11. Templates

Templates added:

- `templates/admin/document_review_queue.html`
- `templates/admin/document_review_detail.html`

Template updated:

- `templates/admin/dashboard.html`

The dashboard now shows pending document review count and links to the review queue.

## 12. Validation

New validation script:

```bash
python scripts/validate_phase_3_2_admin_document_review.py
```

The script validates:

- Ordinary subscriber cannot access the admin review queue.
- Partner user cannot access the admin review queue.
- Admin can access the queue.
- Queue shows submitted partner document.
- Admin can open review detail.
- Detail shows actor, partner, consent warning, extraction/risk/reconciliation context, and sensitive flag.
- Admin-only preview uses private path guard and does not leak private root.
- Admin can approve, request correction, reject, require redaction, mark verified, and mark unverified.
- Audit logs are written.
- Review history rows are written.
- Approval does not change subscriber access or visibility.
- Missing consent warns but does not block internal admin review.

Recommended full validation stack:

```bash
python scripts/validate_phase_1_data_foundation.py
python scripts/validate_phase_2_partner_portal.py
python scripts/validate_phase_2_1_reference_quality.py
python scripts/validate_phase_3_document_vault.py
python scripts/validate_phase_3_0_actor_consent.py
python scripts/validate_phase_3_1_document_preview_extraction.py
python scripts/validate_phase_3_2_admin_document_review.py
python -m compileall app.py models.py routes scripts
git diff --check
```

Expected SQLite validation warning: the existing Postgres-only `migrate_payment_plans_table()` helper prints a `DO $$` SQLite syntax warning during in-memory validation. This warning predates Phase 3.2 and is noted in earlier phase docs.

## 13. Manual Replit Steps

After merge:

1. Restart the Replit app.
2. Log in as an admin user.
3. Visit `/admin/documents/review-queue`.
4. Open a submitted document.
5. Confirm actor, partner, consent, preview, extraction, reconciliation, risk, expiry, and review state render.
6. Record an approve, correction, rejection, redaction, and verification decision on test records.
7. Confirm no subscriber document page or API exposure appears.

No new environment variables or Replit configuration changes are required.

## 14. Deferred Scope

Deferred to future phases:

- Subscriber document access.
- External publishing workflow.
- Paid document access.
- Redaction editor.
- OCR or AI provider integration.
- Actor self-service correction portal.
- Email notification workflow.
- API exposure of documents.
- Automated approval without human review.
