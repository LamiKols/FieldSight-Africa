# Phase 4.2 Commercial Operations And Request Fulfilment

Branch: `feature/phase-4-2-commercial-operations-fulfilment`

Linear issue: FSA-23

## Summary

Phase 4.2 adds an operations workflow around the commercial requests captured in Phase 4.0 and Phase 4.1.

The implementation preserves the existing Flask/Replit app, public routes, payment flows, subscriptions, licensed packs, partner/document governance, API metadata gates, and commercial request capture behavior.

This phase does not grant access on request submission. It gives admins a controlled queue, decision workflow, fulfilment action history, and explicit safe fulfilment helpers.

## Data Model Additions

### `commercial_requests`

Existing table from Phase 4.0.

Phase 4.2 extends the allowed status vocabulary with:

- `approved_for_fulfilment`
- `rejected`

Existing statuses remain:

- `pending`
- `in_review`
- `contacted`
- `closed`
- `cancelled`

### `commercial_fulfilment_actions`

New lightweight table for durable admin fulfilment history.

Fields:

- `commercial_request_id`
- `action_type`
- `status`
- `notes`
- `performed_by_user_id`
- `resulting_api_client_id`
- `resulting_live_intelligence_access_id`
- `metadata_json`
- timestamps from `TimestampMixin`

Supported action types:

- `api_client_setup`
- `live_intelligence_access`
- `upgrade_followup`
- `manual_note`

## Admin Workflow

### Routes

| Route | Method | Purpose |
| --- | --- | --- |
| `/admin/commercial-requests` | GET | Admin-only queue with status/type filters and counters. |
| `/admin/commercial-requests/<int:request_id>` | GET | Admin-only request detail with context, related API clients, Live Intelligence access, decisions, and fulfilment history. |
| `/admin/commercial-requests/<int:request_id>/decision` | POST | Updates commercial review status and notes. |
| `/admin/commercial-requests/<int:request_id>/fulfilment` | POST | Records explicit fulfilment actions with guardrails. |

### Decision Rules

Admin decisions can move a request to:

- `in_review`
- `contacted`
- `approved_for_fulfilment`
- `rejected`
- `closed`
- `cancelled`

Decision updates persist:

- `status`
- `review_notes`
- `reviewed_by_user_id`
- `reviewed_at`

Every decision writes an `AuditLog` action:

- `admin_commercial_request_status_updated`

Decision updates do not create API clients, API keys, subscriptions, licences, payments, document access, or Live Intelligence access.

## Controlled Fulfilment Helpers

Concrete fulfilment actions are blocked unless the commercial request is already `approved_for_fulfilment`.

Blocked attempts write:

- `admin_commercial_request_fulfilment_blocked`

Successful fulfilment actions write:

- `admin_commercial_request_fulfilment_recorded`

### API Access Fulfilment

`api_client_setup` is only valid for `api_access` requests.

It creates or reuses a pending `ApiClient` setup record linked to the requesting subscriber.

It does not:

- create an `ApiKey`;
- expose a raw API secret;
- expose an API key hash;
- grant API metadata access automatically.

### Live Intelligence Fulfilment

`live_intelligence_access` is only valid for `live_intelligence` requests.

It requires explicit admin-provided:

- start date;
- end date;
- at least one region;
- optional crop list.

It creates or updates `LiveIntelligenceAccess` only when the admin submits this fulfilment action on an approved request.

### Upgrade Fulfilment

`upgrade_followup` is only valid for `upgrade` requests.

It records status/notes and a fulfilment action only.

It does not:

- change Stripe;
- change Paystack;
- create a `Payment`;
- create a `Subscription`;
- create a `License`;
- bypass any existing payment or entitlement workflow.

## Subscriber Workflow

### Routes

| Route | Method | Purpose |
| --- | --- | --- |
| `/subscriber/commercial-requests` | GET | Subscriber request status list scoped to `current_user.id`. |
| `/subscriber/commercial-requests/<int:request_id>` | GET | Subscriber request detail scoped to `current_user.id`. |

Subscribers can see only their own commercial requests. Another subscriber's request returns `404`.

Subscriber detail pages show safe request status and fulfilment updates. They do not show API secrets, API key hashes, private document paths, document files, raw extraction text, file hashes, or restricted document fields.

## Dashboard Integration

The admin dashboard now includes:

- pending commercial request count;
- approved-for-fulfilment count;
- direct link to the commercial request queue.

The existing commercial dashboard now links to the operations queue and each request detail page.

`My Access` and the subscriber API dashboard link to subscriber commercial request status pages.

## Audit Logging

Commercial request operations use the existing `AuditLog` table.

Actions added:

- `admin_commercial_request_status_updated`
- `admin_commercial_request_fulfilment_recorded`
- `admin_commercial_request_fulfilment_blocked`

Audit entries record guardrail outcomes such as:

- `api_key_created = false`
- `api_secret_exposed = false`
- `api_key_hash_exposed = false`
- `payment_flow_changed = false`
- `auto_granted_on_submission = false`

## Boundaries Preserved

This phase does not:

- grant access on request submission;
- expose raw API secrets or API key hashes;
- create API keys;
- expose private document paths, files, file hashes, raw extraction text, or restricted document fields;
- bypass consent, publish-readiness, document metadata, entitlement, or payment gates;
- replace Stripe or Paystack flows;
- automatically create subscriptions or licences from upgrade requests.

## Validation

Added:

```bash
python scripts/validate_phase_4_2_commercial_operations.py
```

The validation covers:

- admin commercial request queue is admin-only;
- admin commercial request detail is admin-only;
- subscribers can see only their own commercial requests;
- admin decisions persist and write audit logs;
- fulfilment actions write audit logs;
- API fulfilment creates a setup record without secrets, key hashes, or API keys;
- Live Intelligence access is created only after explicit admin fulfilment;
- upgrade fulfilment does not alter payment, subscription, or licence records;
- rejected and cancelled requests do not create access records.

## Manual Replit Steps

After deployment, restart the Replit app so `db.create_all()` can create the new `commercial_fulfilment_actions` table.

Recommended smoke checks:

1. Log in as a subscriber and submit upgrade, API access, and Live Intelligence requests.
2. Visit `/subscriber/commercial-requests`.
3. Log in as an admin and visit `/admin/commercial-requests`.
4. Move one request to `approved_for_fulfilment`.
5. Record an API setup fulfilment and confirm no API key is created.
6. Record a Live Intelligence fulfilment and confirm access is created only after the explicit action.
7. Record an upgrade follow-up and confirm Stripe/Paystack/payment records are unchanged.
