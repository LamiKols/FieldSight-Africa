# FieldSight Africa - Agricultural Intelligence Platform

## Overview
A subscription-controlled data access platform selling time-sensitive agricultural intelligence datasets. This platform monetises monthly agricultural intelligence via subscriptions using Stripe (international) and Paystack (Nigeria).

**Product Philosophy:** "This platform sells time-sensitive agricultural intelligence, not static directories. Access expires because intelligence decays."

## Tech Stack
- **Backend:** Python Flask
- **ORM:** SQLAlchemy
- **Database:** PostgreSQL
- **Auth:** Flask-Login
- **Payments:** Stripe (primary, international) + Paystack (regional, Nigeria)
- **Frontend:** Jinja2 + TailwindCSS (via CDN)

## Project Structure
```
/
├── app.py              # Main Flask application with seed functions
├── models.py           # SQLAlchemy database models
├── routes/
│   ├── auth.py         # Authentication (login, register, logout)
│   ├── public.py       # Public pages (home, pricing)
│   ├── subscriber.py   # Subscriber dashboard and dataset access
│   ├── admin.py        # Admin dashboard and dataset management
│   └── payments.py     # Stripe and Paystack payment integration
├── templates/
│   ├── base.html       # Base template with TailwindCSS
│   ├── home.html       # Landing page
│   ├── pricing.html    # Subscription plans
│   ├── login.html      # Login form
│   ├── register.html   # Registration form
│   ├── dashboard.html  # Subscriber dashboard
│   ├── datasets.html   # Dataset catalogue
│   ├── dataset_view.html   # Dataset viewer with export
│   └── admin/          # Admin templates
└── static/             # Static assets
```

## Database Models
- **User:** id, name, email, password_hash, role, created_at
- **Subscription:** id, user_id, provider, provider_subscription_id, plan_code, status, current_period_end
- **PaymentPlan:** id, code, name, stripe_price_id, paystack_plan_code, monthly_export_limit, allowed_datasets
- **Dataset:** id, code, name, description
- **DatasetMonth:** id, dataset_id, month, published, uploaded_at
- **DatasetRecord:** id, dataset_month_id, record_json
- **ExportLog:** id, user_id, dataset_month_id, rows_exported, exported_at

## Subscription Plans
- **Free:** View dataset catalogue only, no downloads
- **Starter ($29/mo):** 1 dataset (actor_activity_status), 5,000 rows/month
- **Intelligence ($99/mo):** All 4 datasets, 50,000 rows/month

## Datasets (MVP)
1. actor_activity_status
2. market_changes
3. crop_availability_status
4. trust_index

## Color Scheme
- **Primary (Green):** #059669
- **Secondary (Dark Green):** #065f46
- **Amber (Accent):** #f59e0b

## Environment Variables Required
- `DATABASE_URL` - PostgreSQL connection string (auto-configured)
- `SESSION_SECRET` - Flask session secret
- `STRIPE_SECRET_KEY` - Stripe API key
- `STRIPE_STARTER_PRICE_ID` - Stripe price ID for Starter plan
- `STRIPE_INTELLIGENCE_PRICE_ID` - Stripe price ID for Intelligence plan
- `STRIPE_WEBHOOK_SECRET` - Stripe webhook signing secret
- `PAYSTACK_SECRET_KEY` - Paystack API key
- `PAYSTACK_STARTER_PLAN_CODE` - Paystack plan code for Starter
- `PAYSTACK_INTELLIGENCE_PLAN_CODE` - Paystack plan code for Intelligence

## Running the Application
```bash
python app.py
```
The application runs on port 5000.

## Admin Access
Create an admin user by manually updating the `role` field to 'admin' in the database for a registered user.
