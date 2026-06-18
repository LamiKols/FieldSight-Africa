"""
Database models for Agricultural Intelligence Platform

This platform sells time-sensitive agricultural intelligence, not static directories.
Access expires because intelligence decays.

PRODUCT TYPES:
- Licensed Data Packs: One-off purchase, permanent snapshot ownership
- Live Market Intelligence: Sales-led annual access with monthly updates
- Subscriptions: Monthly access with region + crop scoping
"""

from datetime import datetime
import hashlib
import uuid
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

PARTNER_ROLES = [
    "partner_admin",
    "data_editor",
    "data_reviewer",
    "partner_viewer",
]

COMMON_STATUSES = [
    "active",
    "inactive",
    "suspended",
    "pending",
    "archived",
    "pending_review",
]

ACTOR_TYPES = [
    "farmer",
    "aggregator",
    "exporter",
    "cooperative",
    "processor",
    "buyer",
    "logistics_provider",
]

PARTNER_BATCH_STATUSES = [
    "draft",
    "submitted",
    "needs_correction",
    "approved",
    "rejected",
    "published",
    "archived",
]

PARTNER_DATASET_TYPES = [
    "actor_registry",
    "actor_activity_status",
    "market_changes",
    "crop_availability",
    "trust_index",
]

DOCUMENT_STATUSES = [
    "draft",
    "submitted",
    "needs_correction",
    "approved",
    "rejected",
    "expired",
    "superseded",
    "archived",
]

DOCUMENT_VERIFICATION_STATUSES = [
    "unverified",
    "submitted",
    "verified",
    "expired",
    "rejected",
    "superseded",
]

DOCUMENT_VISIBILITY_LEVELS = [
    "hidden",
    "metadata_only",
    "redacted_document",
    "full_document",
]

DOCUMENT_EXTRACTION_STATUSES = [
    "pending",
    "completed",
    "failed",
    "needs_review",
]

DOCUMENT_EXTRACTOR_TYPES = [
    "manual",
    "template",
    "pdf_text",
    "ocr_placeholder",
    "ai_placeholder",
]

DOCUMENT_INTELLIGENCE_STATUSES = [
    "not_started",
    "extracted",
    "needs_reconciliation",
    "reconciled",
    "failed",
]

DOCUMENT_RECONCILIATION_STATUSES = [
    "pending",
    "accepted",
    "rejected",
    "manually_overridden",
]

DOCUMENT_REDACTION_STATUSES = [
    "not_redacted",
    "redaction_required",
    "not_required",
    "required",
    "in_progress",
    "completed",
    "waived",
    "failed",
]

DOCUMENT_PUBLISH_TARGETS = [
    "verified_metadata",
    "licensed_data_pack_metadata",
    "live_intelligence_metadata",
    "subscriber_portal_metadata",
    "api_metadata",
    "redacted_document_candidate",
    "full_document_restricted_candidate",
]

DOCUMENT_PUBLISH_CONTROL_STATUSES = [
    "not_evaluated",
    "blocked",
    "ready",
    "waived",
]

DOCUMENT_ACCESS_REQUEST_TYPES = [
    "redacted_document",
    "full_document_restricted",
]

DOCUMENT_ACCESS_REQUEST_STATUSES = [
    "pending",
    "in_review",
    "needs_information",
    "approved_for_redacted_access",
    "approved",
    "rejected",
    "closed",
    "cancelled",
]

DOCUMENT_ACCESS_FULFILMENT_ACTION_TYPES = [
    "redacted_access_recorded",
    "restricted_full_document_review_recorded",
    "manual_note",
]

COMMERCIAL_REQUEST_TYPES = [
    "live_intelligence",
    "api_access",
    "upgrade",
]

COMMERCIAL_REQUEST_STATUSES = [
    "pending",
    "in_review",
    "contacted",
    "approved_for_fulfilment",
    "rejected",
    "closed",
    "cancelled",
]

COMMERCIAL_FULFILMENT_ACTION_TYPES = [
    "api_client_setup",
    "live_intelligence_access",
    "upgrade_followup",
    "manual_note",
]

CONSENT_STATUSES = [
    "not_requested",
    "requested",
    "granted",
    "refused",
    "withdrawn",
    "expired",
]

CONSENT_METHODS = [
    "written",
    "digital_checkbox",
    "uploaded_form",
    "email_confirmation",
    "verbal_pending_written_confirmation",
    "partner_attestation",
]

CONSENT_REVIEW_STATUSES = [
    "pending_review",
    "accepted",
    "rejected",
    "needs_correction",
]

CONSENT_SCOPE_OPTIONS = [
    ("store_actor_profile_data", "Store actor profile data internally"),
    ("store_actor_documents", "Store actor documents internally"),
    ("use_actor_data_for_verification", "Use actor data for verification/review"),
    ("share_basic_profile_with_subscribers", "Share basic actor profile with subscribers"),
    ("share_restricted_contact_with_approved_users", "Share restricted contact data with approved users only"),
    ("share_document_metadata_with_subscribers", "Share document metadata with subscribers"),
    ("share_redacted_documents_with_subscribers", "Share redacted documents with subscribers"),
    ("share_full_documents_with_approved_users", "Share full documents with approved users only"),
    ("include_in_paid_data_packs", "Include actor in paid data packs"),
    ("include_in_live_intelligence", "Include actor in live intelligence reports"),
    ("include_in_api_responses", "Include actor in API responses"),
    ("use_documents_for_extraction_quality", "Use uploaded documents for extraction/data quality checks"),
]

CONSENT_DATA_CATEGORY_OPTIONS = [
    ("identity_profile", "Identity profile"),
    ("location", "Location"),
    ("crop_commodity", "Crop/commodity"),
    ("export_profile", "Export profile"),
    ("certification_metadata", "Certification metadata"),
    ("operational_constraints", "Operational constraints"),
    ("contact_details", "Contact details"),
]

CONSENT_DOCUMENT_CATEGORY_OPTIONS = [
    ("public_compliance_document", "Public compliance document"),
    ("export_compliance_document", "Export compliance document"),
    ("company_registration_document", "Company registration document"),
    ("identity_document", "Identity document"),
    ("financial_document", "Financial document"),
    ("transaction_document", "Transaction document"),
    ("logistics_document", "Logistics document"),
    ("other", "Other"),
]

CONSENT_SHARING_CHANNEL_OPTIONS = [
    ("internal_review", "Internal review"),
    ("partner_portal", "Partner portal"),
    ("admin_review", "Admin review"),
    ("licensed_data_pack", "Licensed data pack"),
    ("live_intelligence", "Live intelligence"),
    ("subscriber_portal", "Subscriber portal"),
    ("api", "API"),
    ("approved_buyer_due_diligence", "Approved buyer due diligence"),
]

