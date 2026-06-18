# Phase 4.0 Commercial Product Packaging

Branch: `feature/phase-4-0-commercial-product-packaging`

Linear source of truth: FSA-21

## 1. Summary

Phase 4.0 packages FieldSight Africa's existing entitlement and governance foundation into subscriber-facing commercial product surfaces.

This phase adds:

- Subscriber `My Access` page.
- Subscriber product catalogue for Core Regional, Expanded Regional, National, and Live Market Intelligence.
- Gated commercial CTAs for unavailable datasets, regions, crops, API metadata, restricted document access, and upgrade enquiries.
- Durable commercial request capture for Live Intelligence, API access, and upgrade enquiries.
- Admin commercial dashboard.
- Audit logging for commercial request capture.

This phase preserves the existing public routes, authentication, subscriber datasets and exports, admin dataset upload/publish workflow, Stripe/Paystack flows, partner portal, Phase 3 document governance, API metadata gate, subscriptions, licensed packs, and Replit configuration.

## 2. Model Added

### `CommercialRequest`

Table: `commercial_requests`

Purpose: captures commercial enquiries without granting access automatically.

Fields:

- `user_id`
- `request_type`
- `organization_name`
- `contact_name`
- `contact_email`
- `requested_product`
- `dataset_code`
- `region_code`
- `crop_name`
- `message`
- `context_json`
- `status`
- `reviewed_by_user_id`
- `reviewed_at`
- `review_notes`
- timestamps from `TimestampMixin`

Supported request types:

- `live_intelligence`
- `api_access`
- `upgrade`

Supported statuses:

- `pending`
- `in_review`
- `contacted`
- `closed`
- `cancelled`

No subscription, licence, API client, Live Intelligence grant, document entitlement, document access request, publish control, or payment record is created by this model.

## 3. Subscriber Routes

Routes added to the existing subscriber blueprint:

| Route | Methods | Purpose |
| --- | --- | --- |
| `/subscriber/my-access` | GET | Shows the signed-in subscriber's current subscriptions, licensed packs, live intelligence grants, API clients, document entitlements, document metadata access count, recent document access requests, and recent commercial requests. |
| `/subscriber/products` | GET | Shows Core Regional, Expanded Regional, National, and Live Market Intelligence products with non-granting CTAs. |
| `/subscriber/commercial-request/new` | GET, POST | Captures Live Intelligence, API access, or upgrade enquiries as `CommercialRequest` rows. |

The existing `/live-intelligence/request` route now also creates a durable `CommercialRequest` row for Live Intelligence enquiries while preserving its existing redirect/flash behavior.

## 4. My Access Behavior

`My Access` uses existing entitlement sources only:

- `get_user_entitlements(current_user)`
- active `Subscription`
- `License`
- `LiveIntelligenceAccess`
- owned `ApiClient`
- user-level `DocumentEntitlement`
- Phase 3.4 `document_metadata_access_decision()`
- `DocumentAccessRequest`
- `CommercialRequest`

The page is scoped to the current user. It does not show another user's API clients, commercial requests, licences, subscriptions, or access requests.

Document metadata visibility is summarized using the Phase 3.4 gate. The page does not expose private document files, private paths, filenames, actor contact details, raw extraction output, or restricted document links.

## 5. Product Catalogue

The new product catalogue covers:

- Core Regional
- Expanded Regional
- National
- Live Market Intelligence

Licensed pack product cards read from existing `LicensedPack` rows when available. The catalogue links to the existing packs/payment route for pack checkout and to commercial request capture for fit/upgrade enquiries.

Live Market Intelligence is presented as a custom commercial product and routes to commercial request capture.

Product pages explain access. They do not grant access automatically.

## 6. Gated CTAs

Gated CTAs now exist for:

- unavailable datasets;
- unavailable regions;
- unavailable crops;
- API metadata access;
- restricted document access;
- general upgrade enquiries.

