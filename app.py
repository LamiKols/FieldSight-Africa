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

from models import db, User, PaymentPlan, Dataset, LicensedPack, Region, Crop, DocumentType, ReferenceOption

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SESSION_SECRET', 'dev-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_recycle': 300,
    'pool_pre_ping': True,
}
app.config['PRIVATE_UPLOAD_ROOT'] = os.environ.get('PRIVATE_UPLOAD_ROOT', 'private_uploads')
app.config['DOCUMENT_STORAGE_BACKEND'] = os.environ.get('DOCUMENT_STORAGE_BACKEND', 'local_private')
app.config['S3_COMPATIBLE_ENDPOINT'] = os.environ.get('S3_COMPATIBLE_ENDPOINT')
app.config['S3_BUCKET_NAME'] = os.environ.get('S3_BUCKET_NAME')
app.config['S3_REGION'] = os.environ.get('S3_REGION')

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
from routes.partner import partner_bp, get_current_partner_profile

app.register_blueprint(auth_bp)
app.register_blueprint(public_bp)
app.register_blueprint(subscriber_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(payments_bp)
app.register_blueprint(partner_bp)


@app.context_processor
def inject_partner_profile():
    if current_user.is_authenticated:
        return {"current_partner_profile": get_current_partner_profile()}
    return {"current_partner_profile": None}


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


REFERENCE_REGIONS = [
    {"code": "SW", "name": "South West"},
    {"code": "SE", "name": "South East"},
    {"code": "SS", "name": "South South"},
    {"code": "NC", "name": "North Central"},
    {"code": "NW", "name": "North West"},
    {"code": "NE", "name": "North East"},
]

REFERENCE_CROPS = [
    {"code": "ginger", "name": "Ginger"},
    {"code": "sesame", "name": "Sesame"},
    {"code": "soybeans", "name": "Soybeans"},
]

SENSITIVE_DOCUMENT_TYPE_NAMES = {
    "National ID",
    "NIN Confirmation",
    "BVN Confirmation",
    "Bank Account Confirmation",
    "Tax Identification Number",
    "CAC Certificate",
    "Invoice Record",
    "Delivery Note",
    "Offtake Agreement",
}

DOCUMENT_TYPES_REQUIRING_EXPIRY = {
    "NEPC Registration",
    "Phytosanitary Certificate",
    "Quality Inspection Certificate",
    "Organic Certification",
    "GlobalG.A.P. Certification",
    "HACCP Certification",
    "Warehouse Receipt",
    "Offtake Agreement",
}

DOCUMENT_TYPES_REQUIRING_ISSUING_BODY = {
    "CAC Certificate",
    "Tax Identification Number",
    "Cooperative Registration Certificate",
    "Export Registration Certificate",
    "NEPC Registration",
    "Phytosanitary Certificate",
    "Quality Inspection Certificate",
    "Certificate of Origin",
    "Organic Certification",
    "GlobalG.A.P. Certification",
    "HACCP Certification",
    "Warehouse Receipt",
    "Offtake Agreement",
}

DOCUMENT_TYPES_REQUIRING_REFERENCE_NUMBER = {
    "National ID",
    "NIN Confirmation",
    "BVN Confirmation",
    "CAC Certificate",
    "Tax Identification Number",
    "Cooperative Registration Certificate",
    "Export Registration Certificate",
    "NEPC Registration",
    "Phytosanitary Certificate",
    "Quality Inspection Certificate",
    "Certificate of Origin",
    "Organic Certification",
    "GlobalG.A.P. Certification",
    "HACCP Certification",
    "Warehouse Receipt",
    "Invoice Record",
    "Delivery Note",
    "Bank Account Confirmation",
}

DOCUMENT_TYPE_CATEGORIES = {
    "National ID": "identity",
    "NIN Confirmation": "identity",
    "BVN Confirmation": "financial_identity",
    "Bank Account Confirmation": "financial_identity",
    "CAC Certificate": "business_registration",
    "Tax Identification Number": "business_registration",
    "Cooperative Registration Certificate": "business_registration",
    "Export Registration Certificate": "export_compliance",
    "NEPC Registration": "export_compliance",
    "Phytosanitary Certificate": "quality_compliance",
    "Quality Inspection Certificate": "quality_compliance",
    "Certificate of Origin": "export_compliance",
    "Organic Certification": "quality_compliance",
    "GlobalG.A.P. Certification": "quality_compliance",
    "HACCP Certification": "quality_compliance",
    "Warehouse Receipt": "trade_document",
    "Farm Location Evidence": "field_verification",
    "Field Visit Report": "field_verification",
    "Verification Checklist": "field_verification",
    "Offtake Agreement": "trade_document",
    "Invoice Record": "trade_document",
    "Delivery Note": "trade_document",
}

DOCUMENT_TYPE_NAMES = [
    "National ID",
    "NIN Confirmation",
    "BVN Confirmation",
    "CAC Certificate",
    "Tax Identification Number",
    "Cooperative Registration Certificate",
    "Export Registration Certificate",
    "NEPC Registration",
    "Phytosanitary Certificate",
    "Quality Inspection Certificate",
    "Certificate of Origin",
    "Organic Certification",
    "GlobalG.A.P. Certification",
    "HACCP Certification",
    "Warehouse Receipt",
    "Farm Location Evidence",
    "Field Visit Report",
    "Verification Checklist",
    "Offtake Agreement",
    "Invoice Record",
    "Delivery Note",
    "Bank Account Confirmation",
]

REFERENCE_OPTIONS = {
    "actor_status": [
        ("active", "Active"),
        ("inactive", "Inactive"),
        ("suspended", "Suspended"),
        ("archived", "Archived"),
        ("pending_review", "Pending Review"),
    ],
    "registration_status": [
        ("registered", "Registered"),
        ("unregistered", "Unregistered"),
        ("pending_registration", "Pending Registration"),
        ("expired_registration", "Expired Registration"),
        ("not_applicable", "Not Applicable"),
        ("unknown", "Unknown"),
    ],
    "source_reference_type": [
        ("partner_field_report", "Partner Field Report"),
        ("government_registry", "Government Registry"),
        ("export_permit", "Export Permit"),
        ("cooperative_register", "Cooperative Register"),
        ("inspection_report", "Inspection Report"),
        ("manual_entry", "Manual Entry"),
        ("spreadsheet_import", "Spreadsheet Import"),
        ("other", "Other"),
    ],
    "contact_role": [
        ("owner", "Owner"),
        ("managing_director", "Managing Director"),
        ("operations_manager", "Operations Manager"),
        ("export_manager", "Export Manager"),
        ("farm_manager", "Farm Manager"),
        ("cooperative_lead", "Cooperative Lead"),
        ("warehouse_contact", "Warehouse Contact"),
        ("finance_contact", "Finance Contact"),
        ("compliance_contact", "Compliance Contact"),
        ("other", "Other"),
    ],
    "capacity_unit": [
        ("mt_month", "MT/month"),
        ("mt_year", "MT/year"),
        ("kg_week", "KG/week"),
        ("kg_month", "KG/month"),
        ("bags_month", "bags/month"),
        ("bags_year", "bags/year"),
        ("containers_month", "containers/month"),
        ("containers_year", "containers/year"),
        ("hectares", "hectares"),
        ("tonnes", "tonnes"),
        ("other", "Other"),
    ],
    "certification_verification_status": [
        ("unverified", "Unverified"),
        ("submitted", "Submitted"),
        ("verified", "Verified"),
        ("expired", "Expired"),
        ("rejected", "Rejected"),
        ("superseded", "Superseded"),
    ],
    "certification_status": [
        ("active", "Active"),
        ("expired", "Expired"),
        ("revoked", "Revoked"),
        ("suspended", "Suspended"),
        ("pending", "Pending"),
        ("unknown", "Unknown"),
    ],
    "constraint_category": [
        ("logistics", "Logistics"),
        ("finance", "Finance"),
        ("infrastructure", "Infrastructure"),
        ("documentation", "Documentation"),
        ("regulatory_compliance", "Regulatory Compliance"),
        ("quality_control", "Quality Control"),
        ("storage_warehousing", "Storage / Warehousing"),
        ("processing_capacity", "Processing Capacity"),
        ("power_energy", "Power / Energy"),
        ("security", "Security"),
        ("market_access", "Market Access"),
        ("input_supply", "Input Supply"),
        ("labour", "Labour"),
        ("weather_climate", "Weather / Climate"),
        ("other", "Other"),
    ],
    "constraint_severity": [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("critical", "Critical"),
    ],
    "constraint_status": [
        ("active", "Active"),
        ("resolved", "Resolved"),
        ("monitoring", "Monitoring"),
        ("deferred", "Deferred"),
        ("not_applicable", "Not Applicable"),
    ],
}


def make_code(name):
    return name.lower().replace(".", "").replace("&", "and").replace("/", " ").replace("-", " ").replace(" ", "_")


def seed_reference_data():
    for region_data in REFERENCE_REGIONS:
        region = Region.query.filter_by(code=region_data["code"]).first()
        if region:
            region.name = region_data["name"]
            region.country = "Nigeria"
            region.active = True
        else:
            db.session.add(Region(**region_data))

    for crop_data in REFERENCE_CROPS:
        crop = Crop.query.filter_by(code=crop_data["code"]).first()
        if crop:
            crop.name = crop_data["name"]
            crop.active = True
        else:
            db.session.add(Crop(**crop_data))

    db.session.commit()


def seed_document_types():
    for name in DOCUMENT_TYPE_NAMES:
        sensitive = name in SENSITIVE_DOCUMENT_TYPE_NAMES
        code = make_code(name)
        visibility = "hidden" if sensitive else "metadata_only"
        category = DOCUMENT_TYPE_CATEGORIES.get(name, "general")
        requires_expiry_date = name in DOCUMENT_TYPES_REQUIRING_EXPIRY
        requires_issuing_body = name in DOCUMENT_TYPES_REQUIRING_ISSUING_BODY
        requires_reference_number = name in DOCUMENT_TYPES_REQUIRING_REFERENCE_NUMBER
        applies_to_actor_types = [
            "farmer",
            "aggregator",
            "exporter",
            "cooperative",
            "processor",
            "buyer",
            "logistics_provider",
        ]

        document_type = DocumentType.query.filter_by(code=code).first()
        if document_type:
            document_type.name = name
            document_type.category = category
            document_type.sensitive = sensitive
            document_type.applies_to_actor_types = applies_to_actor_types
            document_type.requires_expiry_date = requires_expiry_date
            document_type.requires_issuing_body = requires_issuing_body
            document_type.requires_reference_number = requires_reference_number
            document_type.default_visibility_level = visibility
            document_type.default_verification_status = "unverified"
            document_type.active = True
        else:
            db.session.add(DocumentType(
                code=code,
                name=name,
                category=category,
                sensitive=sensitive,
                applies_to_actor_types=applies_to_actor_types,
                requires_expiry_date=requires_expiry_date,
                requires_issuing_body=requires_issuing_body,
                requires_reference_number=requires_reference_number,
                default_visibility_level=visibility,
                default_verification_status="unverified",
                active=True
            ))

    db.session.commit()


def migrate_phase_2_1_tables():
    """Add small Phase 2.1 columns to existing databases without a migration framework."""
    from sqlalchemy import inspect, text

    try:
        inspector = inspect(db.engine)
        if "market_actors" not in inspector.get_table_names():
            return
        market_actor_columns = {column["name"] for column in inspector.get_columns("market_actors")}
        if "source_reference_type" not in market_actor_columns:
            db.session.execute(text("ALTER TABLE market_actors ADD COLUMN source_reference_type VARCHAR(80)"))
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Phase 2.1 migration warning: {e}")


def seed_reference_options():
    for category, options in REFERENCE_OPTIONS.items():
        for sort_order, (code, label) in enumerate(options, start=1):
            option = ReferenceOption.query.filter_by(category=category, code=code).first()
            if option:
                option.label = label
                option.sort_order = sort_order
            else:
                db.session.add(ReferenceOption(
                    category=category,
                    code=code,
                    label=label,
                    sort_order=sort_order,
                    active=True,
                    is_default=sort_order == 1,
                ))

    db.session.commit()


with app.app_context():
    db.create_all()
    migrate_payment_plans_table()
    migrate_phase_2_1_tables()
    seed_payment_plans()
    seed_datasets()
    seed_licensed_packs()
    seed_reference_data()
    seed_document_types()
    seed_reference_options()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