DOCUMENT_TYPE_CONSENT_CATEGORY_MAP = {
    "identity": "identity_document",
    "financial_identity": "financial_document",
    "business_registration": "company_registration_document",
    "export_compliance": "export_compliance_document",
    "quality_compliance": "public_compliance_document",
    "trade_document": "transaction_document",
    "field_verification": "other",
}

REFERENCE_OPTION_CATEGORIES = [
    "actor_status",
    "registration_status",
    "source_reference_type",
    "contact_role",
    "capacity_unit",
    "certification_verification_status",
    "certification_status",
    "constraint_category",
    "constraint_severity",
    "constraint_status",
]

NIGERIA_REGIONS = {
    "SW": "South West",
    "SE": "South East",
    "SS": "South South",
    "NC": "North Central",
    "NW": "North West",
    "NE": "North East"
}

NIGERIA_STATE_REGION_MAP = {
    "Lagos": "SW", "Ogun": "SW", "Oyo": "SW", "Osun": "SW", "Ondo": "SW", "Ekiti": "SW",
    "Abia": "SE", "Anambra": "SE", "Ebonyi": "SE", "Enugu": "SE", "Imo": "SE",
    "Akwa Ibom": "SS", "Bayelsa": "SS", "Cross River": "SS",
    "Delta": "SS", "Edo": "SS", "Rivers": "SS",
    "Benue": "NC", "Kogi": "NC", "Kwara": "NC", "Nasarawa": "NC",
    "Niger": "NC", "Plateau": "NC", "FCT": "NC", "Abuja": "NC",
    "Kaduna": "NW", "Kano": "NW", "Katsina": "NW",
    "Kebbi": "NW", "Jigawa": "NW", "Sokoto": "NW", "Zamfara": "NW",
    "Adamawa": "NE", "Bauchi": "NE", "Borno": "NE",
    "Gombe": "NE", "Taraba": "NE", "Yobe": "NE"
}


def get_region_from_state(state_name):
    """Map a state name to its region code. Returns None if not found."""
    if not state_name:
        return None
    normalized = state_name.strip().title()
    return NIGERIA_STATE_REGION_MAP.get(normalized)


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default='subscriber')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    subscriptions = db.relationship('Subscription', backref='user', lazy=True)
    export_logs = db.relationship('ExportLog', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        return self.role == 'admin'

    def get_active_subscription(self):
        from datetime import datetime
        for sub in self.subscriptions:
            if sub.status == 'active' and sub.current_period_end > datetime.utcnow():
                return sub
        return None

    def get_plan(self):
        sub = self.get_active_subscription()
        if sub:
            return PaymentPlan.query.filter_by(code=sub.plan_code).first()
        return None

    def can_access_dataset(self, dataset_code):
        plan = self.get_plan()
        if not plan:
            return False
        return dataset_code in plan.allowed_datasets

    def get_monthly_exports(self):
        from datetime import datetime
        current_month = datetime.utcnow().strftime('%Y-%m')
        total = db.session.query(db.func.sum(ExportLog.rows_exported)).filter(
            ExportLog.user_id == self.id,
            db.func.to_char(ExportLog.exported_at, 'YYYY-MM') == current_month
        ).scalar()
        return total or 0

    def can_export(self, rows_count):
        plan = self.get_plan()
        if not plan:
            return False
        current_exports = self.get_monthly_exports()
        return (current_exports + rows_count) <= plan.monthly_export_limit


class Subscription(db.Model):
    __tablename__ = 'subscriptions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    provider = db.Column(db.String(20), nullable=False)
    provider_subscription_id = db.Column(db.String(255), nullable=False)
    plan_code = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default='active')
    current_period_end = db.Column(db.DateTime, nullable=False)
    regions_selected = db.Column(db.JSON, default=list)
    crops_selected = db.Column(db.JSON, default=list)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class PaymentPlan(db.Model):
    __tablename__ = 'payment_plans'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    stripe_price_id = db.Column(db.String(255))
    paystack_plan_code = db.Column(db.String(255))
    monthly_export_limit = db.Column(db.Integer, nullable=False)
    allowed_datasets = db.Column(db.JSON, nullable=False)
    regions_allowed = db.Column(db.Integer, default=1)
    crops_allowed = db.Column(db.Integer, default=6)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Dataset(db.Model):
    __tablename__ = 'datasets'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)

    months = db.relationship('DatasetMonth', backref='dataset', lazy=True)


class DatasetMonth(db.Model):
    __tablename__ = 'dataset_months'

    id = db.Column(db.Integer, primary_key=True)
    dataset_id = db.Column(db.Integer, db.ForeignKey('datasets.id'), nullable=False)
    month = db.Column(db.String(7), nullable=False)
    published = db.Column(db.Boolean, default=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    records = db.relationship('DatasetRecord', backref='dataset_month', lazy=True, cascade='all, delete-orphan')

    __table_args__ = (db.UniqueConstraint('dataset_id', 'month', name='unique_dataset_month'),)


class DatasetRecord(db.Model):
    __tablename__ = 'dataset_records'

    id = db.Column(db.Integer, primary_key=True)
    dataset_month_id = db.Column(db.Integer, db.ForeignKey('dataset_months.id'), nullable=False)
    record_json = db.Column(db.JSON, nullable=False)


class ExportLog(db.Model):
    __tablename__ = 'export_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    dataset_month_id = db.Column(db.Integer, db.ForeignKey('dataset_months.id'), nullable=False)
    rows_exported = db.Column(db.Integer, nullable=False)
    exported_at = db.Column(db.DateTime, default=datetime.utcnow)

    dataset_month = db.relationship('DatasetMonth', backref='export_logs')


class ViewLog(db.Model):
    __tablename__ = 'view_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    dataset_month_id = db.Column(db.Integer, db.ForeignKey('dataset_months.id'), nullable=False)
    viewed_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='view_logs')
    dataset_month = db.relationship('DatasetMonth', backref='view_logs')


class LicensedPack(db.Model):
    __tablename__ = 'licensed_packs'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    regions_allowed = db.Column(db.Integer, nullable=False)
    crops_allowed = db.Column(db.Integer, nullable=True)
    price_usd = db.Column(db.Integer, nullable=False)
    price_ngn = db.Column(db.Integer, nullable=False)
    stripe_price_id = db.Column(db.String(255))
    stripe_payment_link = db.Column(db.String(255))
    paystack_plan_code = db.Column(db.String(255))
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    licenses = db.relationship('License', backref='licensed_pack', lazy=True)


class License(db.Model):
    __tablename__ = 'licenses'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    licensed_pack_id = db.Column(db.Integer, db.ForeignKey('licensed_packs.id'), nullable=False)
    regions_selected = db.Column(db.JSON, nullable=False)
    crops_selected = db.Column(db.JSON, nullable=False)
    snapshot_month = db.Column(db.String(7), nullable=False)
    status = db.Column(db.String(20), default='active')
    stripe_payment_intent_id = db.Column(db.String(255))
    paystack_reference = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='licenses')


