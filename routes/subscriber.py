"""Subscriber routes"""

import csv
import io
import json
from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, Response
from flask_login import login_required, current_user
from document_access import (
    ACCESS_REQUEST_TARGET_BY_TYPE,
    document_metadata_access_decision,
    externally_candidate_documents,
    log_document_access_attempt,
    request_target_allows,
    safe_document_metadata_payload,
)
from models import (
    DOCUMENT_ACCESS_REQUEST_TYPES,
    ActorDocument,
    AuditLog,
    Dataset,
    DatasetMonth,
    DatasetRecord,
    DocumentAccessRequest,
    ExportLog,
    License,
    LicensedPack,
    NIGERIA_REGIONS,
    ViewLog,
    db,
    get_user_entitlements,
)

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


def request_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr)


def request_user_agent():
    return request.headers.get('User-Agent')


def add_subscriber_audit(action, entity_type, entity_id, before_values=None, after_values=None):
    db.session.add(AuditLog(
        user_id=current_user.id,
        organization_type='subscriber',
        organization_id=current_user.id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_values=before_values,
        after_values=after_values,
        ip_address=request_ip(),
        user_agent=request_user_agent(),
    ))


def clean_subscriber_form_value(field_name):
    value = request.form.get(field_name, '')
    return value.strip() if value else ''


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


@subscriber_bp.route('/subscriber/document-metadata')
@login_required
def document_metadata():
    metadata_items = []
    blocked_count = 0
    for document in externally_candidate_documents():
        allowed, reasons, publish_control, _extraction_run = document_metadata_access_decision(
            current_user,
            document,
            'subscriber_portal',
        )
        log_document_access_attempt(
            document,
            'subscriber_metadata_list_allowed' if allowed else 'subscriber_metadata_list_blocked',
            'subscriber_portal',
            user=current_user,
            subscriber_organization_name=current_user.name,
            ip_address=request_ip(),
            user_agent=request_user_agent(),
        )
        if allowed:
            metadata_items.append(safe_document_metadata_payload(document, 'subscriber_portal', publish_control=publish_control))
        else:
            blocked_count += 1

    db.session.commit()
    return render_template(
        'subscriber/document_metadata.html',
        metadata_items=metadata_items,
        blocked_count=blocked_count,
        entitlements=get_user_entitlements(current_user),
    )


@subscriber_bp.route('/subscriber/document-metadata/<int:document_id>')
@login_required
def document_metadata_detail(document_id):
    document = ActorDocument.query.get_or_404(document_id)
    allowed, reasons, publish_control, _extraction_run = document_metadata_access_decision(
        current_user,
        document,
        'subscriber_portal',
    )
    log_document_access_attempt(
        document,
        'subscriber_metadata_detail_allowed' if allowed else 'subscriber_metadata_detail_blocked',
        'subscriber_portal',
        user=current_user,
        subscriber_organization_name=current_user.name,
        ip_address=request_ip(),
        user_agent=request_user_agent(),
    )
    db.session.commit()

    if not allowed:
        flash('Document metadata is not available under your current entitlement and governance gates.', 'error')
        return redirect(url_for('subscriber.document_metadata'))

    metadata = safe_document_metadata_payload(document, 'subscriber_portal', publish_control=publish_control)
    return render_template(
        'subscriber/document_metadata_detail.html',
        metadata=metadata,
        document=document,
        request_types=DOCUMENT_ACCESS_REQUEST_TYPES,
        access_request_targets=ACCESS_REQUEST_TARGET_BY_TYPE,
    )


