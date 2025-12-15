"""Subscriber routes"""

import csv
import io
import json
from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, Response
from flask_login import login_required, current_user
from models import db, Dataset, DatasetMonth, DatasetRecord, ExportLog, ViewLog, LicensedPack, License, get_user_entitlements, NIGERIA_REGIONS

subscriber_bp = Blueprint('subscriber', __name__)

RATE_LIMIT_VIEWS_PER_MINUTE = 30


def data_access_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        entitlements = get_user_entitlements(current_user)
        if entitlements['access_type'] == 'free':
            flash('You need an active subscription or license to access this feature.', 'warning')
            return redirect(url_for('public.pricing'))
        return f(*args, **kwargs)
    return decorated_function


def filter_records_by_entitlements(records, entitlements):
    """Filter dataset records based on user's region and crop entitlements."""
    filtered = []
    for record in records:
        data = record.record_json
        if isinstance(data, str):
            data = json.loads(data)
        
        region_code = data.get('region_code')
        if entitlements['regions'] and region_code:
            if region_code not in entitlements['regions']:
                continue
        
        crop = data.get('crop') or data.get('Crop') or data.get('CROP')
        if entitlements['crops'] and crop:
            if crop not in entitlements['crops']:
                continue
        
        filtered.append(record)
    return filtered


@subscriber_bp.route('/dashboard')
@login_required
def dashboard():
    entitlements = get_user_entitlements(current_user)
    subscription = current_user.get_active_subscription()
    plan = current_user.get_plan()
    monthly_exports = current_user.get_monthly_exports()
    
    datasets = Dataset.query.all()
    
    current_month = datetime.utcnow().strftime('%Y-%m')
    available_months = DatasetMonth.query.filter_by(published=True).order_by(DatasetMonth.month.desc()).limit(6).all()
    
    region_names = {code: name for code, name in NIGERIA_REGIONS.items() if code in entitlements['regions']} if entitlements['regions'] else {}
    
    return render_template('dashboard.html',
                           subscription=subscription,
                           plan=plan,
                           monthly_exports=monthly_exports,
                           datasets=datasets,
                           available_months=available_months,
                           current_month=current_month,
                           entitlements=entitlements,
                           region_names=region_names)


@subscriber_bp.route('/datasets')
@login_required
def datasets():
    all_datasets = Dataset.query.all()
    entitlements = get_user_entitlements(current_user)
    plan = current_user.get_plan()
    
    dataset_info = []
    for ds in all_datasets:
        if entitlements['access_type'] == 'license' and entitlements['snapshot_month']:
            months = DatasetMonth.query.filter_by(
                dataset_id=ds.id, 
                published=True, 
                month=entitlements['snapshot_month']
            ).all()
        else:
            months = DatasetMonth.query.filter_by(dataset_id=ds.id, published=True).order_by(DatasetMonth.month.desc()).all()
        
        can_access = ds.code in entitlements['datasets']
        dataset_info.append({
            'dataset': ds,
            'months': months,
            'can_access': can_access
        })
    
    return render_template('datasets.html', dataset_info=dataset_info, plan=plan, entitlements=entitlements)


@subscriber_bp.route('/datasets/<dataset_code>/<month>')
@login_required
@data_access_required
def view_dataset_month(dataset_code, month):
    dataset = Dataset.query.filter_by(code=dataset_code).first_or_404()
    entitlements = get_user_entitlements(current_user)
    
    if dataset_code not in entitlements['datasets']:
        flash('Your plan does not include access to this dataset.', 'error')
        return redirect(url_for('subscriber.datasets'))
    
    if entitlements['access_type'] == 'license' and entitlements['snapshot_month']:
        if month != entitlements['snapshot_month']:
            flash(f'Your license only provides access to the {entitlements["snapshot_month"]} snapshot.', 'warning')
            return redirect(url_for('subscriber.datasets'))
    
    dataset_month = DatasetMonth.query.filter_by(dataset_id=dataset.id, month=month, published=True).first_or_404()
    
    one_minute_ago = datetime.utcnow() - timedelta(minutes=1)
    recent_views = ViewLog.query.filter(
        ViewLog.user_id == current_user.id,
        ViewLog.viewed_at > one_minute_ago
    ).count()
    
    if recent_views >= RATE_LIMIT_VIEWS_PER_MINUTE:
        flash('Too many requests. Please wait a moment before viewing more datasets.', 'warning')
        return redirect(url_for('subscriber.datasets'))
    
    all_records = DatasetRecord.query.filter_by(dataset_month_id=dataset_month.id).all()
    filtered_records = filter_records_by_entitlements(all_records, entitlements)
    
    records = filtered_records[:100]
    total_records = len(filtered_records)
    
    plan = current_user.get_plan()
    monthly_exports = current_user.get_monthly_exports()
    
    if entitlements['monthly_export_limit']:
        remaining_exports = entitlements['monthly_export_limit'] - monthly_exports
    else:
        remaining_exports = total_records
    
    current_month_str = datetime.utcnow().strftime('%Y-%m')
    is_current_month = month == current_month_str
    
    region_names = {code: name for code, name in NIGERIA_REGIONS.items() if code in entitlements['regions']} if entitlements['regions'] else NIGERIA_REGIONS
    
    view_log = ViewLog(
        user_id=current_user.id,
        dataset_month_id=dataset_month.id
    )
    db.session.add(view_log)
    db.session.commit()
    
    return render_template('dataset_view.html',
                           dataset=dataset,
                           dataset_month=dataset_month,
                           records=records,
                           total_records=total_records,
                           remaining_exports=remaining_exports,
                           is_current_month=is_current_month,
                           plan=plan,
                           entitlements=entitlements,
                           region_names=region_names)


