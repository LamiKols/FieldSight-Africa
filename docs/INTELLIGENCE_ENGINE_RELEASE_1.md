# Intelligence Engine Release 1

Linear source of truth: FSA-29

Branch: `feature/intelligence-engine-release-1`

## Purpose

Release 1 creates the first coherent FieldSight Africa intelligence engine layer on top of the Phase 5 automation foundation. It adds a safe source registry, deterministic manual ingestion records, change detection, internal alerts, publication candidates, subscriber digest visibility, validation, and documentation.

This release does not replace document automation, document review, consent, redaction, publish-readiness, entitlement, API safety, payment, export, or partner workflows.

## Added Models

- `IntelligenceSource`: registered safe source metadata, trust level, status, category, cadence, owner team, public reference URL, safe configuration JSON, and allowed summary fields.
- `IntelligenceIngestionRun`: manual source ingestion history with safe summary JSON, status, detected change count, generated alert count, optional linked insight, and requested user.
- `IntelligenceChangeEvent`: internal change-detection event generated from an ingestion run.
- `IntelligenceAlert`: internal alert queue item generated from a change event, with review status and optional linked `IntelligenceInsight`.
- `IntelligencePublicationCandidate`: reviewed intelligence candidate for controlled subscriber digest visibility.
- `SubscriberIntelligenceDigest`: approved safe digest summary visible to logged-in subscribers.

## Admin Routes

- `/admin/intelligence-sources`: list and filter sources.
- `/admin/intelligence-sources/new`: create safe source records.
- `/admin/intelligence-sources/<id>`: source detail, safe configuration, recent runs, recent alerts, and manual run control.
- `/admin/intelligence-sources/<id>/edit`: edit source status, category, trust, cadence, and safe configuration.
- `/admin/intelligence-sources/<id>/run`: create a manual ingestion run for active sources only.
- `/admin/intelligence-ingestion-runs`: list ingestion runs.
- `/admin/intelligence-ingestion-runs/<id>`: run detail, safe summary, change events, alerts, and audit trail.
- `/admin/intelligence-alerts`: alert queue.
- `/admin/intelligence-alerts/<id>`: alert detail and review form.
- `/admin/intelligence-alerts/<id>/review`: review alert and optionally create a publication candidate when gates pass.
- `/admin/intelligence-publication-candidates`: publication candidate queue.
- `/admin/intelligence-publication-candidates/<id>`: candidate detail and review workflow.

All admin routes use the existing `admin_required` guard.

## Subscriber Routes

- `/subscriber/intelligence-digests`: approved safe digest list for logged-in subscribers.
- `/subscriber/intelligence-digests/<id>`: safe digest detail.

Subscriber digest pages expose safe summaries only. They do not create document access, API access, buyer access, subscriptions, licences, payment changes, or file downloads.

## Helper Modules

- `intelligence_engine.py`: central source, ingestion, change, alert, publication candidate, digest, sanitization, and audit helper layer.
- `intelligence_sources.py`: compatibility exports for source-related helpers named in the release scope.

## Governance Rules

The release preserves existing gates:

- actor consent remains authoritative for document-derived external sharing;
- document review, verification, redaction, and publish-readiness remain separate;
- entitlement checks remain authoritative for document metadata/API surfaces;
- API-safe metadata is not changed;
- no document file, private path, original filename, stored filename, hash, contact field, raw extraction text, restricted document field, API secret, or key hash is exposed;
- no automatic publishing occurs;
- no subscriber, API, or buyer access is granted automatically;
- Stripe and Paystack flows are unchanged;
- no external AI/OCR provider calls are added;
- no live crawling of restricted systems is added;
- no deployment automation or Replit Agent dependency is added.

## Status Flow

Source statuses:

- `active`
- `paused`
- `disabled`
- `archived`

Only `active` sources can create manual ingestion runs.

Ingestion run statuses:

- `queued`
- `completed`
- `needs_review`
- `failed`
- `cancelled`

Release 1 manual ingestion runs are deterministic and complete immediately after safe change and alert records are created.

Alert statuses:

- `open`
- `in_review`
- `approved`
- `rejected`
- `archived`

Publication candidates can only be created from approved alerts. If an alert is linked to an `IntelligenceInsight`, the linked insight must be approved and marked as an approved publishing candidate before candidate creation is allowed.

Publication candidate statuses:

- `draft`
- `in_review`
- `approved`
- `rejected`
- `archived`

Approving a publication candidate creates or reuses an approved `SubscriberIntelligenceDigest` record containing safe summary metadata only.

## Validation

Added:

```bash
python scripts/validate_intelligence_engine_release_1.py
```

Updated:

```bash
python scripts/validate_all_phases.py
```

Release validation covers:

- admin-only protection for admin intelligence routes;
- source creation and editing;
- paused source run blocking;
- active source manual ingestion;
- safe run summaries;
- change event and alert creation;
- alert review and audit logs;
- publication candidate gating;
- subscriber digest creation for approved candidates only;
- subscriber digest list/detail safety;
- unsafe value suppression across records and rendered pages.

Run before completion:

```bash
python scripts/validate_all_phases.py
python scripts/validate_intelligence_engine_release_1.py
python -m compileall app.py models.py routes scripts intelligence_insights.py intelligence_sources.py intelligence_engine.py
git diff --check
```
