# Commercial Demo And Launch Readiness

Branch: `feature/commercial-demo-launch-readiness`

## Purpose

This release makes the existing FieldSight Africa platform easier to demonstrate to buyers, partners, investors, and internal reviewers. It adds safe synthetic demo data support, admin demo/readiness pages, clearer platform navigation, a subscriber product tour, validation, and documentation.

The release does not change payment flows, entitlements, document access gates, API safety rules, consent rules, publish-readiness controls, redaction controls, or automation processing behaviour.

## Added Demo Data Support

Added:

```bash
python scripts/seed_demo_data.py --confirm-demo-seed
```

The seed script is explicitly local/demo oriented and requires the `--confirm-demo-seed` flag when run directly. It creates deterministic synthetic records for:

- intelligence sources;
- ingestion runs;
- change events and internal alerts;
- publication candidates;
- subscriber intelligence digests;
- commercial requests;
- document access requests;
- actor registry sample records;
- metadata-only document readiness examples.

The script is idempotent. Running it again updates or reuses the same demo records instead of creating duplicate actors, documents, or request scaffolding.

## Safety Boundaries

Demo data is synthetic and intentionally avoids sensitive material:

- no real contact details;
- no original files;
- no document versions;
- no private storage paths;
- no original or stored filenames;
- no file hashes;
- no raw extraction text;
- no API keys or key hashes;
- no subscriptions, licences, live intelligence grants, document entitlements, API clients, or API keys;
- no fulfilment records that would imply access has been granted.

The seed creates metadata-only document records and controlled request examples so the governed workflow can be shown without exposing document files or bypassing gates.

## Added Admin Routes

- `/admin/demo-walkthrough`: admin-only walkthrough path for demonstrating the platform operating model.
- `/admin/commercial-readiness`: admin-only readiness dashboard for commercial launch indicators.
- `/admin/actors`: admin-only read-only actor registry overview that excludes contact fields and document internals.

All routes use the existing `admin_required` guard.

## Added Subscriber Route

- `/subscriber/product-tour`: logged-in subscriber product tour covering My Access, Products, API Docs, Document Requests, Intelligence Digests, and safe request paths.

The route uses existing subscriber authentication and does not grant access or alter entitlements.

## Navigation Improvements

Admin dashboard navigation now exposes the full operating model:

- actors;
- documents;
- document review;
- commercial requests;
- buyer due diligence;
- API products;
- automation;
- intelligence sources;
- intelligence alerts;
- publication candidates;
- reports.

Subscriber navigation now makes the buyer-facing flow easier to find:

- My Access;
- Products;
- API;
- API docs from the product tour;
- Document Metadata;
- Document Requests from the product tour;
- Intelligence Digests;
- Product Tour.

## Commercial Readiness Indicators

The admin readiness page summarizes:

- active intelligence sources;
- recent ingestion runs;
- open intelligence alerts;
- approved digests;
- commercial requests;
- document access requests;
- API access requests;
- pending document review;
- automation queue health.

The page renders safe operational counts and queue summaries only. It does not render private paths, filenames, hashes, raw extraction text, contact fields, API secrets, key hashes, or restricted document details.

## Validation

Added:

```bash
python scripts/validate_commercial_demo_launch_readiness.py
```

Updated:

```bash
python scripts/validate_all_phases.py
```

Validation covers:

- demo seed idempotency;
- absence of file paths, filenames, hashes, API keys, subscriptions, licences, live access, document entitlements, API clients, and fulfilment grants;
- admin-only protection for `/admin/demo-walkthrough`, `/admin/commercial-readiness`, and `/admin/actors`;
- logged-in subscriber protection for `/subscriber/product-tour`;
- safe rendering of readiness, walkthrough, actor overview, admin dashboard, and subscriber tour surfaces;
- presence of the operating model and readiness indicators.

Run before completion:

```bash
python scripts/validate_all_phases.py
python scripts/validate_commercial_demo_launch_readiness.py
python -m compileall app.py models.py routes scripts intelligence_insights.py intelligence_sources.py intelligence_engine.py
git diff --check
```

## Demo Walkthrough

Recommended local demo flow:

1. Run `python scripts/seed_demo_data.py --confirm-demo-seed` against a local/demo database.
2. Log in as the seeded admin user.
3. Open `/admin/demo-walkthrough`.
4. Review `/admin/commercial-readiness`.
5. Show intelligence sources, alerts, publication candidates, commercial requests, due diligence requests, and actor registry.
6. Log in as the seeded subscriber user.
7. Open `/subscriber/product-tour`, then My Access, Products, API Docs, Document Requests, and Intelligence Digests.

Seeded demo credentials are for local/demo use only:

- admin email: `demo.admin@fieldsight-demo.invalid`
- subscriber email: `demo.subscriber@fieldsight-demo.invalid`

Use the local seed script and repository code for local-only credential setup; do not reuse demo credentials in production.
