# Phase 0 Repository Baseline

Date inspected: 2026-06-17

Repository: `LamiKols/FieldSight-Africa`

Branch: `feature/phase-0-repo-baseline`

## 1. Current Architecture Summary

FieldSight Africa is an existing Replit-hosted Flask application for selling access to time-sensitive agricultural intelligence data. The current app is a server-rendered Flask/Jinja application backed by SQLAlchemy models and a PostgreSQL database. It uses Flask-Login for browser-session authentication, Tailwind CSS from the CDN for styling, and payment integrations for Stripe and Paystack.

The main product surfaces are:

- Public marketing and pricing pages.
- Subscriber registration, login, dashboard, dataset catalogue, dataset viewing, and CSV export.
- Licensed one-time data packs with Stripe and Paystack checkout flows.
- Sales-led Live Market Intelligence access granted by admins.
- Admin pages for dataset upload/publish management, user inspection, export monitoring, and Live Intelligence grants.

The codebase is compact and mostly organized around one root application module, one model module, and route blueprints under `routes/`. There is no separate API package, migration framework, service layer, or frontend build pipeline in the current repository.

## 2. Current File/Folder Structure

```text
.
|-- .gitignore
|-- .replit
|-- app.py
|-- main.py
|-- models.py
|-- pyproject.toml
|-- replit.md
|-- uv.lock
|-- attached_assets/
|   |-- IMG_7640_1766238056681.png
|   |-- image_1765801447913.png
|   |-- image_1781628555581.png
|   |-- image_1781628582579.png
|   |-- image_1781693894695.png
|   |-- image_1781693908712.png
|   |-- Pasted-*.txt
|-- routes/
|   |-- __init__.py
|   |-- admin.py
|   |-- auth.py
|   |-- payments.py
|   |-- public.py
|   |-- subscriber.py
|-- static/
|   |-- images/
|       |-- logo.png
|-- templates/
|   |-- base.html
|   |-- dashboard.html
|   |-- dataset_view.html
|   |-- datasets.html
|   |-- home.html
|   |-- licenses.html
|   |-- live_intelligence.html
|   |-- login.html
|   |-- pack_checkout.html
|   |-- packs.html
|   |-- pricing.html
|   |-- register.html
|   |-- admin/
|       |-- dashboard.html
|       |-- datasets.html
|       |-- live_intelligence.html
|       |-- upload.html
|       |-- user_detail.html
|       |-- users.html
|-- docs/
    |-- PHASE_0_REPO_BASELINE.md
```

Notes:

- `attached_assets/` contains images and pasted planning/instruction text from previous Replit work. These are not imported by the current app code.
- `main.py` only prints `Hello from repl-nix-workspace!`; it is not the active web entry point.
- No `requirements.txt` is present. Dependencies are managed through `pyproject.toml` and `uv.lock`.

## 3. Application Startup/Runtime Flow

Primary entry point: `app.py`

Runtime flow:

1. `app.py` loads environment variables through `python-dotenv`.
2. A global Flask app is created with `app = Flask(__name__)`.
3. Flask config is set:
   - `SECRET_KEY` from `SESSION_SECRET`, with fallback `dev-secret-key`.
   - `SQLALCHEMY_DATABASE_URI` from `DATABASE_URL`.
   - `SQLALCHEMY_TRACK_MODIFICATIONS = False`.
   - SQLAlchemy engine options use `pool_recycle` and `pool_pre_ping`.
4. `db.init_app(app)` attaches the SQLAlchemy instance from `models.py`.
5. `LoginManager` is initialized with `login_view = 'auth.login'`.
6. The user loader resolves users by `User.query.get(int(user_id))`.
7. Blueprints are imported and registered:
   - `auth_bp`
   - `public_bp`
   - `subscriber_bp`
   - `admin_bp`
   - `payments_bp`
8. Inside `app.app_context()`, startup creates and seeds database state:
   - `db.create_all()`
   - `migrate_payment_plans_table()`
   - `seed_payment_plans()`
   - `seed_datasets()`
   - `seed_licensed_packs()`
9. Local development runs `app.run(host='0.0.0.0', port=5000, debug=True)`.
10. Replit deployment runs Gunicorn with `app:app`.

Important baseline behavior: the app performs schema creation, a targeted payment-plan table alteration, and seed updates at import/startup time. Future phases should account for this before adding migrations or startup side effects.

## 4. Existing Database Models

All models are defined in `models.py` using Flask-SQLAlchemy.

### User

Table: `users`

Fields include `id`, `name`, `email`, `password_hash`, `role`, and `created_at`.

