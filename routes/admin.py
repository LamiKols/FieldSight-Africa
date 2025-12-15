"""Admin routes"""

import csv
import io
import json
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from functools import wraps
from models import db, User, Subscription, Dataset, DatasetMonth, DatasetRecord, ExportLog, License, LiveIntelligenceAccess, get_region_from_state, NIGERIA_REGIONS

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
            
            processed_rows = []
            rejected_rows = []
            
            for row in rows:
                state = row.get('state') or row.get('State') or row.get('STATE')
                if state:
                    region_code = get_region_from_state(state)
                    if region_code:
                        row['region_code'] = region_code
                        processed_rows.append(row)
                    else:
                        rejected_rows.append({'row': row, 'reason': f'Unknown state: {state}'})
                else:
                    processed_rows.append(row)
            
            for row in processed_rows:
                record = DatasetRecord(
                    dataset_month_id=dataset_month.id,
                    record_json=row
                )
                db.session.add(record)
            
            db.session.commit()
            
            msg = f'Successfully uploaded {len(processed_rows)} records for {dataset.name} - {month}.'
            if rejected_rows:
                msg += f' {len(rejected_rows)} rows rejected due to unmapped states.'
            flash(msg, 'success' if not rejected_rows else 'warning')
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


@admin_bp.route('/live-intelligence')
@login_required
@admin_required
def live_intelligence():
    grants = LiveIntelligenceAccess.query.order_by(LiveIntelligenceAccess.created_at.desc()).all()
    users = User.query.filter_by(role='subscriber').order_by(User.email).all()
    return render_template('admin/live_intelligence.html', 
                           grants=grants, 
                           users=users,
                           regions=NIGERIA_REGIONS)


@admin_bp.route('/live-intelligence/grant', methods=['POST'])
@login_required
@admin_required
def grant_live_intelligence():
    user_id = request.form.get('user_id')
    regions = request.form.getlist('regions')
    crops_text = request.form.get('crops', '')
    crops = [c.strip() for c in crops_text.split(',') if c.strip()]
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    notes = request.form.get('notes', '')
    
    if not user_id or not start_date or not end_date:
        flash('Please fill in all required fields.', 'error')
        return redirect(url_for('admin.live_intelligence'))
    
    if len(regions) == 0:
        flash('Please select at least one region.', 'error')
        return redirect(url_for('admin.live_intelligence'))
    
    try:
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        
        if end <= start:
            flash('End date must be after start date.', 'error')
            return redirect(url_for('admin.live_intelligence'))
        
        grant = LiveIntelligenceAccess(
            user_id=int(user_id),
            regions_allowed=len(regions),
            crops_allowed=len(crops) if crops else None,
            regions_selected=regions,
            crops_selected=crops,
            start_date=start,
            end_date=end,
            active=True,
            notes=notes
        )
        db.session.add(grant)
        db.session.commit()
        
        user = User.query.get(user_id)
        flash(f'Live Intelligence access granted to {user.email}.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error granting access: {str(e)}', 'error')
    
    return redirect(url_for('admin.live_intelligence'))


@admin_bp.route('/live-intelligence/<int:grant_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_live_intelligence(grant_id):
    grant = LiveIntelligenceAccess.query.get_or_404(grant_id)
    grant.active = not grant.active
    db.session.commit()
    
    status = 'activated' if grant.active else 'deactivated'
    flash(f'Access {status} for {grant.user.email}.', 'success')
    return redirect(url_for('admin.live_intelligence'))


@admin_bp.route('/live-intelligence/<int:grant_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_live_intelligence(grant_id):
    grant = LiveIntelligenceAccess.query.get_or_404(grant_id)
    email = grant.user.email
    db.session.delete(grant)
    db.session.commit()
    
    flash(f'Access removed for {email}.', 'success')
    return redirect(url_for('admin.live_intelligence'))
