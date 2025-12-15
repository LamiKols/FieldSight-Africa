"""Admin routes"""

import csv
import io
import json
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from functools import wraps
from models import db, User, Subscription, Dataset, DatasetMonth, DatasetRecord, ExportLog

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            flash('Admin access required.', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


@admin_bp.route('/')
@login_required
@admin_required
def dashboard():
    total_users = User.query.filter_by(role='subscriber').count()
    active_subs = Subscription.query.filter_by(status='active').count()
    total_datasets = Dataset.query.count()
    total_exports = db.session.query(db.func.sum(ExportLog.rows_exported)).scalar() or 0
    
    recent_exports = ExportLog.query.order_by(ExportLog.exported_at.desc()).limit(10).all()
    
    return render_template('admin/dashboard.html',
                           total_users=total_users,
                           active_subs=active_subs,
                           total_datasets=total_datasets,
                           total_exports=total_exports,
                           recent_exports=recent_exports)


@admin_bp.route('/upload', methods=['GET', 'POST'])
@login_required
@admin_required
def upload():
    datasets = Dataset.query.all()
    
    if request.method == 'POST':
        dataset_id = request.form.get('dataset_id')
        month = request.form.get('month')
        override = request.form.get('override') == 'true'
        
        if not dataset_id or not month:
            flash('Please select a dataset and month.', 'error')
            return render_template('admin/upload.html', datasets=datasets)
        
        if 'file' not in request.files:
            flash('No file uploaded.', 'error')
            return render_template('admin/upload.html', datasets=datasets)
        
        file = request.files['file']
        if file.filename == '':
            flash('No file selected.', 'error')
            return render_template('admin/upload.html', datasets=datasets)
        
        if not file.filename.endswith('.csv'):
            flash('Please upload a CSV file.', 'error')
            return render_template('admin/upload.html', datasets=datasets)
        
        dataset = Dataset.query.get(dataset_id)
        if not dataset:
            flash('Invalid dataset selected.', 'error')
            return render_template('admin/upload.html', datasets=datasets)
        
        existing = DatasetMonth.query.filter_by(dataset_id=dataset_id, month=month).first()
        if existing and not override:
            flash(f'Data for {dataset.name} - {month} already exists. Enable override to replace.', 'warning')
            return render_template('admin/upload.html', datasets=datasets)
        
        try:
            stream = io.StringIO(file.stream.read().decode('utf-8'))
            reader = csv.DictReader(stream)
            
            rows = list(reader)
            if not rows:
                flash('CSV file is empty.', 'error')
                return render_template('admin/upload.html', datasets=datasets)
            
            if existing:
                DatasetRecord.query.filter_by(dataset_month_id=existing.id).delete()
                dataset_month = existing
                dataset_month.uploaded_at = datetime.utcnow()
            else:
                dataset_month = DatasetMonth(
                    dataset_id=dataset_id,
                    month=month,
                    published=False
                )
                db.session.add(dataset_month)
                db.session.flush()
            
            for row in rows:
                record = DatasetRecord(
                    dataset_month_id=dataset_month.id,
                    record_json=row
                )
                db.session.add(record)
            
            db.session.commit()
            
            flash(f'Successfully uploaded {len(rows)} records for {dataset.name} - {month}.', 'success')
            return redirect(url_for('admin.datasets'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error processing file: {str(e)}', 'error')
            return render_template('admin/upload.html', datasets=datasets)
    
    return render_template('admin/upload.html', datasets=datasets)


@admin_bp.route('/datasets')
@login_required
@admin_required
def datasets():
    all_datasets = Dataset.query.all()
    dataset_months = DatasetMonth.query.order_by(DatasetMonth.month.desc()).all()
    
    return render_template('admin/datasets.html', 
                           datasets=all_datasets,
                           dataset_months=dataset_months)


@admin_bp.route('/datasets/<int:dataset_month_id>/publish', methods=['POST'])
@login_required
@admin_required
def publish_dataset(dataset_month_id):
    dataset_month = DatasetMonth.query.get_or_404(dataset_month_id)
    dataset_month.published = True
    db.session.commit()
    flash(f'Dataset published successfully.', 'success')
    return redirect(url_for('admin.datasets'))


@admin_bp.route('/datasets/<int:dataset_month_id>/unpublish', methods=['POST'])
@login_required
@admin_required
def unpublish_dataset(dataset_month_id):
    dataset_month = DatasetMonth.query.get_or_404(dataset_month_id)
    dataset_month.published = False
    db.session.commit()
    flash(f'Dataset unpublished.', 'success')
    return redirect(url_for('admin.datasets'))


@admin_bp.route('/users')
@login_required
@admin_required
def users():
    all_users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=all_users)


@admin_bp.route('/users/<int:user_id>')
@login_required
@admin_required
def user_detail(user_id):
    user = User.query.get_or_404(user_id)
    exports = ExportLog.query.filter_by(user_id=user_id).order_by(ExportLog.exported_at.desc()).all()
    return render_template('admin/user_detail.html', user=user, exports=exports)
