# Partner Data Owner Onboarding

Branch: `feature/partner-data-owner-onboarding`

## Purpose

This release makes the partner/data owner journey clear and demo-ready. FieldSight Africa is positioned as a continuously maintained agricultural intelligence network, not a one-off spreadsheet sale.

The operating model is:

```text
Partner/data owner maintains the registry -> actors may later confirm or update their records -> admin reviews data quality and governance -> subscribers access approved current intelligence through subscription
```

## Partner Demo Flow

1. Admin creates or activates a partner organization and owner/editor user.
2. Partner logs into the partner portal.
3. Partner dashboard explains the Live Actor Registry and Continuous Data Updates.
4. Partner adds one actor through `/partner/actors/new`.
5. Partner uploads a CSV/XLSX spreadsheet through `/partner/imports/new`.
6. Partner previews rows at `/partner/imports/<id>/preview`.
7. Partner fixes rejected rows using messages and `/partner/imports/<id>/errors.csv`.
8. Partner submits valid rows through `/partner/imports/<id>/submit`.
9. Admin reviews batch context through `/admin/partner-imports` and `/admin/partner-imports/<id>`.
10. Approved actor records support governed Subscription Access and Subscriber-Safe Intelligence after review gates.
11. Future actor self-updates can use invite-based confirmation and remain review-gated.

## Partner Dashboard

The partner dashboard now highlights:

- Add Single Actor;
- Bulk Upload Spreadsheet;
- View Import Batches;
- Fix Corrections;
- Submit Data For Review;
- View Approved Actors;
- Data Freshness and Last Updated;
- Last Verified Date;
- monthly or periodic Update Cycle;
- Partner-Maintained Records;
- Actor-Confirmed Records;
- Admin-Reviewed Records;
- Subscriber-Safe Intelligence.

## Partner Onboarding Page

Added:

- `/partner/onboarding`

The page explains:

- what the partner/data owner can update;
- single actor entry;
- bulk upload;
- validation and corrections;
- monthly or periodic refresh;
- admin review;
- subscriber-safe gating;
- future invite-based actor self-updates.

## Single Actor Registration

The existing `/partner/actors/new` route remains the single actor entry point and now clearly supports:

- actor/exporter/farmer/aggregator name;
- commodity category;
- location, state, and LGA;
- registration status;
- date of registration;
- years in trade;
- trade destination;
- export capacity;
- certification;
- port of exit;
- constraints;
- Data Freshness Date;
- Last Verified Date;
- Source of Update;
- Update Cycle;
- Partner Notes;
- restricted contact fields.

Freshness and verification metadata are stored in `MarketActor.metadata_json` to avoid a schema migration.

## Bulk Upload Workflow

Added partner routes:

- `/partner/imports`
- `/partner/imports/new`
- `/partner/imports/<id>`
- `/partner/imports/<id>/preview`
- `/partner/imports/<id>/submit`
- `/partner/imports/<id>/errors.csv`

The import foundation uses existing `PartnerUpdateBatch` and `PartnerRecordChange` records:

- `PartnerUpdateBatch` represents the import batch.
- `PartnerRecordChange` rows with `entity_type = actor_registry_import_row` represent sanitized row previews, warnings, corrections, duplicates, and proposed actions.
- Create rows generate pending-review `MarketActor` records immediately so contact values can be written only to restricted `ActorContact` records.
- Update candidate rows do not overwrite existing actors.
- Duplicate warning rows do not create or overwrite actors.
- Invalid rows remain correction rows and are excluded from submitted valid rows.

No uploaded spreadsheet path, private path, raw file, hash, or raw extraction text is stored or rendered.

## Template Column Mapping

The import parser supports the existing exporter database template:

