# Phase 3.4 Entitlement-Controlled Access

Branch: `feature/phase-3-4-entitlement-controlled-access`

Linear source of truth: FSA-20

## 1. Summary

Phase 3.4 completes the Phase 3 document governance stack by adding controlled external access to verified document metadata, API-safe metadata exposure, partner correction workflow, and restricted access request capture.

This phase preserves the existing public routes, authentication, subscriber dataset/export flows, admin CSV upload/publish flow, payment flows, partner actor/batch portal, reference options, actor quality scoring, Phase 3 document vault upload/version/download behavior, private storage security, consent controls, extraction/reconciliation, admin review, redaction controls, publish controls, subscriptions, licensed packs, and Replit configuration.

This phase exposes metadata only. It does not expose original files, redacted files, private paths, filenames, public links, downloads, paid document access, buyer access, or PII.

## 2. Models Added

### `DocumentAccessRequest`

Table: `document_access_requests`

Purpose: captures subscriber/API-client requests for restricted document access without granting access automatically.

Fields:

- `actor_document_id`
- `user_id`
- `api_client_id`
- `request_type`
- `request_channel`
- `organization_name`
- `purpose`
- `status`
- `reviewed_by_user_id`
- `reviewed_at`
- `review_notes`
- timestamps

Supported request types:

- `redacted_document`
- `full_document_restricted`

Supported statuses:

- `pending`
- `approved`
- `rejected`
- `cancelled`

No file storage model was changed.

## 3. Shared Access Gate

New helper module:

`document_access.py`

The shared gate evaluates whether a document metadata record can be shown for a channel.

Metadata access requires:

- Publish control target is `ready` or `waived`.
- Consent allows the document category and sharing channel.
- Document is admin approved.
- Document is verified.
- Document is not archived.
- Expiry gate passes.
- Redaction gate passes.
- Latest extraction/reconciliation gate passes.
- High-risk flags are absent unless the target is explicitly waived.
- User/API owner has entitlement through subscription, license, live intelligence, or document entitlement.

Subscriber channel target:

- `subscriber_portal_metadata`

API channel target:

- `api_metadata`

Access request target mapping:

- `redacted_document` -> `redacted_document_candidate`
- `full_document_restricted` -> `full_document_restricted_candidate`

## 4. Subscriber Metadata Routes

Routes added to the existing subscriber blueprint:

| Route | Methods | Purpose |
| --- | --- | --- |
| `/subscriber/document-metadata` | GET | Shows verified document metadata available under the current user's entitlement and governance gates. |
| `/subscriber/document-metadata/<int:document_id>` | GET | Shows one verified metadata record if all gates pass. |
| `/subscriber/document-access-requests/new` | GET, POST | Captures a restricted access request for admin review. |

Subscriber metadata payload deliberately excludes:

- Private storage paths.
- Original filenames and stored filenames.
- File hashes.
- Downloads or file links.
- Actor names.
- Contact details.
- Internal document descriptions.
- Extraction raw text and evidence excerpts.

Displayed metadata is limited to safe fields such as document type, category, reference number, issuing body, dates, crop/commodity, region, verification status, publish status, actor public ID, and actor type.

## 5. API Metadata Route

Route added:

| Route | Methods | Purpose |
| --- | --- | --- |
| `/api/v1/document-metadata` | GET | Returns API-safe verified document metadata only. |

API authentication:

- Uses existing `ApiClient` and `ApiKey`.
- Accepts `Authorization: Bearer <secret>` or `X-API-Key`.
- Verifies the stored key prefix and SHA-256 hash.
- Requires active API key and active API client.
- Requires either the key or client to include `document_metadata:read`.
- Uses the API client's owner user as the entitlement subject.

The API never returns file fields, private paths, actor names, contact details, raw extraction text, or document descriptions.

API usage is recorded in `ApiUsageEvent`. Allowed and blocked document-level attempts are recorded in `DocumentAccessLog`. Invalid key attempts write an `AuditLog` row.

## 6. Entitlement Behavior

The metadata gate reuses `get_user_entitlements(user)`.

Current allowed entitlement paths:

- Active Live Intelligence access, scoped by region/crop.
- Active licensed data pack, scoped by region/crop.
- Active subscription with `actor_activity_status`, scoped by region/crop.
- Active matching `DocumentEntitlement` row for the user, current payment plan, or current licensed pack.

