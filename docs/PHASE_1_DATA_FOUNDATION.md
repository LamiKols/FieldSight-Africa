# Phase 1 Data Foundation

Date implemented: 2026-06-17

Linear issue: FSA-6

Branch: `feature/phase-1-data-foundation`

## 1. Models Added

Phase 1 adds passive database foundations to the existing Flask/SQLAlchemy app. No new routes, templates, payment handlers, export handlers, admin upload screens, or customer API endpoints were added.

Partner management:

- `PartnerOrganization`
- `PartnerUserProfile`

Reference data:

- `Region`
- `State`
- `LGA`
- `Crop`
- `Commodity`
- `Port`
- `TradeDestination`
- `CertificationType`

Market actor registry:

- `MarketActor`
- `ActorLocation`
- `ActorContact`
- `ActorExportProfile`
- `ActorCertification`
- `ActorConstraint`

Partner monthly update workflow:

- `PartnerUpdateBatch`
- `PartnerRecordChange`
- `PartnerSubmissionReview`

Document management:

- `DocumentType`
- `ActorDocument`
- `ActorDocumentVersion`
- `DocumentReview`
- `DocumentAccessLog`
- `DocumentEntitlement`

API access foundation:

- `ApiClient`
- `ApiKey`
- `ApiUsageEvent`

Audit logging:

- `AuditLog`

## 2. Why These Models Were Added

FSA-6 defines FieldSight Africa's next direction as a partner-managed agricultural data and document intelligence platform. The new models establish the durable database layer needed for future phases where:

- Partner firms maintain actor registry data.
- Partner firms attach supporting document metadata and private files.
- FieldSight admins review submissions before publishing commercial snapshots.
- Subscribers and future API customers access approved data and documents according to entitlements.

This phase only adds foundations. It does not expose these capabilities through UI or APIs yet.

## 3. Relationship To Existing Models

The implementation preserves the current app structure:

- Existing `User` remains the only login/account model.
- Existing `PaymentPlan`, `LicensedPack`, `License`, `Subscription`, `Payment`, and `LiveIntelligenceAccess` are not replaced.
- Existing `Dataset`, `DatasetMonth`, and `DatasetRecord` remain the commercial dataset publication foundation.
- Existing routes, templates, payment flows, admin upload flow, and CSV export behavior are unchanged.

New models connect to existing models through foreign keys where appropriate:

- `PartnerUserProfile.user_id` links partner roles to existing `User` rows.
- `MarketActor.created_by_user_id` links actor creation to existing users.
- `PartnerUpdateBatch.published_dataset_month_id` can link approved partner batches to an existing `DatasetMonth`.
- `DocumentEntitlement` can link future document access to existing users, payment plans, or licensed packs.
- `ApiClient.owner_user_id` links API clients to existing users.
- `AuditLog.user_id` links auditable actions to existing users.

## 4. Partner Organizations And Existing Users

`PartnerOrganization` represents a firm or data partner.

`PartnerUserProfile` maps an existing `User` to a partner organization and assigns a partner role:

- `partner_admin`
- `data_editor`
- `data_reviewer`
- `partner_viewer`

This avoids creating a second authentication system. Future partner portal work should authenticate with the existing Flask-Login flow and then authorize partner actions through `PartnerUserProfile`.

Supported partner/user statuses are documented in code constants and stored as strings:

- `active`
- `inactive`
- `suspended`
- `pending`

## 5. Actor Registry And Existing Dataset Models

The actor registry foundation maps the FSA-6 actor/exporter template into normalized tables:

- `MarketActor` stores actor type, actor name, commodity category, registration status, registration date, status, and partner ownership.
- `ActorLocation` stores location, state, LGA, country, and optional coordinates.
- `ActorContact` stores restricted phone/email/contact details.
- `ActorExportProfile` stores export years, destination, capacity, and port of exit.
- `ActorCertification` stores certification metadata.
- `ActorConstraint` stores actor constraints.

Existing `Dataset`, `DatasetMonth`, and `DatasetRecord` were not duplicated. `PartnerUpdateBatch` includes:

- `dataset_type`, including `actor_registry`
- `reporting_month`
- `published_dataset_month_id`

Future publishing work can review partner batches and then publish approved commercial data into the existing `DatasetMonth`/`DatasetRecord` structure. No `DataSnapshot` model was added in this phase because `DatasetMonth` already represents a monthly commercial snapshot, and adding another snapshot table now would create overlap without enough workflow behavior to justify it.

## 6. Document Metadata And File Storage

Document metadata is modeled separately from file storage:

- `DocumentType` defines the type, sensitivity, default visibility, and default verification status.
- `ActorDocument` stores actor-linked document metadata and review-facing status fields.
- `ActorDocumentVersion` stores version metadata plus a private `storage_path`.
- `DocumentReview` supports future review workflows.
- `DocumentAccessLog` supports future document access auditing.
- `DocumentEntitlement` supports future document access rules.