@subscriber_bp.route('/subscriber/document-access-requests/new', methods=['GET', 'POST'])
@login_required
def new_document_access_request():
    selected_document_id = request.args.get('document_id', '').strip()
    accessible_documents = []
    for document in externally_candidate_documents():
        allowed, _reasons, publish_control, _extraction_run = document_metadata_access_decision(
            current_user,
            document,
            'subscriber_portal',
        )
        if allowed:
            accessible_documents.append({
                'document': document,
                'metadata': safe_document_metadata_payload(document, 'subscriber_portal', publish_control=publish_control),
            })

    if request.method == 'POST':
        document_id = clean_subscriber_form_value('document_id')
        request_type = clean_subscriber_form_value('request_type')
        organization_name = clean_subscriber_form_value('organization_name')
        purpose = clean_subscriber_form_value('purpose')
        if not document_id.isdigit():
            flash('Please choose a document.', 'error')
            return render_template('subscriber/document_access_request_form.html', accessible_documents=accessible_documents, request_types=DOCUMENT_ACCESS_REQUEST_TYPES, selected_document_id=selected_document_id)
        if request_type not in DOCUMENT_ACCESS_REQUEST_TYPES:
            flash('Please choose a supported access request type.', 'error')
            return render_template('subscriber/document_access_request_form.html', accessible_documents=accessible_documents, request_types=DOCUMENT_ACCESS_REQUEST_TYPES, selected_document_id=selected_document_id)
        if not purpose:
            flash('Purpose is required.', 'error')
            return render_template('subscriber/document_access_request_form.html', accessible_documents=accessible_documents, request_types=DOCUMENT_ACCESS_REQUEST_TYPES, selected_document_id=selected_document_id)

        document = ActorDocument.query.get_or_404(int(document_id))
        metadata_allowed, reasons, _publish_control, _extraction_run = document_metadata_access_decision(
            current_user,
            document,
            'subscriber_portal',
        )
        target_allowed, target_reason, request_publish_control = request_target_allows(document, request_type)
        if not metadata_allowed or not target_allowed:
            log_document_access_attempt(
                document,
                'subscriber_document_access_request_blocked',
                'subscriber_portal',
                user=current_user,
                subscriber_organization_name=organization_name or current_user.name,
                ip_address=request_ip(),
                user_agent=request_user_agent(),
            )
            add_subscriber_audit(
                'subscriber_document_access_request_blocked',
                'actor_document',
                document.id,
                after_values={
                    'request_type': request_type,
                    'metadata_allowed': metadata_allowed,
                    'request_target_allowed': target_allowed,
                    'reasons': reasons,
                    'target_reason': target_reason,
                },
            )
            db.session.commit()
            flash('This document is not eligible for a restricted access request yet.', 'error')
            return redirect(url_for('subscriber.document_metadata_detail', document_id=document.id) if metadata_allowed else url_for('subscriber.document_metadata'))

        access_request = DocumentAccessRequest(
            actor_document_id=document.id,
            user_id=current_user.id,
            request_type=request_type,
            request_channel='subscriber_portal',
            organization_name=organization_name or current_user.name,
            purpose=purpose,
            status='pending',
        )
        db.session.add(access_request)
        db.session.flush()
        log_document_access_attempt(
            document,
            'subscriber_document_access_request_created',
            'subscriber_portal',
            user=current_user,
            subscriber_organization_name=access_request.organization_name,
            ip_address=request_ip(),
            user_agent=request_user_agent(),
        )
        add_subscriber_audit(
            'subscriber_document_access_requested',
            'document_access_request',
            access_request.id,
            after_values={
                'actor_document_id': document.id,
                'request_type': request_type,
                'publish_target': ACCESS_REQUEST_TARGET_BY_TYPE.get(request_type),
                'publish_status': request_publish_control.status if request_publish_control else None,
                'auto_granted': False,
            },
        )
        db.session.commit()
        flash('Access request recorded for admin review. No document access has been granted automatically.', 'success')
        return redirect(url_for('subscriber.document_metadata_detail', document_id=document.id))

    return render_template(
        'subscriber/document_access_request_form.html',
        accessible_documents=accessible_documents,
        request_types=DOCUMENT_ACCESS_REQUEST_TYPES,
        selected_document_id=selected_document_id,
    )


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