class LiveIntelligenceAccess(db.Model):
    __tablename__ = 'live_intelligence_access'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    regions_allowed = db.Column(db.Integer, nullable=False)
    crops_allowed = db.Column(db.Integer, nullable=True)
    regions_selected = db.Column(db.JSON, nullable=False)
    crops_selected = db.Column(db.JSON, nullable=False)
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)
    active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='live_intelligence_access')

    def is_valid(self):
        now = datetime.utcnow()
        return self.active and self.start_date <= now <= self.end_date


class Payment(db.Model):
    __tablename__ = 'payments'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    provider = db.Column(db.String(20), nullable=False)
    provider_reference = db.Column(db.String(255), nullable=False)
    payment_type = db.Column(db.String(50), nullable=False)
    amount_usd = db.Column(db.Integer)
    amount_ngn = db.Column(db.Integer)
    status = db.Column(db.String(20), default='pending')
    metadata_json = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='payments')


class PartnerOrganization(TimestampMixin, db.Model):
    __tablename__ = 'partner_organizations'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    slug = db.Column(db.String(120), unique=True, nullable=False)
    description = db.Column(db.Text)
    contact_name = db.Column(db.String(120))
    contact_email = db.Column(db.String(120))
    contact_phone = db.Column(db.String(50))
    country = db.Column(db.String(80), default='Nigeria')
    status = db.Column(db.String(20), default='pending')

    user_profiles = db.relationship('PartnerUserProfile', backref='partner_organization', lazy=True)
    actors = db.relationship('MarketActor', backref='partner_organization', lazy=True)
    update_batches = db.relationship('PartnerUpdateBatch', backref='partner_organization', lazy=True)


class PartnerUserProfile(TimestampMixin, db.Model):
    __tablename__ = 'partner_user_profiles'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    partner_organization_id = db.Column(db.Integer, db.ForeignKey('partner_organizations.id'), nullable=False)
    partner_role = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default='pending')

    user = db.relationship('User', backref='partner_profiles')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'partner_organization_id', name='unique_partner_user_profile'),
    )


class Region(TimestampMixin, db.Model):
    __tablename__ = 'regions'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), unique=True, nullable=False)
    country = db.Column(db.String(80), default='Nigeria')
    active = db.Column(db.Boolean, default=True)

    states = db.relationship('State', backref='region', lazy=True)


class State(TimestampMixin, db.Model):
    __tablename__ = 'states'

    id = db.Column(db.Integer, primary_key=True)
    region_id = db.Column(db.Integer, db.ForeignKey('regions.id'), nullable=False)
    code = db.Column(db.String(20), unique=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    active = db.Column(db.Boolean, default=True)

    lgas = db.relationship('LGA', backref='state', lazy=True)


class LGA(TimestampMixin, db.Model):
    __tablename__ = 'lgas'

    id = db.Column(db.Integer, primary_key=True)
    state_id = db.Column(db.Integer, db.ForeignKey('states.id'), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    active = db.Column(db.Boolean, default=True)

    __table_args__ = (
        db.UniqueConstraint('state_id', 'name', name='unique_state_lga'),
    )


class Crop(TimestampMixin, db.Model):
    __tablename__ = 'crops'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), unique=True, nullable=False)
    active = db.Column(db.Boolean, default=True)

    commodities = db.relationship('Commodity', backref='crop', lazy=True)


class Commodity(TimestampMixin, db.Model):
    __tablename__ = 'commodities'

    id = db.Column(db.Integer, primary_key=True)
    crop_id = db.Column(db.Integer, db.ForeignKey('crops.id'))
    code = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(120), unique=True, nullable=False)
    category = db.Column(db.String(120))
    active = db.Column(db.Boolean, default=True)


class Port(TimestampMixin, db.Model):
    __tablename__ = 'ports'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    country = db.Column(db.String(80), default='Nigeria')
    active = db.Column(db.Boolean, default=True)


class TradeDestination(TimestampMixin, db.Model):
    __tablename__ = 'trade_destinations'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    country = db.Column(db.String(80))
    region = db.Column(db.String(80))
    active = db.Column(db.Boolean, default=True)


class CertificationType(TimestampMixin, db.Model):
    __tablename__ = 'certification_types'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(150), unique=True, nullable=False)
    description = db.Column(db.Text)
    active = db.Column(db.Boolean, default=True)


class ReferenceOption(TimestampMixin, db.Model):
    __tablename__ = 'reference_options'

    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(80), nullable=False)
    code = db.Column(db.String(80), nullable=False)
    label = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    sort_order = db.Column(db.Integer, default=0)
    active = db.Column(db.Boolean, default=True)
    is_default = db.Column(db.Boolean, default=False)
    metadata_json = db.Column(db.JSON)

    __table_args__ = (
        db.UniqueConstraint('category', 'code', name='unique_reference_option_category_code'),
    )


class MarketActor(TimestampMixin, db.Model):
    __tablename__ = 'market_actors'

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    partner_organization_id = db.Column(db.Integer, db.ForeignKey('partner_organizations.id'), nullable=False)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    updated_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    actor_type = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(180), nullable=False)
    crop_id = db.Column(db.Integer, db.ForeignKey('crops.id'))
    commodity_id = db.Column(db.Integer, db.ForeignKey('commodities.id'))
    commodity_category = db.Column(db.String(120))
    registration_status = db.Column(db.String(80))
    date_of_registration = db.Column(db.Date)
    status = db.Column(db.String(20), default='active')
    source_reference_type = db.Column(db.String(80))
    source_reference = db.Column(db.String(120))
    metadata_json = db.Column(db.JSON)
    archived_at = db.Column(db.DateTime)

    created_by_user = db.relationship('User', foreign_keys=[created_by_user_id], backref='created_market_actors')
    updated_by_user = db.relationship('User', foreign_keys=[updated_by_id], backref='updated_market_actors')
    crop = db.relationship('Crop', backref='market_actors')
    commodity = db.relationship('Commodity', backref='market_actors')
    location = db.relationship('ActorLocation', backref='market_actor', uselist=False)
    contacts = db.relationship('ActorContact', backref='market_actor', lazy=True)
    export_profile = db.relationship('ActorExportProfile', backref='market_actor', uselist=False)
    certifications = db.relationship('ActorCertification', backref='market_actor', lazy=True)
    constraints = db.relationship('ActorConstraint', backref='market_actor', lazy=True)


class ActorLocation(TimestampMixin, db.Model):
    __tablename__ = 'actor_locations'

    id = db.Column(db.Integer, primary_key=True)
    market_actor_id = db.Column(db.Integer, db.ForeignKey('market_actors.id'), nullable=False)
    location = db.Column(db.String(255))
    location_text = db.Column(db.String(255))
    region_id = db.Column(db.Integer, db.ForeignKey('regions.id'))
    state_id = db.Column(db.Integer, db.ForeignKey('states.id'))
    state_name = db.Column(db.String(100))
    lga_id = db.Column(db.Integer, db.ForeignKey('lgas.id'))
    lga_name = db.Column(db.String(120))
    country = db.Column(db.String(80), default='Nigeria')
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    is_primary = db.Column(db.Boolean, default=True)

    region = db.relationship('Region', backref='actor_locations')
    state = db.relationship('State', backref='actor_locations')
    lga = db.relationship('LGA', backref='actor_locations')


