# Partner Onboarding Demo Polish

## Purpose

This release polishes the existing Partner Data Owner Onboarding feature for commercial walkthroughs. It does not redesign the platform or introduce a new architecture. The goal is to make the existing partner onboarding, bulk registry import, preview, error CSV, submission, admin review, actor invitation, and subscriber trusted-data story easier to demonstrate.

FieldSight Africa should be presented as ongoing subscription access to a continuously maintained and governed agricultural actor registry, not a one-time dataset upload.

## Demo Personas

- Admin: reviews partner organizations, submitted registry imports, validation summaries, and governance readiness.
- Partner data owner: contributes structured farmer, exporter, aggregator, and cooperative records through single actor entry or bulk spreadsheet import.
- Actor, farmer, exporter, or aggregator: receives an update invitation concept so they can later confirm or update their record before review.
- Buyer or subscriber: sees trusted, confidence-scored, subscription-ready data surfaces without restricted direct-contact fields.

## Step-By-Step Walkthrough

1. Start as an admin at `/admin/dashboard`.
2. Open `/admin/partner-organizations` to show data owner organizations maintaining the Live Actor Registry.
3. Open `/admin/partner-imports` to show pending, successful, and validation-error import scenarios.
4. Switch to the partner persona at `/partner/`.
5. Open `/partner/onboarding` to explain the data owner workflow.
6. Open `/partner/imports` to show bulk registry import batches.
7. Open `/partner/imports/new` to explain spreadsheet upload, preview, and restricted contact handling.
8. Open an import preview/detail page to show valid rows, warnings, rejected rows, duplicate/update candidates, and error CSV availability.
9. Submit a draft import to show that rows move into admin review without publishing subscriber data.
10. Open `/partner/actor-update-invitations` to explain actor-confirmed update foundations.
11. Switch to the buyer/subscriber persona at `/subscriber/product-tour`.
12. Open `/subscriber/document-metadata` or `/subscriber/intelligence-digests` to show safe trusted-data surfaces governed by consent, review, redaction, publish-readiness, entitlement, and API safety gates.

## Important Routes And Screens

- `/partner/`: partner dashboard with demo journey links.
- `/partner/onboarding`: partner data owner onboarding overview.
- `/partner/imports`: partner import batch list.
- `/partner/imports/new`: bulk spreadsheet upload form.
- `/partner/imports/<id>`: import detail and status page.
- `/partner/imports/<id>/preview`: row-level import validation preview.
- `/partner/imports/<id>/submit`: POST-only valid-row submission action.
- `/partner/imports/<id>/errors.csv`: safe correction CSV for validation errors.
- `/partner/actor-update-invitations`: actor-confirmed update invitation foundation.
- `/admin/partner-imports`: admin import queue.
- `/admin/partner-imports/<id>`: admin import detail and review scenario.
- `/admin/partner-organizations`: admin data owner organization list.
- `/admin/partner-organizations/<id>`: admin organization detail.
- `/subscriber/product-tour`: buyer/subscriber product tour.
- `/subscriber/document-metadata`: verified document metadata visibility under existing gates.

## Demo Data Included

The local/demo seed remains deterministic and synthetic. It includes:

- Partner organization examples such as Kano Grain Cooperative, Oyo Cassava Aggregators Network, and Benue Soybean Producers Association.
- Existing demo partner: Demo Sahel Produce Network.
- A pending import: Demo Pending Kano Grain Registry Import.
- A successful/admin-reviewed import: Demo Successful Oyo Cassava Registry Import.
- A validation-error import: Demo Error Benue Soybean Registry Import.
- The existing mixed import: Demo Monthly Live Actor Registry Import.
- Several actor records with different statuses, including Demo Sahel Ginger Exporter, Kaduna Maize Export Cluster, Ogun Cocoa Aggregation Hub, and Oyo Cassava Aggregators Network.
- One safe actor update invitation scenario stored as actor metadata, not as contact data.
- One admin review scenario on the successful import.

All demo records are fictional. The seed does not add real phone numbers, real personal emails, source files, private storage paths, stored filenames, file hashes, API secrets, key hashes, raw extraction text, or restricted document fields. Demo import contact hints remain restricted and are not rendered to public, subscriber, or buyer surfaces.

## Validation Commands

Run:

```bash
python scripts/validate_all_phases.py
python scripts/validate_partner_data_owner_onboarding.py
python scripts/validate_partner_onboarding_demo_polish.py
python scripts/validate_commercial_demo_launch_readiness.py
python -m compileall app.py models.py routes scripts intelligence_insights.py intelligence_sources.py intelligence_engine.py
git diff --check
```

On this local Windows workspace, use `.\.venv\Scripts\python.exe` if the default `python` executable does not have the project dependencies installed.

## Known SQLite Warning

The existing validation suite may print a non-fatal SQLite migration warning about PostgreSQL `DO $$` syntax while using in-memory SQLite. The central validation runner preserves that known warning. The warning is acceptable when the validation scripts still exit successfully.

## Safety Boundaries

- No payment flows are changed.
- No paid entitlements are granted by seed data.
- No subscriber, API, buyer, or public document access is created automatically.
- Restricted contact handling remains protected.
- Consent, review, redaction, publish-readiness, entitlement, audit, and API safety gates remain authoritative.
- The demo seed is local/demo oriented and should not be treated as production data.