Files must not be stored in `static/`. The app now has private storage configuration defaults:

- `PRIVATE_UPLOAD_ROOT`, default `private_uploads`
- `DOCUMENT_STORAGE_BACKEND`, default `local_private`
- `S3_COMPATIBLE_ENDPOINT`, optional future S3-compatible endpoint
- `S3_BUCKET_NAME`, optional future bucket name
- `S3_REGION`, optional future region

`private_uploads/` is added to `.gitignore` so local private files are not committed.

No upload UI, download route, or S3 integration was added in this phase.

## 7. Sensitive Fields And Document Protection

`ActorContact` stores restricted fields:

- phone
- email
- contact name

It defaults to:

- `restricted = True`
- `visibility_level = hidden`

These fields should not be exposed through ordinary subscriber or API access in later phases.

Sensitive document types default to:

- `sensitive = True`
- `default_visibility_level = hidden`
- `default_verification_status = unverified`

Sensitive seeded document types:

- National ID
- NIN Confirmation
- BVN Confirmation
- Bank Account Confirmation
- Tax Identification Number
- CAC Certificate
- Invoice Record
- Delivery Note
- Offtake Agreement

Non-sensitive document types default to `metadata_only`.

## 8. API Key Storage

No API endpoints were added.

The API access foundation includes:

- `ApiClient`
- `ApiKey`
- `ApiUsageEvent`

`ApiKey` intentionally does not include a raw secret column. It stores only:

- `key_prefix`
- `key_hash`

`ApiKey.set_secret(raw_secret)` stores the first eight characters as a lookup prefix and a SHA-256 hash of the raw secret. Raw secrets should only be shown at creation time in a future API-key creation workflow.

## 9. Seed Data Added

New idempotent seed functions were added to `app.py` and are called in the existing startup context after the existing seeds:

- `seed_reference_data()`
- `seed_document_types()`

Seeded regions:

- South West
- South East
- South South
- North Central
- North West
- North East

Seeded crops:

- Ginger
- Sesame
- Soybeans

Seeded document types:

- National ID
- NIN Confirmation
- BVN Confirmation
- CAC Certificate
- Tax Identification Number
- Cooperative Registration Certificate
- Export Registration Certificate
- NEPC Registration
- Phytosanitary Certificate
- Quality Inspection Certificate
- Certificate of Origin
- Organic Certification
- GlobalG.A.P. Certification
- HACCP Certification
- Warehouse Receipt
- Farm Location Evidence
- Field Visit Report
- Verification Checklist
- Offtake Agreement
- Invoice Record
- Delivery Note
- Bank Account Confirmation

Future/add-on commercial plans were not seeded because the current `PaymentPlan` model is tightly tied to subscriber export limits and visible pricing/payment flows. Forcing add-ons into that table now could alter existing pricing behavior. This is intentionally deferred until the commercial plan model is designed.

## 10. Local/Replit Validation

Run the validation script:

```bash
python scripts/validate_phase_1_data_foundation.py
```

The script uses an in-memory SQLite database and does not touch Replit PostgreSQL data. It validates:

- Partner organization creation.
- Partner profile linked to an existing `User`.
- Reference data creation and idempotent seeds.
- Market actor creation.
- Restricted actor contact creation.
- Export profile creation.
- Partner update batch creation.
- Document type and document metadata creation.
- Document version creation.
- API client/key creation.
- API key prefix/hash behavior without raw secret storage.
- Audit log creation.

To validate app startup in Replit:

```bash
python app.py
```

The existing `.replit` workflow still runs `python app.py`, and deployment still uses Gunicorn with `app:app`.

## 11. Environment Variables Added

New environment/config variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `PRIVATE_UPLOAD_ROOT` | `private_uploads` | Private local document storage root for Replit/development. |
| `DOCUMENT_STORAGE_BACKEND` | `local_private` | Future storage backend selector. |
| `S3_COMPATIBLE_ENDPOINT` | unset | Future S3-compatible endpoint. |
| `S3_BUCKET_NAME` | unset | Future S3-compatible bucket name. |
| `S3_REGION` | unset | Future S3-compatible storage region. |

Only `PRIVATE_UPLOAD_ROOT` is required for the local private storage default.

## 12. Intentionally Deferred

Deferred from Phase 1:

- Partner portal UI.
- Document upload UI.
- Admin review screens.
- Customer API endpoints.
- Payment webhook changes.
- CSV export changes.
- A formal migration framework.
- S3-compatible storage implementation.
- Commercial add-on plan seeding in existing payment tables.
- Public/subscriber document access behavior.
- Publishing actor registry rows into commercial snapshots.

These were deferred to preserve the existing working Flask/Replit app and keep Phase 1 focused on database/model/seed/test/documentation foundation.
