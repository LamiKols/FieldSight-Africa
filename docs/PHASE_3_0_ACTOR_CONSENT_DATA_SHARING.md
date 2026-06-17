# Phase 3.0 Actor Consent And Data Sharing

Branch: `feature/phase-3-0-actor-consent-data-sharing`

Linear source of truth: FSA-17

## 1. Summary

Phase 3.0 adds a partner-facing actor consent and data-sharing governance foundation to the existing Flask/Replit app.

The goal is to record what an actor has authorized before FieldSight Africa expands into publishing, subscriber document access, API exposure, buyer due diligence, document extraction, or advanced document intelligence workflows.

This phase preserves the existing public pages, authentication, subscriber dashboard/export flows, admin upload/publish flow, Stripe/Paystack payment flows, subscriptions, licensed packs, partner actor/batch portal, reference options, actor quality scoring, Phase 3 document vault behavior, private file storage security, and Replit configuration.

## 2. Consent Model

New model:

`ActorConsentRecord`

Table:

`actor_consent_records`

Fields:

- `id`
- `market_actor_id`
- `partner_organization_id`
- `consent_status`
- `consent_scope_json`
- `permitted_data_categories_json`
- `permitted_document_categories_json`
- `sharing_channels_json`
- `consent_method`
- `consent_reference`
- `consent_document_id`
- `granted_by_name`
- `granted_by_role`
- `granted_by_email`
- `granted_by_phone`
- `granted_at`
- `expires_at`
- `withdrawn_at`
- `withdrawal_reason`
- `captured_by_user_id`
- `review_status`
- `reviewed_by_user_id`
- `reviewed_at`
- `review_notes`
- `active`
- `created_at`
- `updated_at`

The model is scoped to both `MarketActor` and `PartnerOrganization`. This keeps consent history attached to the partner-owned actor record and prevents cross-organization consent access in partner routes.

`consent_document_id` can link to an uploaded `ActorDocument` when a signed consent form is stored in the Phase 3 private document vault.

## 3. Consent Statuses

Supported statuses:

- `not_requested`
- `requested`
- `granted`
- `refused`
- `withdrawn`
- `expired`

Display rules:

- Granted: green badge
- Requested: amber badge
- Not Requested: grey badge
- Refused, Withdrawn, Expired: red badge

Expiry is enforced by helper logic. A `granted` record with `expires_at` in the past is not active.

## 4. Consent Methods

Supported methods:

- `written`
- `digital_checkbox`
- `uploaded_form`
- `email_confirmation`
- `verbal_pending_written_confirmation`
- `partner_attestation`

When a partner creates a granted consent record, the form requires a consent method and grantor name. If `granted_at` is blank for granted consent, the app uses the current UTC time.

## 5. Consent Scopes

Supported granular scopes:

- Store actor profile data internally
- Store actor documents internally
- Use actor data for verification/review
- Share basic actor profile with subscribers
- Share restricted contact data with approved users only
- Share document metadata with subscribers
- Share redacted documents with subscribers
- Share full documents with approved users only
- Include actor in paid data packs
- Include actor in live intelligence reports
- Include actor in API responses
- Use uploaded documents for extraction/data quality checks

This intentionally avoids treating consent as a blanket yes/no permission.

## 6. Data And Document Categories

Data categories:

- `identity_profile`
- `location`
- `crop_commodity`
- `export_profile`
- `certification_metadata`
- `operational_constraints`
- `contact_details`

Document categories:

- `public_compliance_document`
- `export_compliance_document`
- `company_registration_document`
- `identity_document`
- `financial_document`
- `transaction_document`
- `logistics_document`
- `other`

`models.py` maps seeded `DocumentType.category` values to these consent document categories for sharing checks.

## 7. Sharing Channels

Supported channels:

- `internal_review`
- `partner_portal`
- `admin_review`
- `licensed_data_pack`
- `live_intelligence`
- `subscriber_portal`
- `api`
- `approved_buyer_due_diligence`

Partner actor pages treat these as external sharing channels when deciding whether data/documents are currently externally shareable:

- `licensed_data_pack`
- `live_intelligence`
- `subscriber_portal`
- `api`
- `approved_buyer_due_diligence`

## 8. Helper Functions

New helper functions in `models.py`:

- `consent_record_is_active(consent_record, now=None)`
- `get_active_actor_consent(actor, now=None)`
- `actor_has_active_consent(actor)`
- `actor_can_share_data(actor, channel)`
- `actor_can_share_documents(actor, channel, document_category=None)`
- `consent_document_category_for_document_type(document_type)`

Rules:

- Consent must be `granted`.
- Consent must be `active`.
- Consent must not be withdrawn.
- Consent must not be expired.
- Consent must not have `review_status = rejected`.
- Data sharing requires an allowed channel and at least one permitted data category.
- Document sharing requires an allowed channel and at least one permitted document category.
- If a document category is supplied, the consent record must include that category.

These helpers are the future gate for publishing, subscriber access, API exposure, buyer due diligence, and document intelligence features.

## 9. Partner Workflow

Routes added to `routes/partner.py`:

