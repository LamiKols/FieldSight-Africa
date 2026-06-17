# Phase 3 Actor Document Vault

Branch: `feature/phase-3-actor-document-vault`

Linear source of truth: FSA-8

## 1. Current Phase 3 Summary

Phase 3 adds a partner-facing actor document vault foundation to the existing Flask/Replit app. It preserves the existing public routes, subscriber/export behavior, admin upload/publish flow, payments, subscriptions, licensed packs, partner actor/batch portal, reference options, quality scoring, and Replit configuration.

The implementation uses the Phase 1 document models that already existed:

- `DocumentType`
- `ActorDocument`
- `ActorDocumentVersion`
- `DocumentAccessLog`
- `AuditLog`

No new database models, payment behavior, subscriber document UI, admin review dashboard, or API endpoints were added.

## 2. Partner Routes Added

All routes are registered on the existing `partner_bp` blueprint in `routes/partner.py`.

| Route | Methods | Purpose |
| --- | --- | --- |
| `/partner/actors/<int:actor_id>/documents` | GET | List documents for an actor owned by the current partner organization. |
| `/partner/actors/<int:actor_id>/documents/new` | GET, POST | Upload a new actor document and create the first version. |
| `/partner/documents/<int:document_id>` | GET | Show document metadata, current file metadata, actor link, review/access status, and version history. |
| `/partner/documents/<int:document_id>/edit` | GET, POST | Edit document metadata only. File replacement is intentionally not supported here. |
| `/partner/documents/<int:document_id>/versions/new` | GET, POST | Upload a new file version for an existing document. |
| `/partner/documents/<int:document_id>/download` | GET | Download the current private file when the partner role allows downloads. |

Actor detail pages now include a `Documents` link to the actor vault.

## 3. Access Control

All document vault routes require login and an active `PartnerUserProfile` linked to an active `PartnerOrganization`.

Organization scoping is enforced through:

- `get_partner_actor_or_404(actor_id, profile)` for actor document lists and uploads.
- `get_partner_document_or_404(document_id, profile)` for document detail, edit, version upload, and download.

Permissions:

| Role | Metadata | Upload/edit/version | Download |
| --- | --- | --- | --- |
| `partner_admin` | Yes | Yes | Yes |
| `data_editor` | Yes | Yes | Yes |
| `data_reviewer` | Yes | No | Yes |
| `partner_viewer` | Yes | No | No |
| Ordinary subscriber | No | No | No |

Cross-organization access returns `404` through the existing partner ownership guard.

## 4. Private Storage Behavior

Files are stored under `app.config['PRIVATE_UPLOAD_ROOT']`, defaulting to `private_uploads`.

The storage path pattern is:

```text
private_uploads/actors/<actor_public_id>/documents/document-<document_id>/v<version_number>/<randomized_secure_filename>
```

Files are never written to `static/`. Templates display file metadata such as original filename, stored filename, MIME type, file size, hash prefix, and version number, but they do not render `storage_path` or absolute private paths.

The implementation uses:

- `secure_filename()` for sanitized names.
- A UUID prefix on stored filenames to avoid collisions.
- SHA-256 hashing for uploaded file content.
- A private path guard to ensure saved/downloaded files remain under `PRIVATE_UPLOAD_ROOT`.

## 5. Upload Validation

Allowed extensions:

- `pdf`
- `png`
- `jpg`
- `jpeg`
- `csv`
- `xls`
- `xlsx`

Added environment/config option:

| Variable | Default | Purpose |
| --- | --- | --- |
| `MAX_DOCUMENT_UPLOAD_MB` | `10` | Maximum file size for partner document uploads. |

Oversized files, empty files, and unsafe extensions are rejected before an `ActorDocument` is committed.

## 6. Metadata Form Behavior

The upload/edit form supports:

- Document type
- Title
- Description
- Reference number
- Issuing body
- Issued date
- Expiry date
- Linked crop
- Linked commodity
- Subscriber access level

`DocumentType` requirement flags are enforced:

- `requires_reference_number`
- `requires_issuing_body`
- `requires_expiry_date`

Sensitive document types are forced to:

- `subscriber_access_level = hidden`
- `visibility_level = hidden`

This intentionally overrides any less restrictive submitted value for seeded sensitive document types such as CAC Certificate, National ID, NIN, BVN, bank account confirmation, invoices, delivery notes, and offtake agreements.

## 7. Versioning Behavior

Creating a document writes:

- One `ActorDocument` row with current metadata and current file metadata.
- One `ActorDocumentVersion` row for version `1`.

Uploading a new version:

- Appends a new `ActorDocumentVersion` row.
- Increments `ActorDocument.version_number`.
- Updates current file metadata on `ActorDocument`.
- Leaves previous private files and version rows intact.

Deliberate model choice: `ActorDocumentVersion` does not have an `is_current` flag. The current version is determined by `ActorDocument.version_number` plus the current file metadata stored on `ActorDocument`, matching the Phase 1 data foundation note.