Region scope uses the actor's primary `ActorLocation.region.code`. Crop scope uses document linked crop first, then actor crop, then commodity crop where available.

Free users are blocked.

## 7. Partner Correction Workflow

Routes added to the existing partner blueprint:

| Route | Methods | Purpose |
| --- | --- | --- |
| `/partner/documents/corrections` | GET | Lists partner-owned documents with `needs_correction` or `rejected` review status. |
| `/partner/documents/<int:document_id>/correction` | GET, POST | Lets partner editors update metadata and optionally upload a corrected file version for admin re-review. |

Correction submission:

- Requires an active partner profile.
- Requires document ownership by partner organization.
- Requires editor role.
- Only applies to `needs_correction` or `rejected` documents.
- Updates metadata.
- Optionally creates a new file version using the existing private vault storage guard.
- Sets `document_status = submitted`.
- Sets `review_status = pending`.
- Sets `verification_status = submitted`.
- Writes `partner_document_correction_submitted` audit log.

Correction submission does not publish metadata or grant subscriber/API access.

## 8. Access Request Capture

Subscribers can request:

- Redacted document access.
- Full restricted document access.

The request is only captured when:

- Subscriber metadata access passes for the document.
- Matching publish candidate target is ready or waived.

Captured requests:

- Create `DocumentAccessRequest`.
- Write `DocumentAccessLog`.
- Write `AuditLog`.
- Stay `pending`.
- Do not grant access automatically.

Admin route added:

| Route | Methods | Purpose |
| --- | --- | --- |
| `/admin/document-access-requests` | GET | Lists captured requests for admin review. |

The admin route is review visibility only. Approval/fulfilment is intentionally deferred.

## 9. Audit And Access Logs

Logged events include:

- Subscriber metadata list allowed/blocked.
- Subscriber metadata detail allowed/blocked.
- Subscriber restricted access request created/blocked.
- API metadata allowed/blocked.
- API usage events.
- Unauthorized API metadata attempts.
- Partner correction submissions.

Access attempts use `DocumentAccessLog` where a document exists. API calls use `ApiUsageEvent`. Workflow decisions and request/correction actions use `AuditLog`.

## 10. Validation

New validation script:

```bash
python scripts/validate_phase_3_4_entitlement_controlled_access.py
```

The script validates:

- Subscriber metadata route requires login.
- Entitled subscriber can view verified metadata.
- Free user is blocked.
- Subscriber metadata does not expose private root, filename, actor name, raw description, or file fields.
- Access request creates a pending durable row and audit/access logs.
- API rejects missing key.
- Valid API key returns safe metadata only.
- API blocked document access returns 403 and logs the attempt.
- API usage events are recorded.
- Unauthorized API attempt is audited.
- Admin can view captured access requests.
- Partner correction queue shows admin comments.
- Partner correction submission resets the document for admin review and writes audit log.

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
python scripts/validate_phase_3_4_entitlement_controlled_access.py
python -m compileall app.py models.py routes scripts
git diff --check
```

Expected SQLite validation warning: the existing Postgres-only `migrate_payment_plans_table()` helper prints a `DO $$` SQLite syntax warning during in-memory validation. This warning predates Phase 3.4.

## 11. Manual Replit Steps

After merge:

1. Restart the Replit app so `db.create_all()` can create `document_access_requests`.
2. Confirm Phase 3.3 `document_publish_controls` already exists.
3. Log in as an entitled subscriber and visit `/subscriber/document-metadata`.
4. Confirm metadata is visible only for ready, consented, approved, verified, entitled records.
5. Submit a restricted access request and confirm it appears in `/admin/document-access-requests`.
6. Test `/api/v1/document-metadata` with an active API key linked to an entitled owner user.
7. Log in as a partner editor and visit `/partner/documents/corrections`.

No new environment variables or Replit configuration changes are required.

## 12. Deferred Scope

Deferred to future phases:

- Full document download for subscribers.
- Public document links.
- Paid document checkout.
- Buyer due-diligence portal.
- Visual redaction editor.
- Redacted file generation.
- OCR/AI provider integration.
- Email notification workflow.
- Automatic external publishing without entitlement checks.
- Access request approval/fulfilment workflow.
