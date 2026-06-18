# Phase 4.4 Commercial Reporting And Revenue Intelligence

Branch: `feature/phase-4-4-commercial-reporting-revenue-intelligence`

## Summary

Phase 4.4 adds admin-only commercial reporting on top of the existing Phase 4 commercial packaging, API productisation, commercial operations, and buyer due diligence workflows.

It preserves the existing Flask/Replit app, public routes, authentication, subscriber/export behavior, payment flows, partner portal, document vault, consent controls, extraction/reconciliation, admin document review, redaction controls, publish-readiness controls, API metadata gates, commercial request fulfilment, due diligence request handling, subscriptions, licensed packs, and Replit configuration.

This phase is reporting-only. It does not grant access, expose documents, create billing flows, modify Stripe or Paystack behavior, or bypass any consent, entitlement, redaction, publish-readiness, or document metadata gate.

## Admin Routes

| Route | Method | Purpose |
| --- | --- | --- |
| `/admin/commercial-reports` | GET | Admin-only dashboard for pipeline, funnel, revenue readiness, and follow-up intelligence. |
| `/admin/commercial-reports/pipeline.csv` | GET | Admin-only CSV export of aggregate commercial pipeline metrics. |

Both routes use the existing `login_required` and `admin_required` guards.

## Reporting Inputs

The report reads existing records only:

- `CommercialRequest` for upgrade, API access, and Live Intelligence enquiries.
- `DocumentAccessRequest` for due diligence and controlled document access demand.
- `Subscription` for active subscription readiness.
- `License` and `LicensedPack` for pack activity and licensed value signals.
- `ApiClient` for active API client readiness.
- `LiveIntelligenceAccess` for active Live Intelligence access.
- `CommercialFulfilmentAction` for fulfilment/conversion signals.

No new database tables or payment provider integrations are added in this phase.

## Dashboard Sections

### Pipeline Summary

The dashboard summarizes:

- commercial requests;
- due diligence requests;
- API enquiries;
- Live Intelligence requests;
- upgrade requests;
- active licences;
- active subscriptions;
- data pack activity.

### Request Funnel Analytics

Funnel breakdowns include:

- commercial request status;
- commercial request type;
- requested product;
- requested region;
- requested crop;
- request creation date;
- due diligence request status;
- due diligence request type;
- due diligence request creation date.

### Revenue Readiness

Revenue readiness metrics include:

- active licensed pack count;
- licensed pack catalogue value;
- active subscription count;
- active licence count;
- active licence value;
- commercial requests ready for conversion;
- fulfilled commercial request count;
- fulfilment rate;
- active API clients;
- active Live Intelligence access grants;
- subscriptions by plan;
- licences by pack.

These are readiness and operational signals only. They do not calculate recognized revenue and do not alter any payment flow.

### Follow-Up Queue

The dashboard shows admin follow-up queues for:

- open commercial requests;
- open due diligence requests;
- open API enquiries;
- open Live Intelligence enquiries.

Follow-up items link to the existing admin detail workflows. They show request IDs, status, safe request scope, and age. They do not expose document files, storage paths, hashes, raw extraction text, API secrets, API key hashes, or restricted document fields.

## Date Window Filters

Supported query windows:

- `7d`: last 7 days;
- `30d`: last 30 days;
- `90d`: last 90 days;
- `all`: all time.

Unsupported or empty values fall back to `30d`.

## CSV Export

`/admin/commercial-reports/pipeline.csv` exports aggregate rows with:

- `section`;
- `metric`;
- `segment`;
- `count`;
- `detail`;
- `window`.

The CSV is intentionally aggregate-only. It excludes request-level contact details, personal names, emails, API secrets, API key hashes, private file paths, filenames, document hashes, raw extraction text, and restricted document fields.

## Admin Dashboard Integration

The admin dashboard now includes:

- a `Commercial Reports` navigation card;
- a follow-up counter that combines pending commercial requests and active due diligence requests.

The existing commercial dashboard links to the reporting dashboard.

## Audit-Safe Boundaries

Phase 4.4 does not expose:

- API secrets;
- API key hashes;
- private storage paths;
- document files;
- source filenames;
- personal contact data;
- raw extraction text;
- file hashes;
- restricted document metadata;
- payment provider internals.

The report does not call document metadata access helpers because it does not expose subscriber-facing document metadata. Existing Phase 3.4 and Phase 4.3 gates remain authoritative for any future external metadata or document access.

## Validation

Added:

```bash
python scripts/validate_phase_4_4_commercial_reporting.py
```

The validation covers:

- commercial reporting dashboard is admin-only;
- CSV export is admin-only;
- dashboard renders request funnel metrics;
- dashboard renders revenue readiness metrics;
- dashboard renders follow-up queues;
- all supported date windows render;
- recent requests appear in filtered reports;
- older requests are excluded from 30-day reports and included in all-time reports;
- CSV export excludes restricted fields and secrets;
- admin dashboard includes commercial reporting navigation and follow-up counters.

## Manual Replit Steps

No schema migration is required for Phase 4.4 because no new tables or columns are added.

After deployment, restart the Replit app so the new admin routes and templates are loaded.

Recommended smoke checks:

1. Log in as an admin.
2. Visit `/admin/commercial-reports`.
3. Switch between last 7 days, last 30 days, last 90 days, and all time.
4. Download `/admin/commercial-reports/pipeline.csv`.
5. Confirm the report shows aggregate commercial signals only and does not show contact emails, API secrets, key hashes, private document paths, filenames, or document hashes.
