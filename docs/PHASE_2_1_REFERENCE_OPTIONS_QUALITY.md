# Phase 2.1 Reference Options And Quality Scoring

Date implemented: 2026-06-17

Linear issue: FSA-15

Branch: `feature/phase-2-1-reference-options-quality-scoring`

## 1. Model Added

Phase 2.1 adds `ReferenceOption` in `models.py`.

Fields:

- `id`
- `category`
- `code`
- `label`
- `description`
- `sort_order`
- `active`
- `is_default`
- `metadata_json`
- `created_at`
- `updated_at`

Uniqueness:

- `category` plus `code`

The phase also adds `MarketActor.source_reference_type` as a small, backward-compatible column. Existing `MarketActor.source_reference` remains in place for free-text references.

## 2. Seeded Reference Option Categories

`app.py` now seeds reference options idempotently through `seed_reference_options()`.

Seeded categories:

- `actor_status`
- `registration_status`
- `source_reference_type`
- `contact_role`
- `capacity_unit`
- `certification_verification_status`
- `certification_status`
- `constraint_category`
- `constraint_severity`
- `constraint_status`

The seed data follows FSA-15 and is managed in `REFERENCE_OPTIONS` in `app.py`.

For existing seeded options, startup refreshes label and sort order but preserves admin-managed `active` and `is_default` choices.

The existing dedicated business reference tables remain the source of truth for:

- `Crop`
- `Commodity`
- `Region`
- `State`
- `LGA`
- `Port`
- `TradeDestination`
- `CertificationType`
- `DocumentType`

## 3. Admin Routes Added

Phase 2.1 adds small admin routes to the existing `admin_bp` blueprint:

| Route | Methods | Purpose |
| --- | --- | --- |
| `/admin/reference-options` | GET | List and filter reference options by category. |
| `/admin/reference-options/new` | GET, POST | Create a new reference option in a supported category. |
| `/admin/reference-options/<option_id>/edit` | GET, POST | Edit label, description, sort order, active flag, default flag, and metadata. |

All routes use the existing `login_required` plus `admin_required` decorators. Ordinary users cannot manage reference options.

On edit, category and code are kept stable. This protects existing actor records that store option codes.

## 4. Actor Form Dropdown Changes

The partner actor form now prefers dropdowns for controlled fields:

- Actor status
- Registration status
- Source reference type
- Contact role
- Capacity unit
- Certification verification status
- Certification status
- Constraint category
- Constraint severity
- Constraint status

The form also begins using existing business reference tables where records exist:

- Crop from `Crop`
- Commodity from `Commodity`
- Region from `Region`
- State from `State`
- LGA from `LGA`
- Trade destination from `TradeDestination`
- Port of exit from `Port`
- Certification type from `CertificationType`

Existing text fields are retained where they preserve useful backward compatibility, such as commodity category, source reference, and certification name.

## 5. Fallback Behavior

Free-text fallback behavior is preserved:

- If `State` records do not exist, the actor form shows `state_name` text input.
- If `LGA` records do not exist, the actor form shows `lga_name` text input.
- If `TradeDestination` records do not exist, the actor form shows `trade_destination_name` text input.
- If `Port` records do not exist, the actor form shows `port_of_exit` text input.
- Reference-option validation allows existing free-text values for selected fields where backward compatibility matters, such as capacity unit and constraint category.

This means existing partner actor creation and edit behavior continues to work even before all reference tables are fully populated.

## 6. Quality Scoring Rules

`calculate_actor_quality_score(actor)` was added in `models.py`.

It returns:

- `score`
- `grade`
- `completed_sections`
- `missing_sections`
- `deferred_sections`
- `checks`

Scoring:

| Section | Points |
| --- | ---: |
| Core identity | 25 |
| Location | 15 |
| Contact | 15 |
| Export profile | 15 |
| Certification | 15 |
| Operational constraint | 5 |
| Partner workflow | 5 |
| Documents readiness | 5 |

Documents readiness is marked deferred until Phase 3 and currently contributes 0 points.

Grades:

- `low`: 0-39
- `medium`: 40-69
- `high`: 70-89
- `complete`: 90-100

The score is advisory only and does not block actor creation or editing.

## 7. UI Changes

Partner UI changes:

- Partner dashboard shows average actor quality when actors exist.
- Actor registry list shows each actor's quality score and grade.
- Actor detail page shows a progress bar, grade, missing sections, and deferred document-readiness note.

Admin UI changes:

- Admin dashboard links to Reference Options.
- Reference option list and form templates were added under `templates/admin/`.

Restricted contact fields remain protected:

- The actor list still does not render phone or email.
- Actor detail still only renders restricted contact fields to allowed partner roles.

## 8. Validation Commands

Run the Phase 2.1 validation script:

```bash
python scripts/validate_phase_2_1_reference_quality.py
```

Run Phase 1 and Phase 2 regression validation:

```bash
python scripts/validate_phase_1_data_foundation.py
python scripts/validate_phase_2_partner_portal.py
```

Run compile validation:

```bash
python -m compileall app.py models.py routes scripts
```

Run whitespace validation:

```bash
git diff --check
```

The validation scripts use in-memory SQLite and do not touch Replit PostgreSQL data. They still print the existing SQLite warning from the Postgres-only payment-plan startup helper.

## 9. Manual Replit Test Steps

After merging and pulling `main` in Replit:

1. Confirm the app starts with the existing Replit run workflow or `python app.py`.
2. Log in as an admin user.
3. Visit `/admin/reference-options`.
4. Filter by category and create/edit one non-critical reference option.
5. Log in as a partner user linked through `PartnerUserProfile`.
6. Visit `/partner/actors/new`.
7. Confirm controlled dropdowns appear for status, registration, source reference type, contact role, capacity unit, certification status, and constraint fields.
8. Create or edit an actor.
9. Confirm the actor registry list shows a quality score.
10. Open actor detail and confirm missing sections are visible where data is incomplete.

## 10. Deferred Scope

Still deferred:

- Document upload vault.
- Admin document review.
- Subscriber document access.
- API endpoints.
- Payment/add-on changes.
- Bulk CSV/XLSX import.
- Full migration framework.
- Complex cascading state/LGA JavaScript.
- Phase 3 document readiness scoring backed by uploaded documents.
