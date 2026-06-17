# Phase 2 Partner Data Portal

Date implemented: 2026-06-17

Linear issue: FSA-7

Branch: `feature/phase-2-partner-data-portal`

## 1. Routes Added

Phase 2 adds a partner-only Flask blueprint in `routes/partner.py` with the URL prefix `/partner`.

| Route | Methods | Purpose |
| --- | --- | --- |
| `/partner/` | GET | Partner dashboard with organization, role, actor count, draft batch count, submitted batch count, and quick links. |
| `/partner/actors` | GET | Lists actors owned by the current user's partner organization without restricted phone/email fields. |
| `/partner/actors/new` | GET, POST | Creates a `MarketActor` plus supplied location, contact, export profile, certification, and constraint records. |
| `/partner/actors/<actor_id>` | GET | Shows structured actor details for actors owned by the current user's partner organization. |
| `/partner/actors/<actor_id>/edit` | GET, POST | Updates an actor owned by the current user's partner organization and records the change. |
| `/partner/batches` | GET | Lists update batches for the current user's partner organization. |
| `/partner/batches/new` | GET, POST | Creates a draft `PartnerUpdateBatch`, defaulting to `actor_registry`. |
| `/partner/batches/<batch_id>` | GET | Shows batch status, metadata, and linked record changes. |
| `/partner/batches/<batch_id>/submit` | POST | Moves a draft batch to `submitted` and sets `submitted_at`. |

No API endpoints, payment routes, subscriber export routes, or admin review screens were added.

## 2. Templates Added

New templates live under `templates/partner/` and extend the existing `base.html` layout:

- `dashboard.html`
- `actors.html`
- `actor_form.html`
- `actor_detail.html`
- `batches.html`
- `batch_form.html`
- `batch_detail.html`

The templates reuse the existing Tailwind CDN utility approach. The only global template change is a conditional `Partner Portal` navigation link in `templates/base.html` for authenticated users with an active partner profile.

## 3. Partner Access-Control Model

The portal uses the existing Flask-Login session and `User` model. It does not create a second login system.

Partner authorization is based on `PartnerUserProfile`:

- The profile must belong to `current_user`.
- The profile status must be `active`.
- The linked `PartnerOrganization` status must be `active`.
- The role must be one of the Phase 1 partner roles.

Helper functions added in `routes/partner.py`:

- `get_partner_profile_for_user(user)`
- `get_current_partner_profile()`
- `get_current_partner_org()`
- `require_partner_user()`
- `require_partner_role(...)`

All partner routes require login and active partner profile access. Actor and batch lookups are scoped by `partner_organization_id`, so users cannot view or edit another partner organization's records.

## 4. Role Permissions

| Role | Permissions in Phase 2 |
| --- | --- |
| `partner_admin` | Full partner portal access for the user's own organization. |
| `data_editor` | Create and edit actors and draft batches for the user's own organization. |
| `data_reviewer` | View organization records and submit draft batches. |
| `partner_viewer` | Read-only portal access. Restricted contact fields remain hidden. |

Restricted contact fields are visible only to:

- `partner_admin`
- `data_editor`
- `data_reviewer`

The actor list never renders phone or email fields.

## 5. Creating Or Linking A Partner User For Testing

Phase 2 adds `scripts/create_partner_user.py` as a safe bootstrap script. It links an existing registered user to a partner organization and does not create public partner organizations through the web app.

Example:

```bash
python scripts/create_partner_user.py \
  --email user@example.com \
  --org-name "Example Export Partner" \
  --role data_editor
```

Optional arguments include:

- `--org-slug`
- `--org-status`
- `--profile-status`
- `--contact-name`
- `--contact-email`
- `--contact-phone`

Use the existing registration flow first if the user account does not exist.

## 6. Actor Form Field Mapping

The actor form maps practical exporter spreadsheet fields into the Phase 1 model structure:

