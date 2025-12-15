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

from models import db, User, PaymentPlan, Dataset

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


def seed_payment_plans():
    plans = [
        {
            "code": "STARTER",
            "name": "Starter",
            "stripe_price_id": os.getenv("STRIPE_STARTER_PRICE_ID"),
            "paystack_plan_code": os.getenv("PAYSTACK_STARTER_PLAN_CODE"),
            "monthly_export_limit": 5000,
            "allowed_datasets": ["actor_activity_status"],
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
        }
    ]
    
    for plan in plans:
        existing = PaymentPlan.query.filter_by(code=plan["code"]).first()
        if not existing:
            db.session.add(PaymentPlan(**plan))
    
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
    seed_payment_plans()
    seed_datasets()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