@subscriber_bp.route('/export/<int:dataset_month_id>')
@login_required
@data_access_required
def export_dataset(dataset_month_id):
    dataset_month = DatasetMonth.query.get_or_404(dataset_month_id)
    entitlements = get_user_entitlements(current_user)
    
    if not dataset_month.published:
        flash('This dataset is not available for export.', 'error')
        return redirect(url_for('subscriber.datasets'))
    
    dataset = dataset_month.dataset
    
    if dataset.code not in entitlements['datasets']:
        flash('Your plan does not include access to this dataset.', 'error')
        return redirect(url_for('subscriber.datasets'))
    
    if entitlements['access_type'] == 'license' and entitlements['snapshot_month']:
        if dataset_month.month != entitlements['snapshot_month']:
            flash(f'Your license only provides access to the {entitlements["snapshot_month"]} snapshot.', 'warning')
            return redirect(url_for('subscriber.datasets'))
    
    all_records = DatasetRecord.query.filter_by(dataset_month_id=dataset_month_id).all()
    records = filter_records_by_entitlements(all_records, entitlements)
    total_rows = len(records)
    
    if entitlements['monthly_export_limit']:
        monthly_exports = current_user.get_monthly_exports()
        if (monthly_exports + total_rows) > entitlements['monthly_export_limit']:
            remaining = entitlements['monthly_export_limit'] - monthly_exports
            flash(f'Export limit exceeded. You have {remaining} rows remaining this month.', 'error')
            return redirect(url_for('subscriber.view_dataset_month', dataset_code=dataset.code, month=dataset_month.month))
    
    if not records:
        flash('No records to export based on your region/crop access.', 'warning')
        return redirect(url_for('subscriber.view_dataset_month', dataset_code=dataset.code, month=dataset_month.month))
    
    output = io.StringIO()
    
    first_record = records[0].record_json
    if isinstance(first_record, str):
        first_record = json.loads(first_record)
    fieldnames = list(first_record.keys())
    
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    
    for record in records:
        data = record.record_json
        if isinstance(data, str):
            data = json.loads(data)
        writer.writerow(data)
    
    export_log = ExportLog(
        user_id=current_user.id,
        dataset_month_id=dataset_month_id,
        rows_exported=total_rows
    )
    db.session.add(export_log)
    db.session.commit()
    
    output.seek(0)
    filename = f"{dataset.code}_{dataset_month.month}.csv"
    
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


@subscriber_bp.route('/packs')
def packs():
    """Licensed data packs catalogue - permanent snapshot purchases."""
    packs = LicensedPack.query.filter_by(active=True).all()
    entitlements = get_user_entitlements(current_user) if current_user.is_authenticated else None
    
    current_month = datetime.utcnow().strftime('%Y-%m')
    
    return render_template('packs.html',
                           packs=packs,
                           entitlements=entitlements,
                           current_month=current_month,
                           regions=NIGERIA_REGIONS)


@subscriber_bp.route('/licenses')
@login_required
def licenses():
    """User's purchased licensed data packs."""
    user_licenses = License.query.filter_by(user_id=current_user.id).order_by(License.created_at.desc()).all()
    entitlements = get_user_entitlements(current_user)
    
    return render_template('licenses.html',
                           licenses=user_licenses,
                           entitlements=entitlements,
                           regions=NIGERIA_REGIONS)


@subscriber_bp.route('/live-intelligence')
def live_intelligence():
    """Live Market Intelligence explainer page with request form."""
    entitlements = get_user_entitlements(current_user) if current_user.is_authenticated else None
    
    return render_template('live_intelligence.html',
                           entitlements=entitlements,
                           regions=NIGERIA_REGIONS)


@subscriber_bp.route('/live-intelligence/request', methods=['POST'])
@login_required
def live_intelligence_request():
    """Handle Live Intelligence access request form submission."""
    name = request.form.get('name')
    email = request.form.get('email')
    organization = request.form.get('organization')
    regions_requested = request.form.getlist('regions')
    message = request.form.get('message')
    
    flash('Thank you for your interest! Our team will contact you within 2 business days to discuss your Live Intelligence requirements.', 'success')
    return redirect(url_for('subscriber.live_intelligence'))