Behavior:

- Inherits `UserMixin`.
- Passwords are hashed with Werkzeug helpers.
- `role == 'admin'` controls admin access.
- Includes helpers for active subscription lookup, plan lookup, dataset access, monthly export totals, and export-limit checks.

### Subscription

Table: `subscriptions`

Represents monthly access from a payment provider. Fields include `user_id`, `provider`, `provider_subscription_id`, `plan_code`, `status`, `current_period_end`, `regions_selected`, and `crops_selected`.

### PaymentPlan

Table: `payment_plans`

Represents seeded subscription tiers. Fields include provider identifiers, monthly export limit, allowed datasets, region limits, and crop limits.

Seeded plan codes:

- `STARTER`
- `INTELLIGENCE`

### Dataset

Table: `datasets`

Represents a dataset catalogue item. Seeded dataset codes:

- `actor_activity_status`
- `market_changes`
- `crop_availability_status`
- `trust_index`

### DatasetMonth

Table: `dataset_months`

Represents a month of data for a dataset, with `published` status and `uploaded_at`. It has a unique constraint across `dataset_id` and `month`.

### DatasetRecord

Table: `dataset_records`

Stores uploaded CSV rows as JSON in `record_json`, associated with a `DatasetMonth`.

### ExportLog

Table: `export_logs`

Records CSV exports by user, dataset month, row count, and timestamp. Used for monthly export accounting and admin export monitoring.

### ViewLog

Table: `view_logs`

Records dataset views by user and dataset month. Used by subscriber dataset view rate limiting.

### LicensedPack

Table: `licensed_packs`

Represents one-time licensed data pack products. Fields include limits, USD/NGN prices, optional payment identifiers/links, active flag, and timestamps.

Seeded pack codes:

- `CORE_REGIONAL`
- `EXPANDED_REGIONAL`
- `NATIONAL`

### License

Table: `licenses`

Represents activated one-time pack access for a user. Stores selected regions/crops, snapshot month, status, and Stripe or Paystack payment references.

### LiveIntelligenceAccess

Table: `live_intelligence_access`

Represents admin-granted live intelligence access with selected regions/crops, start/end dates, active flag, and notes.

### Payment

Table: `payments`

Records completed one-time licensed-pack payments with provider, provider reference, payment type, amount, status, and metadata.

### Entitlement Logic

`get_user_entitlements(user)` centralizes access priority:

1. Active Live Intelligence access.
2. Active License.
3. Active Subscription.
4. Free catalogue-only access.

This function is a key integration point for future access-controlled features.

## 5. Existing Routes and What Each Route Appears To Do

### Public Routes: `routes/public.py`

| Route | Methods | Purpose |
| --- | --- | --- |
| `/` | GET | Render the public landing page. |
| `/pricing` | GET | Load all `PaymentPlan` rows and render subscription pricing. |

### Auth Routes: `routes/auth.py`

| Route | Methods | Purpose |
| --- | --- | --- |
| `/login` | GET, POST | Authenticate existing users, then redirect admins to admin dashboard and subscribers to subscriber dashboard. |
| `/register` | GET, POST | Validate name/email/password, create a subscriber user, log them in, and redirect to data packs. |
| `/logout` | GET | Log out the current authenticated user and redirect home. |

### Subscriber Routes: `routes/subscriber.py`

| Route | Methods | Purpose |
| --- | --- | --- |
| `/dashboard` | GET | Authenticated subscriber dashboard showing entitlement, plan, datasets, exports, and available months. |
| `/datasets` | GET | Authenticated dataset catalogue with access flags and published months. Licenses are scoped to the licensed snapshot month. |
| `/datasets/<dataset_code>/<month>` | GET | Authenticated, entitlement-required dataset viewer with rate limiting, filtering by regions/crops, view logging, and first 100 records displayed. |
| `/export/<dataset_month_id>` | GET | Authenticated, entitlement-required CSV export with region/crop filtering, export-limit enforcement, and `ExportLog` creation. |
| `/packs` | GET | Public licensed data pack catalogue, with current-month snapshot context. |
| `/licenses` | GET | Authenticated list of the current user's purchased licenses. |
| `/live-intelligence` | GET | Public Live Market Intelligence explainer/request page. |
| `/live-intelligence/request` | POST | Authenticated request form handler. Currently flashes a confirmation and does not persist the request. |

### Admin Routes: `routes/admin.py`

All admin routes use `/admin` prefix plus both `login_required` and `admin_required`.