Dataset, region, crop, API, Live Intelligence, and upgrade CTAs create `CommercialRequest` rows when submitted. Restricted document CTAs continue to use the Phase 3.4 `DocumentAccessRequest` flow and still require metadata visibility before a request can be captured.

Commercial request submission records:

- request type;
- organization/contact details;
- requested product;
- optional dataset, region, and crop context;
- request message;
- context JSON including the source/referrer and current entitlement type.

Commercial request submission does not update payment, subscription, licence, live intelligence, API, or document gate state.

## 7. Admin Commercial Dashboard

Route added to the existing admin blueprint:

| Route | Methods | Purpose |
| --- | --- | --- |
| `/admin/commercial-dashboard` | GET | Shows commercial package readiness and demand context for admins. |

The dashboard is protected by the existing `login_required` and `admin_required` decorators.

It shows:

- active licensed pack products;
- active subscriptions;
- recent licences;
- Live Intelligence grants;
- API clients;
- document access requests;
- commercial requests;
- recent commercial audit events;
- recent blocked document metadata access events.

The existing admin dashboard now links to this page and shows a pending commercial request count.

## 8. Audit Logging

Commercial request capture writes `AuditLog` rows with:

- `commercial_live_intelligence_request_created`
- `commercial_api_access_request_created`
- `commercial_upgrade_request_created`

Audit payloads explicitly include:

- `auto_granted: false`
- `entitlement_changed: false`

This makes the non-fulfilment boundary visible to future reviewers.

## 9. Preserved Access And Governance Boundaries

Phase 4.0 does not:

- change Stripe or Paystack flows;
- create subscriptions;
- create licences;
- create API clients;
- grant Live Intelligence access;
- grant document metadata access;
- grant restricted document access;
- expose document files, paths, filenames, hashes, raw extraction text, actor names, contact data, or PII;
- bypass Phase 3.4 metadata gates;
- change partner or admin document review behavior.

The Phase 3.4 gate remains authoritative for subscriber/API document metadata visibility.

## 10. Validation

New validation script:

```bash
python scripts/validate_phase_4_0_commercial_packaging.py
```

The script validates:

- `My Access` requires login.
- Subscriber can see their own access state.
- `My Access` does not show another user's API client or email.
- Product catalogue renders Core Regional, Expanded Regional, National, and Live Market Intelligence.
- Product catalogue explains non-granting CTAs.
- Upgrade, API access, and Live Intelligence commercial requests are captured durably.
- Audit logs are written for each request type.
- Request audit payloads mark access as not auto-granted.
- Commercial CTAs do not create subscriptions, licences, Live Intelligence grants, or API clients.
- Admin commercial dashboard is admin-only.
- Admin commercial dashboard renders requests, API clients, and recent audit events for admins.

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
python -m compileall app.py models.py routes scripts
git diff --check
```

Expected SQLite validation warning: the existing Postgres-only `migrate_payment_plans_table()` helper prints a `DO $$` SQLite syntax warning during in-memory validation. This warning predates Phase 4.0.

## 11. Manual Replit Steps

After merge:

1. Restart the Replit app so `db.create_all()` can create `commercial_requests`.
2. Log in as a subscriber and visit `/subscriber/my-access`.
3. Visit `/subscriber/products` and confirm the four product tiers render.
4. Submit Live Intelligence, API access, and upgrade enquiries through `/subscriber/commercial-request/new`.
5. Log in as an admin and visit `/admin/commercial-dashboard`.
6. Confirm commercial requests and audit events appear.

No new environment variables or Replit configuration changes are required.

## 12. Deferred Scope

Deferred to future phases:

- commercial request review/fulfilment workflow;
- sales notifications;
- CRM integration;
- API client provisioning from an approved request;
- paid document access;
- restricted document request approval;
- automatic licence creation from commercial request;
- product-specific checkout redesign;
- billing portal changes.
