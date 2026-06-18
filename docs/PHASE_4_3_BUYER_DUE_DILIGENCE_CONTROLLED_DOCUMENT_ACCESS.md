# Phase 4.3 Buyer Due Diligence And Controlled Document Access

Branch: `feature/phase-4-3-buyer-due-diligence-controlled-document-access`

## Summary

Phase 4.3 adds a controlled buyer due diligence workflow on top of the Phase 3.4 document access request foundation.

It preserves the existing Flask/Replit app, public routes, authentication, subscriber/export behavior, payment flows, partner portal, document vault, consent controls, extraction/reconciliation, admin review, redaction controls, publish-readiness controls, API metadata gates, commercial operations workflow, subscriptions, licensed packs, and Replit configuration.

This phase does not expose document files. It adds admin decisioning and safe fulfilment records for restricted document access requests while keeping consent, entitlement, redaction, and publish-readiness gates authoritative.

## Data Model Additions

### `document_access_requests`

Existing table from Phase 3.4.

Phase 4.3 extends the supported status vocabulary with:

- `in_review`
- `needs_information`
- `approved_for_redacted_access`
- `closed`

Existing statuses remain supported:

- `pending`
- `approved`
- `rejected`
- `cancelled`

### `document_access_fulfilment_actions`

New lightweight table for durable fulfilment history.

Fields:

- `document_access_request_id`
- `action_type`
- `status`
- `visibility_level`
- `notes`
- `performed_by_user_id`
- `metadata_json`
- timestamps from `TimestampMixin`

Supported action types:

- `redacted_access_recorded`
- `restricted_full_document_review_recorded`
- `manual_note`

The table stores operational fulfilment history only. It does not store file paths, filenames, hashes, extracted text, document bytes, public links, or payment records.

## Admin Routes

| Route | Method | Purpose |
| --- | --- | --- |
| `/admin/due-diligence-requests` | GET | Admin-only due diligence request queue with status/type filters and counters. |
| `/admin/due-diligence-requests/<int:request_id>` | GET | Admin-only detail view for request context, safe document metadata, gate status, decision controls, fulfilment history, and audit history. |
| `/admin/due-diligence-requests/<int:request_id>/decision` | POST | Updates due diligence decision status and review notes. |
| `/admin/due-diligence-requests/<int:request_id>/fulfilment` | POST | Records a safe fulfilment action after approval gates pass. |

The existing `/admin/document-access-requests` capture-list route remains available and now links into the Phase 4.3 due diligence workflow.

## Subscriber Routes

| Route | Method | Purpose |
| --- | --- | --- |
| `/subscriber/document-access-requests` | GET | Subscriber request status list scoped to `current_user.id`. |
| `/subscriber/document-access-requests/<int:request_id>` | GET | Subscriber request detail scoped to `current_user.id`. |

Subscribers can only view their own document access requests. Another subscriber's request returns `404`.

Subscriber detail pages show request status and safe metadata only when the existing metadata gate currently allows it.

## Decision Workflow

Admin decisions can move a request to:

- `in_review`
- `needs_information`
- `approved_for_redacted_access`
- `rejected`
- `closed`
- `cancelled`

When an admin attempts `approved_for_redacted_access`, the app re-runs:

- subscriber metadata entitlement gate;
- actor consent gate;
- document publish-readiness gate for `subscriber_portal_metadata`;
- document publish-readiness gate for the requested access target;
- admin approval and verification checks;
- redaction gate;
- extraction/reconciliation and risk gates;
- expiry checks.

Approval is blocked if the current request no longer passes the existing governance gates.

## Visibility Separation

The admin detail page explicitly separates:

- `metadata_only`: subscriber metadata visibility through `subscriber_portal_metadata`;
- `redacted_document_candidate`: readiness for a future redacted document access flow;
- `full_document_restricted_candidate`: readiness for a future restricted full-document due diligence flow.

This phase records readiness and fulfilment decisions. It does not create a public download route, subscriber file view, redacted file delivery path, or full-document delivery path.

## Fulfilment Rules

Concrete fulfilment actions require:

- request status is `approved_for_redacted_access`;
- current metadata access gate passes;
- current requested publish target is `ready` or `waived`.

Rejected and cancelled requests are blocked from concrete fulfilment actions.

Fulfilment records:

- `DocumentAccessFulfilmentAction`;
- `AuditLog`;
- admin-channel `DocumentAccessLog`.

Fulfilment does not expose:

- storage paths;
- source files;
- original filenames;
- stored filenames;
- hashes;
- contact fields;
- raw extraction text;
- restricted document fields;
- download links.

## Audit Logging

New audit actions:

- `admin_due_diligence_request_status_updated`
- `admin_due_diligence_decision_blocked`
- `admin_due_diligence_fulfilment_recorded`
- `admin_due_diligence_fulfilment_blocked`

Audit entries record guardrail outcomes such as:

- `access_granted = false`
- `file_exposed = false`
- `download_created = false`
- `storage_path_exposed = false`
- `payment_flow_changed = false`

## Dashboard Integration

The admin dashboard now includes:

- active due diligence request count;
- link to `/admin/due-diligence-requests`.

Subscriber `My Access` now links to the document access request status list.

## Validation

Added:

```bash
python scripts/validate_phase_4_3_buyer_due_diligence.py
```

The validation covers:

- admin due diligence queue is admin-only;
- admin due diligence detail is admin-only;
- subscribers can see only their own document access requests;
- approval is blocked when consent/publish/entitlement readiness fails;
- rejected and cancelled requests cannot create fulfilment actions;
- restricted fields do not render on admin or subscriber due diligence pages;
- decisions persist and write audit logs;
- fulfilment actions write audit and access logs.

## Manual Replit Steps

After deployment, restart the Replit app so `db.create_all()` can create `document_access_fulfilment_actions`.

Recommended smoke checks:

1. Submit a restricted document access request as an entitled subscriber.
2. Visit `/subscriber/document-access-requests`.
3. Log in as admin and visit `/admin/due-diligence-requests`.
4. Open a request and confirm metadata-only, redacted candidate, and full restricted candidate sections are separate.
5. Attempt approval on a request whose gates are blocked and confirm approval is refused.
6. Approve a gate-passing request and record a fulfilment action.
7. Confirm no file path, filename, hash, raw extraction text, or download link appears.
