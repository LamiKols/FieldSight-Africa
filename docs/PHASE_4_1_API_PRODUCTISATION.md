# Phase 4.1 API Productisation And Developer Onboarding

Branch: `feature/phase-4-1-api-productisation-developer-onboarding`

Linear source of truth: FSA-22

## 1. Summary

Phase 4.1 packages FieldSight Africa's existing API-safe document metadata endpoint into a developer-facing product experience.

This phase adds:

- Subscriber API product/dashboard page.
- Subscriber API documentation/onboarding page.
- Subscriber API access request flow using the existing `CommercialRequest` pattern.
- Admin API dashboard.
- Validation coverage for API productisation safety rules.

This phase preserves Phase 1 through Phase 4.0 behavior, including existing payments, subscriber dataset/export flows, partner portal, document governance, commercial request capture, API key hashing/prefix behavior, and the Phase 3.4 metadata gate.

No new database table, payment flow, API endpoint, key creation workflow, or automatic API access grant was added.

## 2. Existing API Foundation Reused

Phase 4.1 reuses:

- `ApiClient`
- `ApiKey`
- `ApiUsageEvent`
- `DocumentAccessLog`
- `CommercialRequest`
- `/api/v1/document-metadata`
- `document_access.document_metadata_access_decision()`
- `document_access.safe_document_metadata_payload()`

The existing API key model remains authoritative:

- only `key_prefix` and `key_hash` are stored;
- raw API secrets are not stored;
- dashboards only show prefixes and operational metadata;
- raw secrets are not displayed by Phase 4.1.

## 3. Subscriber Routes

Routes added to the existing subscriber blueprint:

| Route | Methods | Purpose |
| --- | --- | --- |
| `/subscriber/api` | GET | API product landing page and subscriber API dashboard. |
| `/subscriber/api/docs` | GET | API onboarding documentation for `/api/v1/document-metadata`. |
| `/subscriber/api/request-access` | GET, POST | Captures an API access enquiry as a `CommercialRequest`. |

All subscriber API routes require login.

## 4. Subscriber API Dashboard

The subscriber API page shows:

- owned API clients;
- API client status;
- client scopes;
- API key prefixes;
- key status;
- key last-used timestamps;
- recent API usage events for the subscriber's own API clients;
- safe sample request;
- safe response field list;
- recent API access enquiries.

The dashboard is scoped to `ApiClient.owner_user_id == current_user.id`.

It does not show:

- another user's API clients;
- raw API secrets;
- key hashes;
- document files;
- private storage paths;
- original or stored filenames;
- file hashes;
- raw extraction text;
- actor names or contacts;
- partner-sensitive document notes.

## 5. API Documentation Page

The docs page describes the existing endpoint:

```text
GET /api/v1/document-metadata
```

Authentication:

```text
Authorization: Bearer <your_api_secret>
```

or:

```text
X-API-Key: <your_api_secret>
```

Required scope:

```text
document_metadata:read
```

Optional filters:

- `document_id`
- `document_type`
- `crop`
- `region`

## 6. Safe Metadata Fields

The docs describe the fields actually returned by `safe_document_metadata_payload()`:

- `document_id`
- `actor_public_id`
- `actor_type`
- `document_type`
- `document_type_code`
- `document_category`
- `reference_number`
- `issuing_body`
- `issued_at`
- `expires_at`
- `crop`
- `commodity`
- `region_code`
- `region_name`
- `verification_status`
- `review_status`
- `redaction_status`
- `publish_target`
- `publish_status`
- `metadata_only`

The docs and dashboards explicitly avoid unsafe fields such as private paths, filenames, file hashes, PII, raw extraction text, and partner-sensitive notes.

## 7. API Access Request Flow

Route:

```text
/subscriber/api/request-access
```

Submitting the form creates a `CommercialRequest` with:

- `request_type = "api_access"`
- `requested_product = "API Metadata Access"`
- `dataset_code = "document_metadata"`
- organization/contact/message fields;
- context JSON noting:
  - requested endpoint `/api/v1/document-metadata`;
  - requested scope `document_metadata:read`;
  - safe metadata fields;
  - `commercial_packaging_phase = "4.1"`;
  - `auto_client_created = false`;
  - `auto_access_granted = false`.

The existing subscriber audit helper writes:

```text
commercial_api_access_request_created
```

The audit payload continues to include:

- `auto_granted: false`
- `entitlement_changed: false`

The route does not create:

- an `ApiClient`;
- an `ApiKey`;
- an API scope;
- a subscription;
- a licence;
- Live Intelligence access;
- document metadata access.

## 8. Admin API Dashboard

Route:

```text
/admin/api-dashboard
```

The admin API dashboard is protected by `login_required` and `admin_required`.

It shows:

- API clients;
- key prefixes and key status;
- scopes;
- recent API usage events;
- blocked API metadata attempts from `DocumentAccessLog`;
- unauthorized API attempts from `AuditLog`;
- API access enquiries from `CommercialRequest`.

It does not show raw API secrets or key hashes.

## 9. Preserved Gates

Phase 4.1 does not change `/api/v1/document-metadata`.

The endpoint still requires:

- active API key;
- active API client;
- `document_metadata:read` scope on the key or client;
- linked owner user;
- Phase 3.4 document metadata gate pass;
- entitlement scope pass.

Phase 4.1 does not expose document files, private storage paths, filenames, file hashes, PII, raw extraction text, restricted fields, or partner-sensitive fields.

## 10. Validation

New validation script:

```bash
python scripts/validate_phase_4_1_api_productisation.py
```

The script validates:

- `/subscriber/api`, `/subscriber/api/docs`, and `/subscriber/api/request-access` require login.
- Subscriber API dashboard renders owned API clients.
- Subscriber API dashboard shows key prefixes but not raw secrets or key hashes.
- Subscriber API dashboard does not show another user's API client.
- API docs render the safe endpoint, authentication guidance, scope, and actual safe fields.
- API docs do not render unsafe field names.
- API access request creates a pending `CommercialRequest`.
- API access request writes an audit log.
- API access request does not create `ApiClient` or `ApiKey` rows.
- Admin API dashboard is admin-only.
- Admin API dashboard renders API clients, key prefixes, usage events, blocked attempts, and API enquiries.
- Admin API dashboard does not expose raw secrets, hashes, private paths, file hashes, or actor names.

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
python scripts/validate_phase_4_0_commercial_packaging.py
python scripts/validate_phase_4_1_api_productisation.py
python -m compileall app.py models.py routes scripts
git diff --check
```

Expected SQLite validation warning: the existing Postgres-only `migrate_payment_plans_table()` helper prints a `DO $$` SQLite syntax warning during in-memory validation. This warning predates Phase 4.1.

## 11. Manual Replit Steps

After merge:

1. Restart the Replit app.
2. Log in as a subscriber and visit `/subscriber/api`.
3. Visit `/subscriber/api/docs`.
4. Submit an API enquiry at `/subscriber/api/request-access`.
5. Log in as an admin and visit `/admin/api-dashboard`.
6. Confirm key prefixes, usage, blocked attempts, and API access enquiries render without raw secrets or restricted document fields.

No new environment variables or Replit configuration changes are required.

## 12. Deferred Scope

Deferred to future phases:

- API client creation UI.
- API key creation/rotation UI.
- Showing raw API secret once at creation.
- API usage quotas and rate limiting.
- API billing.
- API client approval workflow.
- Sandbox API environment.
- Developer portal accounts separate from subscribers.
- Webhooks or SDKs.