## 8. Audit And Access Logging

Audit rows are written to `AuditLog` for:

- `partner_document_created`
- `partner_document_metadata_updated`
- `partner_document_version_uploaded`

Access rows are written to `DocumentAccessLog` for:

- `metadata_view` on document detail
- `download` on document download

Access logs include the current user, document, current version where available, access type, `partner_portal` access channel, visibility level, IP address, and user agent.

## 9. Templates Added

New partner templates:

- `templates/partner/documents.html`
- `templates/partner/document_form.html`
- `templates/partner/document_detail.html`
- `templates/partner/document_version_form.html`

Updated partner template:

- `templates/partner/actor_detail.html`

The templates follow the existing server-rendered Jinja/Tailwind CDN style used by the partner portal.

## 10. Preserved Areas

Phase 3 did not change:

- Public routes
- Authentication routes
- Subscriber dashboard/dataset/export routes
- CSV export behavior
- Payment, Stripe, Paystack, subscriptions, licensed packs, and webhook code
- Admin CSV upload/publish flow
- Admin reference option screens
- Replit runtime configuration
- Existing database setup pattern
- Existing actor quality scoring behavior

Actor quality scoring still shows document readiness as deferred. FSA-8 focused on vault foundation behavior, not changing the scoring formula.

## 11. Validation

New validation script:

```bash
python scripts/validate_phase_3_document_vault.py
```

On the local Windows workspace used during implementation, the system `python` did not have Flask installed, so validation was run with the repo virtual environment:

```powershell
.venv\Scripts\python.exe scripts\validate_phase_3_document_vault.py
```

The script validates:

- Login required for document routes.
- Ordinary subscribers cannot access partner vault routes.
- Cross-organization actor/document access is denied.
- Editor upload creates `ActorDocument` and `ActorDocumentVersion`.
- Files are saved under `PRIVATE_UPLOAD_ROOT` and not under `static/`.
- File metadata is stored.
- Sensitive document types default to hidden access.
- Invalid extensions are rejected.
- Oversized uploads are rejected.
- Metadata edits do not replace files or create versions.
- New version upload increments `ActorDocument.version_number`.
- Partner viewer can view metadata but cannot download.
- Reviewer can download.
- Download creates `DocumentAccessLog`.
- Create/edit/version actions create `AuditLog` rows.

Expected SQLite validation warning: the existing Postgres-only `migrate_payment_plans_table()` helper prints a `DO $$` SQLite syntax warning during in-memory validation. This warning predates Phase 3 and is also noted in earlier validation docs.

Recommended full validation stack:

```bash
python scripts/validate_phase_1_data_foundation.py
python scripts/validate_phase_2_partner_portal.py
python scripts/validate_phase_2_1_reference_quality.py
python scripts/validate_phase_3_document_vault.py
python -m compileall app.py models.py routes scripts
git diff --check
```

## 12. Gaps And Risks Before Expansion

Still deferred:

- Subscriber document access UI and entitlement enforcement.
- Admin document review dashboard.
- Redaction workflow.
- Signed URLs.
- S3-compatible object storage implementation.
- API document endpoints.
- OCR or AI extraction.
- Bulk document import.
- Payment add-ons for premium document access.
- Formal Alembic-style migration framework.

Current operational risks:

- Local private storage is suitable for Replit/development but should be revisited before high-volume production storage.
- Existing startup migrations remain lightweight and do not replace a proper migration tool.
- Download authorization is partner-only in this phase; future subscriber document access must be added separately and should not reuse partner download rules.
- Sensitive document protection currently relies on seeded `DocumentType.sensitive` metadata and route-level defaults.

## 13. Recommended Safe Next Integration Approach

1. Keep partner upload/review flows separate from subscriber access until entitlement rules are designed.
2. Add admin document review screens before exposing any document content to subscribers.
3. Introduce redaction status transitions before allowing `redacted_document` subscriber access.
4. Add object storage behind the existing `DOCUMENT_STORAGE_BACKEND` and `S3_*` config keys without changing route semantics.
5. Add subscriber-facing access logs before building document APIs.
6. Add migration tooling before broad production schema changes.
7. Keep payment/subscription changes isolated from document vault routes unless a future issue explicitly scopes document monetization.

## 14. Manual Replit Steps

After merging and pulling in Replit:

1. Confirm `PRIVATE_UPLOAD_ROOT` is set or allow the default `private_uploads`.
2. Optionally set `MAX_DOCUMENT_UPLOAD_MB` if 10 MB is not the desired upload cap.
3. Start the existing Replit app flow.
4. Log in as a partner user with `partner_admin` or `data_editor`.
5. Open an owned actor detail page and click `Documents`.
6. Upload a safe test PDF.
7. Confirm the detail page shows metadata and version history.
8. Upload a new version and confirm the version number increments.
9. Log in as `partner_viewer` and confirm metadata is visible but download is denied.
10. Confirm uploaded files are stored under the private upload root, not `static/`.
