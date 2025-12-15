"""Subscriber routes"""

import csv
import io
import json
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, Response
from flask_login import login_required, current_user
from models import db, Dataset, DatasetMonth, DatasetRecord, ExportLog

subscriber_bp = Blueprint('subscriber', __name__)


def subscription_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.get_active_subscription():
            flash('You need an active subscription to access this feature.', 'warning')
            return redirect(url_for('public.pricing'))
        return f(*args, **kwargs)
    return decorated_function


@subscriber_bp.route('/dashboard')
@login_required
def dashboard():
    subscription = current_user.get_active_subscription()
    plan = current_user.get_plan()
    monthly_exports = current_user.get_monthly_exports()
    
    datasets = Dataset.query.all()
    
    current_month = datetime.utcnow().strftime('%Y-%m')
    available_months = DatasetMonth.query.filter_by(published=True).order_by(DatasetMonth.month.desc()).limit(6).all()
    
    return render_template('dashboard.html',
                           subscription=subscription,
                           plan=plan,
                           monthly_exports=monthly_exports,
                           datasets=datasets,
                           available_months=available_months,
                           current_month=current_month)


@subscriber_bp.route('/datasets')
@login_required
def datasets():
    all_datasets = Dataset.query.all()
    plan = current_user.get_plan()
    
    dataset_info = []
    for ds in all_datasets:
        months = DatasetMonth.query.filter_by(dataset_id=ds.id, published=True).order_by(DatasetMonth.month.desc()).all()
        can_access = current_user.can_access_dataset(ds.code)
        dataset_info.append({
            'dataset': ds,
            'months': months,
            'can_access': can_access
        })
    
    return render_template('datasets.html', dataset_info=dataset_info, plan=plan)


@subscriber_bp.route('/datasets/<dataset_code>/<month>')
@login_required
@subscription_required
def view_dataset_month(dataset_code, month):
    dataset = Dataset.query.filter_by(code=dataset_code).first_or_404()
    
    if not current_user.can_access_dataset(dataset_code):
        flash('Your plan does not include access to this dataset.', 'error')
        return redirect(url_for('subscriber.datasets'))
    
    dataset_month = DatasetMonth.query.filter_by(dataset_id=dataset.id, month=month, published=True).first_or_404()
    
    records = DatasetRecord.query.filter_by(dataset_month_id=dataset_month.id).limit(100).all()
    total_records = DatasetRecord.query.filter_by(dataset_month_id=dataset_month.id).count()
    
    plan = current_user.get_plan()
    monthly_exports = current_user.get_monthly_exports()
    remaining_exports = plan.monthly_export_limit - monthly_exports if plan else 0
    
    current_month = datetime.utcnow().strftime('%Y-%m')
    is_current_month = month == current_month
    
    return render_template('dataset_view.html',
                           dataset=dataset,
                           dataset_month=dataset_month,
                           records=records,
                           total_records=total_records,
                           remaining_exports=remaining_exports,
                           is_current_month=is_current_month,
                           plan=plan)


@subscriber_bp.route('/export/<int:dataset_month_id>')
@login_required
@subscription_required
def export_dataset(dataset_month_id):
    dataset_month = DatasetMonth.query.get_or_404(dataset_month_id)
    dataset = dataset_month.dataset
    
    if not current_user.can_access_dataset(dataset.code):
        flash('Your plan does not include access to this dataset.', 'error')
        return redirect(url_for('subscriber.datasets'))
    
    records = DatasetRecord.query.filter_by(dataset_month_id=dataset_month_id).all()
    total_rows = len(records)
    
    if not current_user.can_export(total_rows):
        plan = current_user.get_plan()
        monthly_exports = current_user.get_monthly_exports()
        flash(f'Export limit exceeded. You have {plan.monthly_export_limit - monthly_exports} rows remaining this month.', 'error')
        return redirect(url_for('subscriber.view_dataset_month', dataset_code=dataset.code, month=dataset_month.month))
    
    if not records:
        flash('No records to export.', 'warning')
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