| Route | Methods | Purpose |
| --- | --- | --- |
| `/admin/` | GET | Admin dashboard with subscriber count, active subscriptions, dataset count, total exported rows, and recent exports. |
| `/admin/upload` | GET, POST | Upload CSV data for a selected dataset and month. Supports optional overwrite and maps state names to Nigerian region codes. |
| `/admin/datasets` | GET | View uploaded dataset months and publish status. |
| `/admin/datasets/<dataset_month_id>/publish` | POST | Mark a dataset month as published. |
| `/admin/datasets/<dataset_month_id>/unpublish` | POST | Mark a dataset month as unpublished. |
| `/admin/users` | GET | List users. |
| `/admin/users/<user_id>` | GET | Show user details and export history. |
| `/admin/live-intelligence` | GET | View existing Live Intelligence grants and form for granting access. |
| `/admin/live-intelligence/grant` | POST | Create a Live Intelligence access grant for a subscriber. |
| `/admin/live-intelligence/<grant_id>/toggle` | POST | Toggle a Live Intelligence grant active/inactive. |
| `/admin/live-intelligence/<grant_id>/delete` | POST | Delete a Live Intelligence grant. |

### Payment Routes: `routes/payments.py`

| Route | Methods | Purpose |
| --- | --- | --- |
| `/subscribe/stripe/<plan_code>` | GET | Start Stripe subscription checkout for a seeded `PaymentPlan`. |
| `/subscribe/paystack/<plan_code>` | GET | Start Paystack subscription checkout for a seeded `PaymentPlan`. |
| `/payment/success` | GET | Verify Stripe subscription checkout session and create a `Subscription`. |
| `/payment/paystack/callback` | GET | Verify Paystack subscription transaction and create a `Subscription`. |
| `/webhook/stripe` | POST | Stripe webhook endpoint for subscription update/deletion events. Returns JSON. |
| `/webhook/paystack` | POST | Paystack webhook endpoint for subscription disable events. Returns JSON. |
| `/pack/<pack_code>/<provider>` | GET | Render one-time licensed-pack checkout selection page. |
| `/pack/<pack_code>/<provider>/process` | POST | Validate selected regions/crops and start Stripe or Paystack one-time pack payment. |
| `/payment/pack/success` | GET | Verify Stripe one-time pack checkout and create `License` plus `Payment` records. |
| `/payment/pack/paystack/callback` | GET | Verify Paystack one-time pack transaction and create `License` plus `Payment` records. |

## 6. Existing Templates and What Each Template Supports

All templates use Jinja and extend `templates/base.html`.

| Template | Purpose |
| --- | --- |
| `base.html` | Shared HTML shell, Tailwind CDN config, navigation, flash messages, footer, logo. |
| `home.html` | Public landing page for FieldSight Africa and calls to view packs/live intelligence. |
| `pricing.html` | Subscription pricing cards for free and seeded paid plans, with Stripe/Paystack links. |
| `login.html` | Login form. |
| `register.html` | Registration form. |
| `dashboard.html` | Subscriber dashboard with access status, export usage, dataset access, and upgrade prompts. |
| `datasets.html` | Dataset catalogue and published month links based on entitlements. |
| `dataset_view.html` | Dataset month table preview, export link, anti-copy UI behavior, watermark/access notice. |
| `packs.html` | Licensed data pack catalogue with Stripe and Paystack purchase links. |
| `pack_checkout.html` | Region/crop selection before pack payment. |
| `licenses.html` | User license list and explanation of licensed snapshot access. |
| `live_intelligence.html` | Live Intelligence explainer and request form. |
| `admin/dashboard.html` | Admin metrics and recent export activity. |
| `admin/upload.html` | Admin CSV upload form. |
| `admin/datasets.html` | Admin dataset month list with publish/unpublish forms. |
| `admin/users.html` | Admin user list. |
| `admin/user_detail.html` | Admin user details and export history. |
| `admin/live_intelligence.html` | Admin Live Intelligence grants and grant form. |

Page structure:

- `base.html` provides global navigation.
- Public navigation includes Home, Data Packs, Live Intelligence, Login, and Sign Up.
- Authenticated navigation adds Datasets, Dashboard, Logout, and Admin if the user is an admin.
- Styling is mostly inline Tailwind utility classes rather than local CSS files.

## 7. Existing Admin Functionality

Admin access is role-based. A user is considered admin when `User.role == 'admin'`. The existing `replit.md` notes that admin users are created by manually updating a registered user's `role` field in the database.

Current admin capabilities:

- View high-level metrics.
- Inspect recent export activity.
- Upload monthly CSV data for existing dataset types.
- Override an existing dataset month during upload.
- Publish/unpublish dataset months.
- List users.
- View individual user details and export history.
- Grant, toggle, and delete Live Intelligence access.

Current admin limitations and assumptions:

- There is no admin UI for creating new dataset definitions.
- There is no admin UI for editing payment plans or licensed pack prices.
- CSV upload stores all row data directly as JSON records.
- Live Intelligence request form submissions are not persisted or surfaced in admin.
- Admin role assignment is manual database work.

## 8. Existing Payment/Subscription/Licence Functionality

The app has both subscription and one-time licensed-pack flows.

### Stripe

Subscription flow:

- `/subscribe/stripe/<plan_code>` creates a Stripe Checkout Session in subscription mode.
- `/payment/success` retrieves the session and Stripe subscription, then creates a local `Subscription`.
- `/webhook/stripe` updates or cancels subscriptions based on Stripe webhook events.

Licensed pack flow:

- `/pack/<pack_code>/stripe` renders pack selection.
- `/pack/<pack_code>/stripe/process` creates a Stripe Checkout Session in one-time payment mode using dynamic `price_data`.
- `/payment/pack/success` verifies the session, creates a `License`, and records a `Payment`.

### Paystack

Subscription flow:

- `/subscribe/paystack/<plan_code>` initializes a Paystack transaction with a Paystack plan code.
- `/payment/paystack/callback` verifies the transaction and creates a local `Subscription` with a 30-day period.
- `/webhook/paystack` verifies the Paystack signature and handles `subscription.disable` by cancelling a matching local subscription.

Licensed pack flow:

- `/pack/<pack_code>/paystack` renders pack selection.
- `/pack/<pack_code>/paystack/process` initializes a NGN one-time Paystack transaction.
- `/payment/pack/paystack/callback` verifies the transaction, creates a `License`, and records a `Payment`.

### Access Model

Access is resolved through `get_user_entitlements()` with this priority:

1. Live Intelligence grant.
2. Licensed pack snapshot.
3. Active subscription.
4. Free access.

This means future paid access features should use or extend this entitlement function instead of checking payments directly.

## 9. Existing API/Export Functionality

There is no separate versioned JSON API for product data.

Existing JSON-like endpoints:

- `/webhook/stripe`
- `/webhook/paystack`

Both are payment webhook endpoints and return JSON responses.

Existing export/download logic:

- `/export/<dataset_month_id>` returns CSV through a Flask `Response`.
- Export data is filtered by entitlement regions and crops.
- Subscription exports enforce monthly row limits.
- Export activity is logged to `ExportLog`.
- License and Live Intelligence access appear to allow unlimited exports, because their entitlements use `monthly_export_limit = None`.

Existing CSV ingestion logic:

- `/admin/upload` accepts CSV files.
- It uses `csv.DictReader`.
- If a row has `state`, `State`, or `STATE`, the app maps it to `region_code` using `NIGERIA_STATE_REGION_MAP`.
- Rows with unknown states are rejected from the upload batch and reported through flash messaging.

## 10. Existing Environment Variables

Environment variables read by application code:

| Variable | Used in | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `app.py` | SQLAlchemy database connection URI. |
| `SESSION_SECRET` | `app.py` | Flask session signing secret. Falls back to `dev-secret-key`. |
| `STRIPE_SECRET_KEY` | `routes/payments.py` | Stripe API key. |
| `STRIPE_STARTER_PRICE_ID` | `app.py` | Seeded Stripe price ID for Starter plan. |
| `STRIPE_INTELLIGENCE_PRICE_ID` | `app.py` | Seeded Stripe price ID for Intelligence plan. |
| `STRIPE_WEBHOOK_SECRET` | `routes/payments.py` | Stripe webhook signature secret. |
| `PAYSTACK_SECRET_KEY` | `routes/payments.py` | Paystack API key and webhook HMAC secret. |
| `PAYSTACK_STARTER_PLAN_CODE` | `app.py` | Seeded Paystack plan code for Starter plan. |
| `PAYSTACK_INTELLIGENCE_PLAN_CODE` | `app.py` | Seeded Paystack plan code for Intelligence plan. |
| `REPLIT_DEV_DOMAIN` | `routes/payments.py` | Used to construct checkout callback URLs; falls back to `request.host_url`. |

`python-dotenv` is loaded at startup, so local `.env` files are supported. `.env` is ignored by `.gitignore`.

## 11. Existing Replit Runtime/Deployment Setup

`.replit` config:

- Modules:
  - `python-3.11`
  - `postgresql-16`
- Nix channel: `stable-25_05`
- Replit integrations:
  - `python_log_in_with_replit:1.0.0`
  - `python_database:1.0.0`
- Run button workflow:
  - `Project` workflow runs `Start application`.
  - `Start application` executes `python app.py`.
  - Waits for port `5000`.
  - Output type is `webview`.
- Port mapping:
  - Local port `5000`
  - External port `80`
- Deployment:
  - Target: `autoscale`
  - Run command: `gunicorn --bind=0.0.0.0:5000 --reuse-port app:app`

Dependency setup:

- `pyproject.toml` defines Python `>=3.11`.
- Dependencies include Flask, Flask-Dance, Flask-Login, Flask-SQLAlchemy, Gunicorn, OAuth/PyJWT-related packages, psycopg2-binary, python-dotenv, Stripe, and Werkzeug.
- `uv.lock` is committed.

## 12. Gaps and Risks Before Expansion

Key risks to address carefully before larger build phases:

- Startup schema mutation: `db.create_all()` and `migrate_payment_plans_table()` run at import/startup. Adding models or schema changes without a migration plan can create production drift.
- No migration framework: There is no Alembic/Flask-Migrate setup. Current schema evolution is ad hoc.
- Payment verification is callback-heavy: Success callbacks create subscriptions/licenses. Webhooks exist but do not fully reconcile all payment states or one-time pack purchases.
- Webhook coverage is partial: Stripe handles subscription update/delete; Paystack handles subscription disable. One-time licensed pack payment webhooks are not currently used for reconciliation.
- No persisted Live Intelligence requests: The public request form only flashes a message.
- Admin role is manually assigned in the database.
- No CSRF protection is configured globally. Some templates include a conditional `csrf_token()` call, but the app does not currently initialize Flask-WTF or equivalent CSRF middleware.
- No explicit authorization checks on payment callback ownership beyond `login_required` and current user context. Future payment hardening should verify metadata/user ownership carefully.
- Subscription `provider_subscription_id` for Paystack subscriptions is set to the transaction reference, while the Paystack webhook searches by `subscription_code`; this may affect cancellation reconciliation.
- Dataset rows are arbitrary JSON from CSV uploads. Future consumers should not assume a stable schema unless enforced during upload.
- CSV upload reads all rows into memory before processing.
- Dataset view rate limiting is database-count based and scoped to page views, not exports.
- Styling is CDN Tailwind with no local build step. Future UI work should stay consistent unless a build pipeline is intentionally introduced.
- `main.py` is not the app entry point and may confuse future tooling.
- `requests` is imported directly in payment routes but is not listed as a direct dependency in `pyproject.toml`; it is present transitively in `uv.lock` through Stripe/Flask-Dance. Future dependency cleanup should decide whether to add it explicitly.
- No automated tests are present in the inspected repository.
- There is no separate application factory. The app is created globally, and startup side effects run at import time, which affects testing and scripts.

## 13. Recommended Safe Integration Approach for Next Build Phases

Recommended approach:

1. Preserve the current Flask/Jinja blueprint structure.
2. Treat `app.py`, `models.py`, and the route files as the current source of truth.
3. Add new behavior in small, route-specific increments rather than replacing the app shell.
4. Reuse `get_user_entitlements()` for all new access-control decisions.
5. Avoid adding new startup database side effects until a migration approach is agreed.
6. If schema changes are required, introduce a migration plan explicitly before changing models.
7. Keep payment changes isolated to `routes/payments.py` unless introducing a documented service layer.
8. Keep admin-only functionality behind `admin_required`.
9. Preserve existing route paths and template names to avoid breaking Replit workflows and existing links.
10. Keep Tailwind CDN styling consistent for near-term UI changes; introduce a build pipeline only as a deliberate phase.
11. Add tests around entitlement logic, CSV upload/export behavior, and payment callback/webhook reconciliation before broadening paid-access features.
12. Document new environment variables at the same time they are introduced.
13. Avoid editing `pyproject.toml`, `uv.lock`, `.replit`, or payment environment variables unless the build phase explicitly requires it.

For the next build phases, the safest extension path is:

- First, add tests or lightweight verification scripts for existing entitlement, export, and payment behavior.
- Second, add new admin or subscriber pages as new routes/templates using the current blueprint conventions.
- Third, introduce schema changes only after deciding whether to keep the current `db.create_all()` approach or move to migrations.
- Fourth, harden payments and CSRF before increasing paid feature complexity.