class ActorContact(TimestampMixin, db.Model):
    __tablename__ = 'actor_contacts'

    id = db.Column(db.Integer, primary_key=True)
    market_actor_id = db.Column(db.Integer, db.ForeignKey('market_actors.id'), nullable=False)
    contact_role = db.Column(db.String(80))
    contact_name = db.Column(db.String(120))
    phone = db.Column(db.String(50))
    email = db.Column(db.String(120))
    restricted = db.Column(db.Boolean, default=True)
    visibility_level = db.Column(db.String(50), default='hidden')
    is_primary = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text)


class ActorExportProfile(TimestampMixin, db.Model):
    __tablename__ = 'actor_export_profiles'

    id = db.Column(db.Integer, primary_key=True)
    market_actor_id = db.Column(db.Integer, db.ForeignKey('market_actors.id'), nullable=False)
    years_in_export_trade = db.Column(db.Integer)
    trade_destination_id = db.Column(db.Integer, db.ForeignKey('trade_destinations.id'))
    trade_destination_name = db.Column(db.String(120))
    export_capacity = db.Column(db.String(120))
    export_capacity_unit = db.Column(db.String(50))
    port_id = db.Column(db.Integer, db.ForeignKey('ports.id'))
    port_of_exit = db.Column(db.String(120))
    notes = db.Column(db.Text)

    trade_destination = db.relationship('TradeDestination', backref='actor_export_profiles')
    port = db.relationship('Port', backref='actor_export_profiles')


class ActorCertification(TimestampMixin, db.Model):
    __tablename__ = 'actor_certifications'

    id = db.Column(db.Integer, primary_key=True)
    market_actor_id = db.Column(db.Integer, db.ForeignKey('market_actors.id'), nullable=False)
    certification_type_id = db.Column(db.Integer, db.ForeignKey('certification_types.id'))
    certification_name = db.Column(db.String(150))
    certificate_number = db.Column(db.String(120))
    reference_number = db.Column(db.String(120))
    issuing_body = db.Column(db.String(180))
    verification_status = db.Column(db.String(50), default='unverified')
    status = db.Column(db.String(50), default='active')
    issued_at = db.Column(db.Date)
    expires_at = db.Column(db.Date)
    notes = db.Column(db.Text)

    certification_type = db.relationship('CertificationType', backref='actor_certifications')


class ActorConstraint(TimestampMixin, db.Model):
    __tablename__ = 'actor_constraints'

    id = db.Column(db.Integer, primary_key=True)
    market_actor_id = db.Column(db.Integer, db.ForeignKey('market_actors.id'), nullable=False)
    constraint_category = db.Column(db.String(120))
    constraint_text = db.Column(db.Text, nullable=False)
    severity = db.Column(db.String(50))
    status = db.Column(db.String(50), default='active')


class PartnerUpdateBatch(TimestampMixin, db.Model):
    __tablename__ = 'partner_update_batches'

    id = db.Column(db.Integer, primary_key=True)
    partner_organization_id = db.Column(db.Integer, db.ForeignKey('partner_organizations.id'), nullable=False)
    title = db.Column(db.String(180))
    submitted_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    reviewed_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    dataset_type = db.Column(db.String(80), nullable=False)
    reporting_month = db.Column(db.String(7))
    status = db.Column(db.String(50), default='draft')
    notes = db.Column(db.Text)
    review_comments = db.Column(db.Text)
    submitted_at = db.Column(db.DateTime)
    reviewed_at = db.Column(db.DateTime)
    approved_at = db.Column(db.DateTime)
    published_at = db.Column(db.DateTime)
    published_dataset_month_id = db.Column(db.Integer, db.ForeignKey('dataset_months.id'))

    submitted_by_user = db.relationship('User', foreign_keys=[submitted_by_user_id], backref='submitted_partner_batches')
    reviewed_by_user = db.relationship('User', foreign_keys=[reviewed_by_user_id], backref='reviewed_partner_batches')
    published_dataset_month = db.relationship('DatasetMonth', backref='partner_update_batches')
    record_changes = db.relationship('PartnerRecordChange', backref='partner_update_batch', lazy=True)
    reviews = db.relationship('PartnerSubmissionReview', backref='partner_update_batch', lazy=True)


class PartnerRecordChange(TimestampMixin, db.Model):
    __tablename__ = 'partner_record_changes'

    id = db.Column(db.Integer, primary_key=True)
    partner_update_batch_id = db.Column(db.Integer, db.ForeignKey('partner_update_batches.id'), nullable=False)
    market_actor_id = db.Column(db.Integer, db.ForeignKey('market_actors.id'))
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    entity_type = db.Column(db.String(80), nullable=False)
    entity_id = db.Column(db.Integer)
    change_type = db.Column(db.String(50), nullable=False)
    before_values = db.Column(db.JSON)
    after_values = db.Column(db.JSON)
    status = db.Column(db.String(50), default='draft')

    market_actor = db.relationship('MarketActor', backref='partner_record_changes')
    created_by_user = db.relationship('User', backref='created_partner_record_changes')


class PartnerSubmissionReview(TimestampMixin, db.Model):
    __tablename__ = 'partner_submission_reviews'

    id = db.Column(db.Integer, primary_key=True)
    partner_update_batch_id = db.Column(db.Integer, db.ForeignKey('partner_update_batches.id'), nullable=False)
    reviewer_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(50), nullable=False)
    notes = db.Column(db.Text)
    reviewed_at = db.Column(db.DateTime, default=datetime.utcnow)

    reviewer_user = db.relationship('User', backref='partner_submission_reviews')


class DocumentType(TimestampMixin, db.Model):
    __tablename__ = 'document_types'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(80), unique=True, nullable=False)
    name = db.Column(db.String(180), unique=True, nullable=False)
    category = db.Column(db.String(100))
    description = db.Column(db.Text)
    sensitive = db.Column(db.Boolean, default=False)
    applies_to_actor_types = db.Column(db.JSON, default=list)
    requires_expiry_date = db.Column(db.Boolean, default=False)
    requires_issuing_body = db.Column(db.Boolean, default=False)
    requires_reference_number = db.Column(db.Boolean, default=False)
    default_visibility_level = db.Column(db.String(50), default='metadata_only')
    default_verification_status = db.Column(db.String(50), default='unverified')
    active = db.Column(db.Boolean, default=True)

    documents = db.relationship('ActorDocument', backref='document_type', lazy=True)


