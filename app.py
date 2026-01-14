"""
Agricultural Intelligence Platform - Main Application

This platform sells time-sensitive agricultural intelligence, not static directories.
Access expires because intelligence decays.

FUTURE-READY:
- Webhooks reconciliation
- Annual billing
- API access
- Revenue sharing
- Data refresh automation
"""

import os
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, flash, request
from flask_login import LoginManager, login_required, current_user
from dotenv import load_dotenv

load_dotenv()

from models import db, User, PaymentPlan, Dataset, LicensedPack

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SESSION_SECRET', 'dev-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_recycle': 300,
    'pool_pre_ping': True,
}

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


from routes.auth import auth_bp
from routes.public import public_bp
from routes.subscriber import subscriber_bp
from routes.admin import admin_bp
from routes.payments import payments_bp

app.register_blueprint(auth_bp)
app.register_blueprint(public_bp)
app.register_blueprint(subscriber_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(payments_bp)


def migrate_payment_plans_table():
    """Add missing columns to payment_plans table if they don't exist"""
    from sqlalchemy import text
    try:
        db.session.execute(text("""
            DO $$ 
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'payment_plans' AND column_name = 'regions_allowed'
                ) THEN
                    ALTER TABLE payment_plans ADD COLUMN regions_allowed INTEGER DEFAULT 1;
                END IF;
                
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'payment_plans' AND column_name = 'crops_allowed'
                ) THEN
                    ALTER TABLE payment_plans ADD COLUMN crops_allowed INTEGER DEFAULT 6;
                END IF;
            END $$;
        """))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Migration warning: {e}")


def seed_payment_plans():
    plans = [
        {
            "code": "STARTER",
            "name": "Starter",
            "stripe_price_id": os.getenv("STRIPE_STARTER_PRICE_ID"),
            "paystack_plan_code": os.getenv("PAYSTACK_STARTER_PLAN_CODE"),
            "monthly_export_limit": 5000,
            "allowed_datasets": ["actor_activity_status"],
            "regions_allowed": 1,
            "crops_allowed": 6,
        },
        {
            "code": "INTELLIGENCE",
            "name": "Intelligence",
            "stripe_price_id": os.getenv("STRIPE_INTELLIGENCE_PRICE_ID"),
            "paystack_plan_code": os.getenv("PAYSTACK_INTELLIGENCE_PLAN_CODE"),
            "monthly_export_limit": 50000,
            "allowed_datasets": [
                "actor_activity_status",
                "market_changes",
                "crop_availability_status",
                "trust_index"
            ],
            "regions_allowed": 3,
            "crops_allowed": 15,
        }
    ]
    
    for plan_data in plans:
        existing = PaymentPlan.query.filter_by(code=plan_data["code"]).first()
        if existing:
            existing.regions_allowed = plan_data["regions_allowed"]
            existing.crops_allowed = plan_data["crops_allowed"]
        else:
            db.session.add(PaymentPlan(**plan_data))
    
    db.session.commit()


def seed_licensed_packs():
    packs = [
        {
            "code": "CORE_REGIONAL",
            "name": "Core Regional Intelligence Pack",
            "description": "Single region focus with up to 6 crops. Permanent licensed access to a point-in-time snapshot.",
            "regions_allowed": 1,
            "crops_allowed": 6,
            "price_usd": 1800,
            "price_ngn": 1500000,
        },
        {
            "code": "EXPANDED_REGIONAL",
            "name": "Expanded Regional Intelligence Pack",
            "description": "Two regions with up to 15 crops total. Permanent licensed access to a point-in-time snapshot.",
            "regions_allowed": 2,
            "crops_allowed": 15,
            "price_usd": 3800,
            "price_ngn": 3000000,
        },
        {
            "code": "NATIONAL",
            "name": "National Intelligence Pack",
            "description": "All 6 regions and all crops. Complete national coverage snapshot with permanent licensed access.",
            "regions_allowed": 6,
            "crops_allowed": None,
            "price_usd": 8500,
            "price_ngn": 7000000,
        }
    ]
    
    for pack_data in packs:
        existing = LicensedPack.query.filter_by(code=pack_data["code"]).first()
        if not existing:
            db.session.add(LicensedPack(**pack_data))
    
    db.session.commit()


def seed_datasets():
    datasets = [
        {
            "code": "actor_activity_status",
            "name": "Actor Activity Status",
            "description": "Monthly intelligence on agricultural actor activities and market participation."
        },
        {
            "code": "market_changes",
            "name": "Market Changes",
            "description": "Price movements, supply shifts, and demand patterns across agricultural markets."
        },
        {
            "code": "crop_availability_status",
            "name": "Crop Availability Status",
            "description": "Current crop inventory levels, harvest projections, and availability forecasts."
        },
        {
            "code": "trust_index",
            "name": "Trust Index",
            "description": "Reliability scores and trust metrics for agricultural market participants."
        }
    ]
    
    for ds in datasets:
        existing = Dataset.query.filter_by(code=ds["code"]).first()
        if not existing:
            db.session.add(Dataset(**ds))
    
    db.session.commit()


with app.app_context():
    db.create_all()
    migrate_payment_plans_table()
    seed_payment_plans()
    seed_datasets()
    seed_licensed_packs()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
