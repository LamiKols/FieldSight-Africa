"""
Database models for Agricultural Intelligence Platform

This platform sells time-sensitive agricultural intelligence, not static directories.
Access expires because intelligence decays.
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


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