| Form Field | Model Field |
| --- | --- |
| Actor Name | `MarketActor.name` |
| Actor Type | `MarketActor.actor_type` |
| Crop | `MarketActor.crop_id` |
| Commodity Category | `MarketActor.commodity_category` |
| Registration Status | `MarketActor.registration_status` |
| Date of Registration | `MarketActor.date_of_registration` |
| Source Reference | `MarketActor.source_reference` |
| Status | `MarketActor.status` |
| Region | `ActorLocation.region_id` |
| State | `ActorLocation.state_name` |
| LGA | `ActorLocation.lga_name` |
| Location Text | `ActorLocation.location_text` and `ActorLocation.location` |
| Contact Role | `ActorContact.contact_role` |
| Contact Name | `ActorContact.contact_name` |
| Phone | `ActorContact.phone` |
| Email | `ActorContact.email` |
| Years in Export Trade | `ActorExportProfile.years_in_export_trade` |
| Trade Destination | `ActorExportProfile.trade_destination_name` |
| Export Capacity | `ActorExportProfile.export_capacity` |
| Capacity Unit | `ActorExportProfile.export_capacity_unit` |
| Port of Exit | `ActorExportProfile.port_of_exit` |
| Certification Name | `ActorCertification.certification_name` |
| Certificate Number | `ActorCertification.certificate_number` |
| Reference Number | `ActorCertification.reference_number` |
| Issuing Body | `ActorCertification.issuing_body` |
| Constraint Category | `ActorConstraint.constraint_category` |
| Constraint Text | `ActorConstraint.constraint_text` |
| Severity | `ActorConstraint.severity` |

Required actor validation:

- Actor name is required.
- Actor type must match the Phase 1 supported actor types.
- Actor status must match the Phase 1 common statuses.
- Selected crop, region, and draft batch IDs must belong to existing safe records.
- Constraint text is required when constraint details are supplied.

## 7. Batch Workflow

Partners can create draft batches from `/partner/batches/new`. The default dataset type is `actor_registry`.

Allowed Phase 2 transition:

- `draft` -> `submitted`

The submit route rejects non-draft batches. On submission, the route sets:

- `PartnerUpdateBatch.status = "submitted"`
- `PartnerUpdateBatch.submitted_at`
- `PartnerUpdateBatch.submitted_by_user_id`

Linked `PartnerRecordChange` rows are also moved to `submitted`.

When actors are created or edited without selecting a draft batch, the portal auto-creates or reuses a monthly draft batch named `Direct actor changes - YYYY-MM`. This keeps direct form edits traceable without requiring a partner to manually create a batch first.

## 8. Audit Logging Behavior

Phase 2 writes `AuditLog` records for:

- `partner_actor_created`
- `partner_actor_updated`
- `partner_batch_created`
- `partner_batch_submitted`

Audit rows include the current user, partner organization, entity type, entity ID, basic before/after JSON where applicable, IP address, and user agent.

Actor creates and updates also write a basic `PartnerRecordChange` row with `before_values` and `after_values` snapshots. This is intentionally lightweight and does not try to build full field-level diff tooling yet.

## 9. Deferred Scope

The following FSA capabilities remain deferred to later phases:

- Document upload UI.
- Document vault workflow.
- Admin submission review screens.
- Publishing approved partner records into commercial `DatasetMonth` snapshots.
- Subscriber actor registry catalogue.
- Customer API endpoints.
- Payment/add-on changes.
- Bulk CSV/XLSX import.
- S3 or object storage integration.
- Full migration framework.

## 10. Replit Validation Steps

Run the Phase 2 validation script:

```bash
python scripts/validate_phase_2_partner_portal.py
```

Run compile validation:

```bash
python -m compileall app.py models.py routes scripts
```

Optional Phase 1 regression validation:

```bash
python scripts/validate_phase_1_data_foundation.py
```

Start the existing Replit app with the existing command:

```bash
python app.py
```

If port 5000 is already in use on Replit, that usually indicates the Replit web process is already running.