class ActorDocument(TimestampMixin, db.Model):
    __tablename__ = 'actor_documents'

    id = db.Column(db.Integer, primary_key=True)
    market_actor_id = db.Column(db.Integer, db.ForeignKey('market_actors.id'), nullable=False)
    partner_organization_id = db.Column(db.Integer, db.ForeignKey('partner_organizations.id'), nullable=False)
    document_type_id = db.Column(db.Integer, db.ForeignKey('document_types.id'), nullable=False)
    uploaded_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text)
    original_filename = db.Column(db.String(255))
    stored_filename = db.Column(db.String(255))
    storage_path = db.Column(db.String(500))
    mime_type = db.Column(db.String(120))
    file_size = db.Column(db.Integer)
    file_hash = db.Column(db.String(64))
    version_number = db.Column(db.Integer, default=1)
    document_reference_number = db.Column(db.String(120))
    issuing_body = db.Column(db.String(180))
    linked_crop_id = db.Column(db.Integer, db.ForeignKey('crops.id'))
    linked_commodity_id = db.Column(db.Integer, db.ForeignKey('commodities.id'))
    document_status = db.Column(db.String(50), default='draft')
    verification_status = db.Column(db.String(50), default='unverified')
    redaction_status = db.Column(db.String(50), default='not_redacted')
    subscriber_access_level = db.Column(db.String(50), default='metadata_only')
    review_status = db.Column(db.String(50), default='pending')
    reviewed_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    reviewed_at = db.Column(db.DateTime)
    review_comments = db.Column(db.Text)
    visibility_level = db.Column(db.String(50), default='metadata_only')
    issued_at = db.Column(db.Date)
    expires_at = db.Column(db.Date)
    is_current_version = db.Column(db.Boolean, default=True)
    archived_at = db.Column(db.DateTime)
    metadata_json = db.Column(db.JSON)

    market_actor = db.relationship('MarketActor', backref='documents')
    partner_organization = db.relationship('PartnerOrganization', backref='documents')
    uploaded_by_user = db.relationship('User', foreign_keys=[uploaded_by_user_id], backref='uploaded_actor_documents')
    reviewed_by_user = db.relationship('User', foreign_keys=[reviewed_by_user_id], backref='reviewed_actor_documents')
    linked_crop = db.relationship('Crop', backref='actor_documents')
    linked_commodity = db.relationship('Commodity', backref='actor_documents')
    versions = db.relationship('ActorDocumentVersion', backref='actor_document', lazy=True)


class ActorDocumentVersion(db.Model):
    __tablename__ = 'actor_document_versions'

    id = db.Column(db.Integer, primary_key=True)
    actor_document_id = db.Column(db.Integer, db.ForeignKey('actor_documents.id'), nullable=False)
    version_number = db.Column(db.Integer, nullable=False)
    storage_backend = db.Column(db.String(50), default='local_private')
    storage_path = db.Column(db.String(500), nullable=False)
    original_filename = db.Column(db.String(255))
    content_type = db.Column(db.String(120))
    file_size_bytes = db.Column(db.Integer)
    checksum_sha256 = db.Column(db.String(64))
    uploaded_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    document_status = db.Column(db.String(50), default='draft')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    uploaded_by_user = db.relationship('User', backref='uploaded_document_versions')

    __table_args__ = (
        db.UniqueConstraint('actor_document_id', 'version_number', name='unique_document_version'),
    )


class DocumentExtractionRun(TimestampMixin, db.Model):
    __tablename__ = 'document_extraction_runs'

    id = db.Column(db.Integer, primary_key=True)
    actor_document_id = db.Column(db.Integer, db.ForeignKey('actor_documents.id'), nullable=False)
    actor_document_version_id = db.Column(db.Integer, db.ForeignKey('actor_document_versions.id'))
    status = db.Column(db.String(50), default='pending')
    extractor_type = db.Column(db.String(80), default='template')
    document_type_code = db.Column(db.String(80))
    template_profile_code = db.Column(db.String(120))
    source_filename = db.Column(db.String(255))
    extracted_fields_json = db.Column(db.JSON, default=dict)
    confidence_json = db.Column(db.JSON, default=dict)
    field_evidence_json = db.Column(db.JSON, default=dict)
    provenance_json = db.Column(db.JSON, default=dict)
    metadata_mismatches_json = db.Column(db.JSON, default=list)
    risk_flags_json = db.Column(db.JSON, default=list)
    expiry_renewal_json = db.Column(db.JSON, default=dict)
    quality_score = db.Column(db.Integer)
    document_intelligence_status = db.Column(db.String(80), default='not_started')
    manual_correction_notes = db.Column(db.Text)
    raw_text_excerpt = db.Column(db.Text)
    error_message = db.Column(db.Text)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    actor_document = db.relationship('ActorDocument', backref='extraction_runs')
    actor_document_version = db.relationship('ActorDocumentVersion', backref='extraction_runs')
    created_by_user = db.relationship('User', backref='document_extraction_runs')


class DocumentFieldReconciliation(TimestampMixin, db.Model):
    __tablename__ = 'document_field_reconciliations'

    id = db.Column(db.Integer, primary_key=True)
    actor_document_id = db.Column(db.Integer, db.ForeignKey('actor_documents.id'), nullable=False)
    extraction_run_id = db.Column(db.Integer, db.ForeignKey('document_extraction_runs.id'), nullable=False)
    field_name = db.Column(db.String(120), nullable=False)
    field_label = db.Column(db.String(180))
    current_value = db.Column(db.Text)
    extracted_value = db.Column(db.Text)
    accepted_value = db.Column(db.Text)
    confidence = db.Column(db.Float)
    status = db.Column(db.String(50), default='pending')
    evidence_json = db.Column(db.JSON, default=dict)
    provenance_json = db.Column(db.JSON, default=dict)
    risk_flags_json = db.Column(db.JSON, default=list)
    decision_history_json = db.Column(db.JSON, default=list)
    manual_correction_notes = db.Column(db.Text)
    reviewed_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    reviewed_at = db.Column(db.DateTime)

    actor_document = db.relationship('ActorDocument', backref='field_reconciliations')
    extraction_run = db.relationship('DocumentExtractionRun', backref='field_reconciliations')
    reviewed_by_user = db.relationship('User', backref='document_field_reconciliations')


class DocumentReview(TimestampMixin, db.Model):
    __tablename__ = 'document_reviews'

    id = db.Column(db.Integer, primary_key=True)
    actor_document_id = db.Column(db.Integer, db.ForeignKey('actor_documents.id'), nullable=False)
    actor_document_version_id = db.Column(db.Integer, db.ForeignKey('actor_document_versions.id'))
    reviewer_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(50), nullable=False)
    notes = db.Column(db.Text)
    reviewed_at = db.Column(db.DateTime, default=datetime.utcnow)

    actor_document = db.relationship('ActorDocument', backref='reviews')
    actor_document_version = db.relationship('ActorDocumentVersion', backref='reviews')
    reviewer_user = db.relationship('User', backref='document_reviews')