- `COMMODITY CATEGORY` -> commodity/category
- `FARMER/AGGREAGATOR` -> actor name
- `LOCATION` -> location text
- `STATE` -> state reference or text
- `PHONE` -> restricted contact phone
- `EMAIL` -> restricted contact email
- `LGA` -> LGA reference or text
- `REGISTRATION STATUS` -> registration status
- `DATE OF REGISTRATION` -> registration date
- `NUMBER OF YEARS IN EXPORT TRADE` -> years in export trade
- `TRADE DESTINATION` -> trade destination text
- `EXPORT CAPACITY` -> export capacity text
- `ERTIFICATION` -> certification
- `PORT OF EXIT` -> port of exit
- `CONSTRAINT` -> constraint text

Spelling variants are handled:

- `FARMER/AGGREAGATOR` and `FARMER/AGGREGATOR` both map to actor name.
- `ERTIFICATION` and `CERTIFICATION` both map to certification.

## Row Validation

Validation checks:

- actor name exists;
- commodity/category can be mapped or safely stored as partner text with a warning;
- state and LGA can be matched or safely captured as text;
- export capacity is retained as text;
- dates are parsed safely;
- contact values are only persisted in restricted contact rows;
- likely duplicates and update candidates are flagged;
- uploaded paths are never exposed.

Rows are marked as:

- `create`;
- `update_candidate`;
- `duplicate_warning`;
- `invalid`.

## Admin Visibility

Added admin routes:

- `/admin/partner-imports`
- `/admin/partner-imports/<id>`
- `/admin/partner-organizations`
- `/admin/partner-organizations/<id>`
- `/admin/partner-organizations/<id>/users`

Admin pages show:

- partner organization;
- submitted by;
- row counts;
- valid rows;
- rejected rows;
- duplicate warnings;
- created actors;
- update candidates;
- status;
- update cycle;
- freshness summary;
- data owner users.

They do not render restricted phone/email values or uploaded file internals.

## Actor Self-Update Foundation

Added:

- `/partner/actor-update-invitations`

This page documents the future invite-based flow:

- partner invites an actor to confirm/update their record;
- actor updates become pending change requests;
- no actor update auto-publishes;
- partner/admin review remains required;
- existing consent, review, publish-readiness, entitlement, audit, and API safety gates remain authoritative.

The actual invite-token workflow is intentionally left for a later release.

## Demo Seed Updates

Updated:

```bash
python scripts/seed_demo_data.py --confirm-demo-seed
```

The seed now creates:

- a partner organization;
- a partner owner/editor user profile;
- sample actor records with freshness and last verified metadata;
- one valid import row;
- one rejected/correction row;
- one update candidate row;
- a partner dashboard state that demonstrates the owner journey.

The seed remains synthetic, deterministic, local/demo oriented, and does not create paid entitlements.

## Validation

Added:

```bash
python scripts/validate_partner_data_owner_onboarding.py
```

Updated:

```bash
python scripts/validate_all_phases.py
```

Validation covers:

- protected partner onboarding route;
- partner dashboard journey language and navigation;
- single actor registration fields;
- bulk upload route and parser;
- spelling variants in the source template;
- invalid row correction messages;
- error CSV;
- cross-partner batch isolation;
- admin import and partner organization summaries;
- restricted contact safety;
- absence of disallowed one-off workflow language from partner surfaces.

Run before completion:

```bash
python scripts/validate_all_phases.py
python scripts/validate_partner_data_owner_onboarding.py
python -m compileall app.py models.py routes scripts intelligence_insights.py intelligence_sources.py intelligence_engine.py
git diff --check
```

## Boundaries

- Stripe and Paystack are unchanged.
- No payment entitlements are created.
- Restricted contact data is not exposed to public, subscriber, API, or buyer views.
- Uploaded file paths, private paths, raw files, hashes, and raw extraction text are not exposed.
- Consent, review, redaction, publish-readiness, entitlement, audit, and API safety gates are not bypassed.
- Replit Agent is not used.
- No deployment automation is added.
- Existing validation is not weakened.