| Route | Methods | Purpose |
| --- | --- | --- |
| `/partner/actors/<int:actor_id>/consent` | GET | Show active/latest consent and full consent history for a partner-owned actor. |
| `/partner/actors/<int:actor_id>/consent/new` | GET, POST | Create a new consent record for a partner-owned actor. |
| `/partner/actors/<int:actor_id>/consent/<int:consent_id>/withdraw` | POST | Withdraw an existing consent record and capture a reason. |

Access:

- All consent routes require login.
- All consent routes require an active partner profile.
- All consent routes enforce actor ownership by `partner_organization_id`.
- `partner_admin` and `data_editor` can create and withdraw consent.
- Other active partner roles can view consent history for their organization.
- Ordinary subscribers cannot access consent routes.

Templates added:

- `templates/partner/consent.html`
- `templates/partner/consent_form.html`

## 10. Actor Detail Integration

`templates/partner/actor_detail.html` now shows:

- Consent status badge
- Data shareable yes/no
- Documents shareable yes/no
- Consent method
- Granted by
- Granted at
- Expiry date
- Sharing channels
- Data categories
- Document categories
- Consent History action
- Record Consent or Update Consent action for editor roles

If no active consent exists, actor detail shows:

`No active consent is recorded. Actor data and documents should not be externally shared.`

## 11. Document Vault Integration

Document upload is still allowed without active consent. Partners may need to store documents internally before consent is fully captured.

However, when active consent is missing, `parse_document_form()` forces document `subscriber_access_level` and `visibility_level` to `hidden`. This prevents current document metadata from carrying a future subscriber-share flag without consent.

`templates/partner/document_detail.html` now shows:

- Warning when no active actor consent exists.
- Warning when active consent does not allow the document category for subscriber sharing.
- Consent category.
- Whether consent allows sharing.

Phase 3 private storage, upload, versioning, protected download, and access logging behavior are otherwise unchanged.

## 12. Audit Logging

`AuditLog` rows are written for:

- `consent_created`
- `consent_withdrawn`

`consent_updated` is documented for future use if an edit route is added. This phase records a new consent record for updates rather than mutating existing records through an edit screen.

Withdrawal records:

- set `consent_status = withdrawn`
- set `withdrawn_at`
- capture `withdrawal_reason`
- set `active = False`

## 13. Validation

New validation script:

```bash
python scripts/validate_phase_3_0_actor_consent.py
```

On the local Windows workspace used during implementation, validation should be run from the repo virtual environment:

```powershell
.venv\Scripts\python.exe scripts\validate_phase_3_0_actor_consent.py
```

The script covers:

- Actor detail renders consent status.
- Ordinary subscribers cannot access consent routes.
- Cross-organization partners cannot access consent routes.
- Partner editor can create granted consent.
- Active consent helper returns true for valid granted consent.
- Helpers return false for missing, refused, withdrawn, and expired consent.
- Consent history page renders.
- Consent withdrawal works and writes audit logs.
- Actor detail shows warning when no active consent exists.
- Document detail shows warning when no active consent exists.

Recommended full validation stack:

```bash
python scripts/validate_phase_1_data_foundation.py
python scripts/validate_phase_2_partner_portal.py
python scripts/validate_phase_2_1_reference_quality.py
python scripts/validate_phase_3_document_vault.py
python scripts/validate_phase_3_0_actor_consent.py
python -m compileall app.py models.py routes scripts
git diff --check
```

Expected SQLite validation warning: the existing Postgres-only `migrate_payment_plans_table()` helper prints a `DO $$` SQLite syntax warning during in-memory validation. This warning predates Phase 3.0 and is also noted in earlier validation docs.

## 14. Manual Replit Test Steps

After merging and pulling in Replit:

1. Start the existing Replit app flow.
2. Log in as a partner user with `partner_admin` or `data_editor`.
3. Open an actor detail page.
4. Confirm the Consent And Data Sharing panel shows Not Requested and the missing-consent warning.
5. Click Record Consent.
6. Save a granted consent record with a method, grantor, scopes, categories, and sharing channels.
7. Confirm actor detail shows Granted and shareability values.
8. Open Consent History and confirm the record appears.
9. Withdraw the consent with a reason.
10. Confirm the actor returns to non-shareable state.
11. Open a document detail page for the actor and confirm consent warnings reflect the current consent state.

## 15. Deferred Scope

Still deferred:

- Actor self-service portal.
- SMS/email consent capture.
- E-signature integration.
- Legal document generation.
- Legal/compliance review of consent wording and retention policy.
- Subscriber document access.
- Admin publishing workflow.
- API sharing enforcement beyond helper functions.
- External consent verification provider.
- Consent edit route; this phase records new consent rows and supports withdrawal.
- Consent-specific migration tooling beyond the existing startup `db.create_all()` pattern.

## 16. Safe Next Integration Approach

1. Reuse `actor_can_share_data()` and `actor_can_share_documents()` before any publishing, subscriber access, buyer access, API response, redaction, or extraction output leaves internal review.
2. Add admin review screens before accepting consent for external subscriber or buyer workflows.
3. Add actor-facing confirmation only after legal wording and identity verification are designed.
4. Keep payment/subscription changes isolated until a future issue explicitly scopes consent-dependent monetization.