class DocumentPublishControl(TimestampMixin, db.Model):
    __tablename__ = 'document_publish_controls'

    id = db.Column(db.Integer, primary_key=True)
    actor_document_id = db.Column(db.Integer, db.ForeignKey('actor_documents.id'), nullable=False)
    publish_target = db.Column(db.String(80), nullable=False)
    status = db.Column(db.String(50), default='not_evaluated', nullable=False)
    readiness_checks_json = db.Column(db.JSON, default=list)
    blocking_reasons_json = db.Column(db.JSON, default=list)
    admin_decision = db.Column(db.String(80), default='not_evaluated')
    notes = db.Column(db.Text)
    decided_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    decided_at = db.Column(db.DateTime)
    last_evaluated_at = db.Column(db.DateTime)

    actor_document = db.relationship('ActorDocument', backref='publish_controls')
    decided_by_user = db.relationship('User', backref='document_publish_control_decisions')

    __table_args__ = (
        db.UniqueConstraint('actor_document_id', 'publish_target', name='unique_document_publish_control_target'),
    )


class DocumentAccessLog(db.Model):
    __tablename__ = 'document_access_logs'

    id = db.Column(db.Integer, primary_key=True)
    actor_document_id = db.Column(db.Integer, db.ForeignKey('actor_documents.id'), nullable=False)
    actor_document_version_id = db.Column(db.Integer, db.ForeignKey('actor_document_versions.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    api_client_id = db.Column(db.Integer, db.ForeignKey('api_clients.id'))
    access_type = db.Column(db.String(80), nullable=False)
    access_channel = db.Column(db.String(80))
    subscriber_organization_name = db.Column(db.String(180))
    visibility_level = db.Column(db.String(50), nullable=False)
    ip_address = db.Column(db.String(80))
    user_agent = db.Column(db.String(255))
    accessed_at = db.Column(db.DateTime, default=datetime.utcnow)

    actor_document = db.relationship('ActorDocument', backref='access_logs')
    actor_document_version = db.relationship('ActorDocumentVersion', backref='access_logs')
    user = db.relationship('User', backref='document_access_logs')
    api_client = db.relationship('ApiClient', backref='document_access_logs')


class DocumentEntitlement(TimestampMixin, db.Model):
    __tablename__ = 'document_entitlements'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    payment_plan_id = db.Column(db.Integer, db.ForeignKey('payment_plans.id'))
    licensed_pack_id = db.Column(db.Integer, db.ForeignKey('licensed_packs.id'))
    document_type_id = db.Column(db.Integer, db.ForeignKey('document_types.id'))
    access_scope = db.Column(db.String(80), default='metadata')
    visibility_level = db.Column(db.String(50), default='metadata_only')
    active = db.Column(db.Boolean, default=True)
    starts_at = db.Column(db.DateTime)
    ends_at = db.Column(db.DateTime)

    user = db.relationship('User', backref='document_entitlements')
    payment_plan = db.relationship('PaymentPlan', backref='document_entitlements')
    licensed_pack = db.relationship('LicensedPack', backref='document_entitlements')
    document_type = db.relationship('DocumentType', backref='document_entitlements')


class DocumentAccessRequest(TimestampMixin, db.Model):
    __tablename__ = 'document_access_requests'

    id = db.Column(db.Integer, primary_key=True)
    actor_document_id = db.Column(db.Integer, db.ForeignKey('actor_documents.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    api_client_id = db.Column(db.Integer, db.ForeignKey('api_clients.id'))
    request_type = db.Column(db.String(80), nullable=False)
    request_channel = db.Column(db.String(80), default='subscriber_portal')
    organization_name = db.Column(db.String(180))
    purpose = db.Column(db.Text)
    status = db.Column(db.String(50), default='pending')
    reviewed_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    reviewed_at = db.Column(db.DateTime)
    review_notes = db.Column(db.Text)

    actor_document = db.relationship('ActorDocument', backref='access_requests')
    user = db.relationship('User', foreign_keys=[user_id], backref='document_access_requests')
    api_client = db.relationship('ApiClient', backref='document_access_requests')
    reviewed_by_user = db.relationship('User', foreign_keys=[reviewed_by_user_id], backref='reviewed_document_access_requests')


class DocumentAccessFulfilmentAction(TimestampMixin, db.Model):
    __tablename__ = 'document_access_fulfilment_actions'

    id = db.Column(db.Integer, primary_key=True)
    document_access_request_id = db.Column(db.Integer, db.ForeignKey('document_access_requests.id'), nullable=False)
    action_type = db.Column(db.String(80), nullable=False)
    status = db.Column(db.String(50), default='recorded')
    visibility_level = db.Column(db.String(50), default='redacted_document_candidate')
    notes = db.Column(db.Text)
    performed_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    metadata_json = db.Column(db.JSON, default=dict)

    document_access_request = db.relationship('DocumentAccessRequest', backref='fulfilment_actions')
    performed_by_user = db.relationship('User', foreign_keys=[performed_by_user_id], backref='document_access_fulfilment_actions')


class CommercialRequest(TimestampMixin, db.Model):
    __tablename__ = 'commercial_requests'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    request_type = db.Column(db.String(80), nullable=False)
    organization_name = db.Column(db.String(180))
    contact_name = db.Column(db.String(120))
    contact_email = db.Column(db.String(120))
    requested_product = db.Column(db.String(120))
    dataset_code = db.Column(db.String(80))
    region_code = db.Column(db.String(20))
    crop_name = db.Column(db.String(120))
    message = db.Column(db.Text)
    context_json = db.Column(db.JSON, default=dict)
    status = db.Column(db.String(50), default='pending')
    reviewed_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    reviewed_at = db.Column(db.DateTime)
    review_notes = db.Column(db.Text)

    user = db.relationship('User', foreign_keys=[user_id], backref='commercial_requests')
    reviewed_by_user = db.relationship('User', foreign_keys=[reviewed_by_user_id], backref='reviewed_commercial_requests')


class CommercialFulfilmentAction(TimestampMixin, db.Model):
    __tablename__ = 'commercial_fulfilment_actions'

    id = db.Column(db.Integer, primary_key=True)
    commercial_request_id = db.Column(db.Integer, db.ForeignKey('commercial_requests.id'), nullable=False)
    action_type = db.Column(db.String(80), nullable=False)
    status = db.Column(db.String(50), default='recorded')
    notes = db.Column(db.Text)
    performed_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    resulting_api_client_id = db.Column(db.Integer, db.ForeignKey('api_clients.id'))
    resulting_live_intelligence_access_id = db.Column(db.Integer, db.ForeignKey('live_intelligence_access.id'))
    metadata_json = db.Column(db.JSON, default=dict)

    commercial_request = db.relationship('CommercialRequest', backref='fulfilment_actions')
    performed_by_user = db.relationship('User', foreign_keys=[performed_by_user_id], backref='commercial_fulfilment_actions')
    resulting_api_client = db.relationship('ApiClient', backref='commercial_fulfilment_actions')
    resulting_live_intelligence_access = db.relationship('LiveIntelligenceAccess', backref='commercial_fulfilment_actions')


class ActorConsentRecord(TimestampMixin, db.Model):
    __tablename__ = 'actor_consent_records'

    id = db.Column(db.Integer, primary_key=True)
    market_actor_id = db.Column(db.Integer, db.ForeignKey('market_actors.id'), nullable=False)
    partner_organization_id = db.Column(db.Integer, db.ForeignKey('partner_organizations.id'), nullable=False)
    consent_status = db.Column(db.String(50), default='not_requested', nullable=False)
    consent_scope_json = db.Column(db.JSON, default=list)
    permitted_data_categories_json = db.Column(db.JSON, default=list)
    permitted_document_categories_json = db.Column(db.JSON, default=list)
    sharing_channels_json = db.Column(db.JSON, default=list)
    consent_method = db.Column(db.String(80))
    consent_reference = db.Column(db.String(180))
    consent_document_id = db.Column(db.Integer, db.ForeignKey('actor_documents.id'))
    granted_by_name = db.Column(db.String(120))
    granted_by_role = db.Column(db.String(120))
    granted_by_email = db.Column(db.String(120))
    granted_by_phone = db.Column(db.String(50))
    granted_at = db.Column(db.DateTime)
    expires_at = db.Column(db.DateTime)
    withdrawn_at = db.Column(db.DateTime)
    withdrawal_reason = db.Column(db.Text)
    captured_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    review_status = db.Column(db.String(50), default='pending_review')
    reviewed_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    reviewed_at = db.Column(db.DateTime)
    review_notes = db.Column(db.Text)
    active = db.Column(db.Boolean, default=True)

    market_actor = db.relationship('MarketActor', backref='consent_records')
    partner_organization = db.relationship('PartnerOrganization', backref='actor_consent_records')
    consent_document = db.relationship('ActorDocument', foreign_keys=[consent_document_id], backref='linked_consent_records')
    captured_by_user = db.relationship('User', foreign_keys=[captured_by_user_id], backref='captured_actor_consents')
    reviewed_by_user = db.relationship('User', foreign_keys=[reviewed_by_user_id], backref='reviewed_actor_consents')


class ApiClient(TimestampMixin, db.Model):
    __tablename__ = 'api_clients'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    slug = db.Column(db.String(120), unique=True, nullable=False)
    owner_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    partner_organization_id = db.Column(db.Integer, db.ForeignKey('partner_organizations.id'))
    status = db.Column(db.String(20), default='pending')
    scopes = db.Column(db.JSON, default=list)
    notes = db.Column(db.Text)

    owner_user = db.relationship('User', backref='api_clients')
    partner_organization = db.relationship('PartnerOrganization', backref='api_clients')
    api_keys = db.relationship('ApiKey', backref='api_client', lazy=True)


class ApiKey(db.Model):
    __tablename__ = 'api_keys'

    id = db.Column(db.Integer, primary_key=True)
    api_client_id = db.Column(db.Integer, db.ForeignKey('api_clients.id'), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    key_prefix = db.Column(db.String(16), nullable=False)
    key_hash = db.Column(db.String(64), nullable=False)
    status = db.Column(db.String(20), default='active')
    scopes = db.Column(db.JSON, default=list)
    last_used_at = db.Column(db.DateTime)
    expires_at = db.Column(db.DateTime)
    revoked_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @staticmethod
    def hash_secret(raw_secret):
        return hashlib.sha256(raw_secret.encode('utf-8')).hexdigest()

    def set_secret(self, raw_secret):
        self.key_prefix = raw_secret[:8]
        self.key_hash = self.hash_secret(raw_secret)


class ApiUsageEvent(db.Model):
    __tablename__ = 'api_usage_events'

    id = db.Column(db.Integer, primary_key=True)
    api_client_id = db.Column(db.Integer, db.ForeignKey('api_clients.id'), nullable=False)
    api_key_id = db.Column(db.Integer, db.ForeignKey('api_keys.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    endpoint = db.Column(db.String(255), nullable=False)
    method = db.Column(db.String(10), nullable=False)
    dataset_type = db.Column(db.String(80))
    snapshot_month = db.Column(db.String(7))
    filters_json = db.Column(db.JSON)
    row_count = db.Column(db.Integer)
    status_code = db.Column(db.Integer)
    units = db.Column(db.Integer, default=1)
    ip_address = db.Column(db.String(80))
    user_agent = db.Column(db.String(255))
    metadata_json = db.Column(db.JSON)
    occurred_at = db.Column(db.DateTime, default=datetime.utcnow)

    api_client = db.relationship('ApiClient', backref='usage_events')
    api_key = db.relationship('ApiKey', backref='usage_events')
    user = db.relationship('User', backref='api_usage_events')


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    organization_type = db.Column(db.String(80))
    organization_id = db.Column(db.Integer)
    action = db.Column(db.String(120), nullable=False)
    entity_type = db.Column(db.String(120), nullable=False)
    entity_id = db.Column(db.Integer)
    before_values = db.Column(db.JSON)
    after_values = db.Column(db.JSON)
    ip_address = db.Column(db.String(80))
    user_agent = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='audit_logs')


def get_user_entitlements(user):
    """
    Get user's data access entitlements with priority logic.

    Priority (highest to lowest):
    1. Active LiveIntelligenceAccess - full live access to monthly updates
    2. Active License - snapshot access to specific month only
    3. Active Subscription - monthly access with scoped regions/crops
    4. Free - view catalogue only, no data access

    Returns dict with:
    - access_type: 'live_intelligence' | 'license' | 'subscription' | 'free'
    - regions: list of region codes user can access
    - crops: list of crop names user can access (None = all)
    - datasets: list of dataset codes user can access
    - monthly_export_limit: int or None
    - snapshot_month: str (YYYY-MM) for license only, else None
    - source: the access object (LiveIntelligenceAccess, License, Subscription, or None)
    """
    if not user:
        return {
            'access_type': 'free',
            'regions': [],
            'crops': [],
            'datasets': [],
            'monthly_export_limit': 0,
            'snapshot_month': None,
            'source': None
        }

    now = datetime.utcnow()

    live_access = LiveIntelligenceAccess.query.filter_by(
        user_id=user.id,
        active=True
    ).filter(
        LiveIntelligenceAccess.start_date <= now,
        LiveIntelligenceAccess.end_date >= now
    ).first()

    if live_access:
        all_datasets = ['actor_activity_status', 'market_changes', 'crop_availability_status', 'trust_index']
        return {
            'access_type': 'live_intelligence',
            'regions': live_access.regions_selected or list(NIGERIA_REGIONS.keys()),
            'crops': live_access.crops_selected if live_access.crops_selected else None,
            'datasets': all_datasets,
            'monthly_export_limit': None,
            'snapshot_month': None,
            'source': live_access
        }

    active_license = License.query.filter_by(
        user_id=user.id,
        status='active'
    ).order_by(License.created_at.desc()).first()

    if active_license:
        all_datasets = ['actor_activity_status', 'market_changes', 'crop_availability_status', 'trust_index']
        return {
            'access_type': 'license',
            'regions': active_license.regions_selected or [],
            'crops': active_license.crops_selected if active_license.crops_selected else None,
            'datasets': all_datasets,
            'monthly_export_limit': None,
            'snapshot_month': active_license.snapshot_month,
            'source': active_license
        }

    subscription = user.get_active_subscription()
    if subscription:
        plan = PaymentPlan.query.filter_by(code=subscription.plan_code).first()
        if plan:
            return {
                'access_type': 'subscription',
                'regions': subscription.regions_selected or [],
                'crops': subscription.crops_selected or [],
                'datasets': plan.allowed_datasets or [],
                'monthly_export_limit': plan.monthly_export_limit,
                'snapshot_month': None,
                'source': subscription
            }

    return {
        'access_type': 'free',
        'regions': [],
        'crops': [],
        'datasets': [],
        'monthly_export_limit': 0,
        'snapshot_month': None,
        'source': None
    }


def consent_record_is_active(consent_record, now=None):
    """Return true when a consent record currently permits sharing gates."""

    if not consent_record:
        return False
    now = now or datetime.utcnow()
    if not consent_record.active:
        return False
    if consent_record.consent_status != "granted":
        return False
    if consent_record.withdrawn_at:
        return False
    if consent_record.expires_at and consent_record.expires_at < now:
        return False
    if consent_record.review_status == "rejected":
        return False
    return True


def get_active_actor_consent(actor, now=None):
    if not actor:
        return None

    latest_consent_record = (
        ActorConsentRecord.query.filter_by(
            market_actor_id=actor.id,
            partner_organization_id=actor.partner_organization_id,
        )
        .order_by(ActorConsentRecord.updated_at.desc(), ActorConsentRecord.id.desc())
        .first()
    )
    if consent_record_is_active(latest_consent_record, now=now):
        return latest_consent_record
    return None


def actor_has_active_consent(actor):
    return get_active_actor_consent(actor) is not None


def actor_can_share_data(actor, channel):
    consent_record = get_active_actor_consent(actor)
    if not consent_record:
        return False
    if channel not in (consent_record.sharing_channels_json or []):
        return False
    return bool(consent_record.permitted_data_categories_json)


def actor_can_share_documents(actor, channel, document_category=None):
    consent_record = get_active_actor_consent(actor)
    if not consent_record:
        return False
    if channel not in (consent_record.sharing_channels_json or []):
        return False

    permitted_categories = consent_record.permitted_document_categories_json or []
    if not permitted_categories:
        return False
    if document_category:
        return document_category in permitted_categories
    return True


def consent_document_category_for_document_type(document_type):
    if not document_type:
        return "other"
    return DOCUMENT_TYPE_CONSENT_CATEGORY_MAP.get(document_type.category, "other")


def calculate_actor_quality_score(actor):
    """Return advisory data quality scoring for a market actor."""

    def has_value(value):
        return value is not None and value != ""

    def score_section(name, max_points, checks):
        passed = [check for check in checks if check["complete"]]
        points = round(max_points * (len(passed) / len(checks))) if checks else 0
        completed = len(passed) == len(checks)
        return {
            "name": name,
            "points": points,
            "max_points": max_points,
            "complete": completed,
            "checks": checks,
        }

    location = actor.location
    primary_contact = actor.contacts[0] if actor.contacts else None
    export_profile = actor.export_profile
    certification = actor.certifications[0] if actor.certifications else None
    constraint = actor.constraints[0] if actor.constraints else None

    sections = [
        score_section("Core identity", 25, [
            {"label": "Actor name", "complete": has_value(actor.name)},
            {"label": "Actor type", "complete": has_value(actor.actor_type)},
            {"label": "Actor status", "complete": has_value(actor.status)},
            {"label": "Crop or commodity category", "complete": bool(actor.crop_id or actor.commodity_id or has_value(actor.commodity_category))},
        ]),
        score_section("Location", 15, [
            {"label": "Region, state, LGA, or location text", "complete": bool(location and (location.region_id or location.state_id or location.lga_id or has_value(location.state_name) or has_value(location.lga_name) or has_value(location.location_text)))},
        ]),
        score_section("Contact", 15, [
            {"label": "Contact name", "complete": bool(primary_contact and has_value(primary_contact.contact_name))},
            {"label": "Contact role", "complete": bool(primary_contact and has_value(primary_contact.contact_role))},
            {"label": "Phone or email", "complete": bool(primary_contact and (has_value(primary_contact.phone) or has_value(primary_contact.email)))},
        ]),
        score_section("Export profile", 15, [
            {"label": "Years in trade", "complete": bool(export_profile and export_profile.years_in_export_trade is not None)},
            {"label": "Destination", "complete": bool(export_profile and (export_profile.trade_destination_id or has_value(export_profile.trade_destination_name)))},
            {"label": "Capacity", "complete": bool(export_profile and has_value(export_profile.export_capacity))},
            {"label": "Port", "complete": bool(export_profile and (export_profile.port_id or has_value(export_profile.port_of_exit)))},
        ]),
        score_section("Certification", 15, [
            {"label": "Certification name or type", "complete": bool(certification and (certification.certification_type_id or has_value(certification.certification_name)))},
            {"label": "Issuing body", "complete": bool(certification and has_value(certification.issuing_body))},
            {"label": "Reference or certificate number", "complete": bool(certification and (has_value(certification.reference_number) or has_value(certification.certificate_number)))},
            {"label": "Certification status", "complete": bool(certification and has_value(certification.status))},
        ]),
        score_section("Operational constraint", 5, [
            {"label": "Constraint category, text, and severity", "complete": bool(constraint and ((constraint.status == "not_applicable") or (has_value(constraint.constraint_category) and has_value(constraint.constraint_text) and has_value(constraint.severity))))},
        ]),
        score_section("Partner workflow", 5, [
            {"label": "At least one partner record change", "complete": bool(actor.partner_record_changes)},
        ]),
        {
            "name": "Documents readiness",
            "points": 0,
            "max_points": 5,
            "complete": False,
            "deferred": True,
            "checks": [
                {"label": "Document vault deferred until Phase 3", "complete": False}
            ],
        },
    ]

    score = sum(section["points"] for section in sections)
    if score >= 90:
        grade = "complete"
    elif score >= 70:
        grade = "high"
    elif score >= 40:
        grade = "medium"
    else:
        grade = "low"

    completed_sections = [section["name"] for section in sections if section["complete"]]
    missing_sections = [section["name"] for section in sections if not section["complete"] and not section.get("deferred")]
    deferred_sections = [section["name"] for section in sections if section.get("deferred")]

    return {
        "score": score,
        "grade": grade,
        "completed_sections": completed_sections,
        "missing_sections": missing_sections,
        "deferred_sections": deferred_sections,
        "checks": sections,
    }
