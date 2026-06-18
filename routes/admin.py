"""Admin routes"""

import csv
import io
import json
import mimetypes
from datetime import datetime
from flask import Blueprint, abort, render_template, redirect, send_file, url_for, flash, request
from flask_login import login_required, current_user
from functools import wraps
from models import (
    ActorConsentRecord,
    ActorDocument,
    AuditLog,
    DocumentAccessLog,
    DocumentExtractionRun,
    DocumentFieldReconciliation,
    DocumentReview,
    DocumentType,
    MarketActor,
    PartnerOrganization,
    db,
    User,
    Subscription,
    Dataset,
    DatasetMonth,
    DatasetRecord,
    ExportLog,
    License,
    LiveIntelligenceAccess,
    ReferenceOption,
    REFERENCE_OPTION_CATEGORIES,
    get_region_from_state,
    NIGERIA_REGIONS,
    actor_can_share_documents,
    consent_document_category_for_document_type,
    get_active_actor_consent,
)
from routes.partner import (
    PREVIEWABLE_DOCUMENT_EXTENSIONS,
    current_document_version,
    document_version_file_metadata,
    resolve_document_storage_path,
)

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

ADMIN_REVIEW_STATUSES = [
    'pending',
    'approved',
    'rejected',
    'needs_correction',
    'redaction_required',
]

ADMIN_REVIEW_ACTIONS = {
    'approve': {
        'review_status': 'approved',
        'document_status': 'approved',
        'audit_action': 'admin_document_review_approved',
        'review_entry_status': 'approved',
    },
    'reject': {
        'review_status': 'rejected',
        'document_status': 'rejected',
        'verification_status': 'rejected',
        'audit_action': 'admin_document_review_rejected',
        'review_entry_status': 'rejected',
    },
    'request_correction': {
        'review_status': 'needs_correction',
        'document_status': 'needs_correction',
        'audit_action': 'admin_document_correction_requested',
        'review_entry_status': 'needs_correction',
    },
    'require_redaction': {
        'review_status': 'redaction_required',
        'redaction_status': 'redaction_required',
        'audit_action': 'admin_document_redaction_required',
        'review_entry_status': 'redaction_required',
    },
    'mark_verified': {
        'verification_status': 'verified',
        'audit_action': 'admin_document_verification_updated',
        'review_entry_status': 'verified',
    },
    'mark_unverified': {
        'verification_status': 'unverified',
        'audit_action': 'admin_document_verification_updated',
        'review_entry_status': 'unverified',
    },
}

EXTERNAL_DOCUMENT_REVIEW_CHANNELS = [
    'subscriber_portal',
    'api',
    'approved_buyer_due_diligence',
]


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            flash('Admin access required.', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def iso_date(value):
    return value.isoformat() if value else None


def document_review_snapshot(document):
    return {
        'id': document.id,
        'market_actor_id': document.market_actor_id,
        'partner_organization_id': document.partner_organization_id,
        'document_type_id': document.document_type_id,
        'title': document.title,
        'document_status': document.document_status,
        'review_status': document.review_status,
        'verification_status': document.verification_status,
        'redaction_status': document.redaction_status,
        'subscriber_access_level': document.subscriber_access_level,
        'visibility_level': document.visibility_level,
        'reviewed_by_user_id': document.reviewed_by_user_id,
        'reviewed_at': document.reviewed_at.isoformat() if document.reviewed_at else None,
        'review_comments': document.review_comments,
        'document_reference_number': document.document_reference_number,
        'issuing_body': document.issuing_body,
        'issued_at': iso_date(document.issued_at),
        'expires_at': iso_date(document.expires_at),
        'version_number': document.version_number,
    }


def latest_document_extraction_run(document):
    return (
        DocumentExtractionRun.query.filter_by(actor_document_id=document.id)
        .order_by(DocumentExtractionRun.created_at.desc(), DocumentExtractionRun.id.desc())
        .first()
    )


def reconciliation_rows_for_run(extraction_run):
    if not extraction_run:
        return []
    return (
        DocumentFieldReconciliation.query.filter_by(extraction_run_id=extraction_run.id)
        .order_by(DocumentFieldReconciliation.id)
        .all()
    )


def admin_document_preview_policy(document, version=None):
    _storage_path, _download_name, mime_type, extension = document_version_file_metadata(document, version=version)
    if extension in {'png', 'jpg', 'jpeg'}:
        preview_kind = 'image'
    elif extension == 'pdf':
        preview_kind = 'pdf'
    elif extension == 'csv' or (mime_type or '').startswith('text/'):
        preview_kind = 'text'
    else:
        preview_kind = 'unsupported'

    allowed = extension in PREVIEWABLE_DOCUMENT_EXTENSIONS
    return {
        'allowed': allowed,
        'preview_kind': preview_kind,
        'message': 'Admin inline preview is available for internal review.' if allowed else 'Inline preview is not available for this file type.',
        'extension': extension,
    }


def document_consent_review_context(document):
    actor = document.market_actor
    document_category = consent_document_category_for_document_type(document.document_type)
    active_consent = get_active_actor_consent(actor)
    channel_permissions = {
        channel: actor_can_share_documents(actor, channel, document_category)
        for channel in EXTERNAL_DOCUMENT_REVIEW_CHANNELS
    }
    all_external_channels_allowed = all(channel_permissions.values())

    if not active_consent:
        warning = 'No active actor consent is recorded. External subscriber, API, and buyer sharing is blocked.'
        consent_status = 'missing'
    elif not all_external_channels_allowed:
        warning = 'Active consent exists, but it does not allow every external document sharing channel required for subscriber/API/buyer use.'
        consent_status = 'external_blocked'
    else:
        warning = None
        consent_status = 'externally_shareable'

    return {
        'active_consent': active_consent,
        'document_category': document_category,
        'channel_permissions': channel_permissions,
        'all_external_channels_allowed': all_external_channels_allowed,
        'warning': warning,
        'consent_status': consent_status,
    }


def document_admin_review_context(document):
    extraction_run = latest_document_extraction_run(document)
    reconciliation_rows = reconciliation_rows_for_run(extraction_run)
    risk_flags = extraction_run.risk_flags_json if extraction_run and extraction_run.risk_flags_json else []
    mismatches = extraction_run.metadata_mismatches_json if extraction_run and extraction_run.metadata_mismatches_json else []
    expiry_readiness = extraction_run.expiry_renewal_json if extraction_run and extraction_run.expiry_renewal_json else {}
    consent_context = document_consent_review_context(document)
    version = current_document_version(document)

    return {
        'document': document,
        'actor': document.market_actor,
        'partner_organization': document.partner_organization,
        'current_version': version,
        'preview_policy': admin_document_preview_policy(document, version=version),
        'consent': consent_context,
        'extraction_run': extraction_run,
        'reconciliation_rows': reconciliation_rows,
        'risk_flags': risk_flags,
        'risk_flag_count': len(risk_flags),
        'mismatches': mismatches,
        'mismatch_count': len(mismatches),
        'expiry_readiness': expiry_readiness,
        'reconciliation_pending_count': len([row for row in reconciliation_rows if row.status == 'pending']),
    }


def add_admin_document_access_log(document, access_type, version=None):
    db.session.add(DocumentAccessLog(
        actor_document_id=document.id,
        actor_document_version_id=version.id if version else None,
        user_id=current_user.id,
        access_type=access_type,
        access_channel='admin_review',
        visibility_level=document.visibility_level or document.subscriber_access_level or 'metadata_only',
        ip_address=request.headers.get('X-Forwarded-For', request.remote_addr),
        user_agent=request.headers.get('User-Agent'),
    ))


def add_admin_document_audit(document, action, before_values, after_values):
    db.session.add(AuditLog(
        user_id=current_user.id,
        organization_type='partner_organization',
        organization_id=document.partner_organization_id,
        action=action,
        entity_type='actor_document',
        entity_id=document.id,
        before_values=before_values,
        after_values=after_values,
        ip_address=request.headers.get('X-Forwarded-For', request.remote_addr),
        user_agent=request.headers.get('User-Agent'),
    ))


def clean_admin_form_value(field_name):
    value = request.form.get(field_name, '')
    return value.strip() if value else ''


def decision_notes_for_action(action):
    review_notes = clean_admin_form_value('review_notes')
    correction_reason = clean_admin_form_value('correction_reason')
    rejection_reason = clean_admin_form_value('rejection_reason')
    if action == 'request_correction':
        return correction_reason or review_notes
    if action == 'reject':
        return rejection_reason or review_notes
    return review_notes


def apply_admin_review_action(document, action, notes):
    config = ADMIN_REVIEW_ACTIONS[action]
    if 'review_status' in config:
        document.review_status = config['review_status']
    if 'document_status' in config:
        document.document_status = config['document_status']
    if 'verification_status' in config:
        document.verification_status = config['verification_status']
    if 'redaction_status' in config:
        document.redaction_status = config['redaction_status']

    optional_verification_status = clean_admin_form_value('verification_status')
    if optional_verification_status in {'unverified', 'verified', 'expired', 'rejected', 'superseded'}:
        document.verification_status = optional_verification_status

    document.reviewed_by_user_id = current_user.id
    document.reviewed_at = datetime.utcnow()
    if notes:
        document.review_comments = notes
    return config


def filter_admin_review_documents(documents, extraction_status, risk_flag, consent_status):
    filtered_documents = []
    for document in documents:
        context = document_admin_review_context(document)
        extraction_run = context['extraction_run']

        if extraction_status:
            if extraction_status == 'missing':
                if extraction_run:
                    continue
            elif not extraction_run or extraction_run.status != extraction_status:
                continue

        if risk_flag and risk_flag not in context['risk_flags']:
            continue

        if consent_status and consent_status != context['consent']['consent_status']:
            continue

        filtered_documents.append(context)
    return filtered_documents


@admin_bp.route('/')
@login_required
@admin_required
def dashboard():
    total_users = User.query.filter_by(role='subscriber').count()
    active_subs = Subscription.query.filter_by(status='active').count()
    total_datasets = Dataset.query.count()
    total_exports = db.session.query(db.func.sum(ExportLog.rows_exported)).scalar() or 0
    pending_document_reviews = ActorDocument.query.filter(
        ActorDocument.archived_at.is_(None),
        ActorDocument.review_status.in_(['pending', 'needs_correction', 'redaction_required']),
    ).count()
    
    recent_exports = ExportLog.query.order_by(ExportLog.exported_at.desc()).limit(10).all()
    
    return render_template('admin/dashboard.html',
                           total_users=total_users,
                           active_subs=active_subs,
                           total_datasets=total_datasets,
                           total_exports=total_exports,
                           pending_document_reviews=pending_document_reviews,
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


@admin_bp.route('/documents/review-queue')
@login_required
@admin_required
def document_review_queue():
    selected_review_status = request.args.get('review_status', '').strip()
    selected_verification_status = request.args.get('verification_status', '').strip()
    selected_document_type_id = request.args.get('document_type_id', '').strip()
    selected_partner_organization_id = request.args.get('partner_organization_id', '').strip()
    selected_extraction_status = request.args.get('extraction_status', '').strip()
    selected_risk_flag = request.args.get('risk_flag', '').strip()
    selected_consent_status = request.args.get('consent_status', '').strip()

    query = ActorDocument.query.filter(ActorDocument.archived_at.is_(None))

    if selected_review_status:
        query = query.filter(ActorDocument.review_status == selected_review_status)
    else:
        query = query.filter(ActorDocument.review_status.in_(['pending', 'needs_correction', 'redaction_required']))

    if selected_verification_status:
        query = query.filter(ActorDocument.verification_status == selected_verification_status)
    if selected_document_type_id.isdigit():
        query = query.filter(ActorDocument.document_type_id == int(selected_document_type_id))
    if selected_partner_organization_id.isdigit():
        query = query.filter(ActorDocument.partner_organization_id == int(selected_partner_organization_id))

    documents = query.order_by(ActorDocument.updated_at.desc(), ActorDocument.id.desc()).all()
    review_items = filter_admin_review_documents(
        documents,
        selected_extraction_status,
        selected_risk_flag,
        selected_consent_status,
    )

    document_types = DocumentType.query.order_by(DocumentType.category, DocumentType.name).all()
    partner_organizations = PartnerOrganization.query.order_by(PartnerOrganization.name).all()
    extraction_statuses = [
        'missing',
        'pending',
        'completed',
        'failed',
        'needs_review',
    ]
    risk_flags = sorted({
        flag
        for run in DocumentExtractionRun.query.all()
        for flag in (run.risk_flags_json or [])
    })

    return render_template(
        'admin/document_review_queue.html',
        review_items=review_items,
        document_types=document_types,
        partner_organizations=partner_organizations,
        review_statuses=ADMIN_REVIEW_STATUSES,
        verification_statuses=['unverified', 'verified', 'expired', 'rejected', 'superseded'],
        extraction_statuses=extraction_statuses,
        risk_flags=risk_flags,
        consent_statuses=[
            ('missing', 'Missing active consent'),
            ('external_blocked', 'External sharing blocked'),
            ('externally_shareable', 'External channels allowed'),
        ],
        selected_review_status=selected_review_status,
        selected_verification_status=selected_verification_status,
        selected_document_type_id=selected_document_type_id,
        selected_partner_organization_id=selected_partner_organization_id,
        selected_extraction_status=selected_extraction_status,
        selected_risk_flag=selected_risk_flag,
        selected_consent_status=selected_consent_status,
    )


@admin_bp.route('/documents/<int:document_id>/review')
@login_required
@admin_required
def document_review_detail(document_id):
    document = ActorDocument.query.get_or_404(document_id)
    context = document_admin_review_context(document)
    review_history = (
        DocumentReview.query.filter_by(actor_document_id=document.id)
        .order_by(DocumentReview.reviewed_at.desc(), DocumentReview.id.desc())
        .all()
    )
    add_admin_document_access_log(document, 'admin_review_detail', version=context['current_version'])
    db.session.commit()

    return render_template(
        'admin/document_review_detail.html',
        **context,
        review_history=review_history,
        review_actions=ADMIN_REVIEW_ACTIONS,
        verification_statuses=['unverified', 'verified', 'expired', 'rejected', 'superseded'],
    )


@admin_bp.route('/documents/<int:document_id>/preview')
@login_required
@admin_required
def preview_document(document_id):
    document = ActorDocument.query.get_or_404(document_id)
    version = current_document_version(document)
    preview_policy = admin_document_preview_policy(document, version=version)
    if not preview_policy['allowed']:
        abort(415)

    storage_path, download_name, mime_type, _extension = document_version_file_metadata(document, version=version)
    if not storage_path:
        abort(404)

    file_path = resolve_document_storage_path(storage_path)
    if not file_path.exists() or not file_path.is_file():
        abort(404)

    add_admin_document_access_log(document, 'admin_preview', version=version)
    db.session.commit()

    response = send_file(
        file_path,
        as_attachment=False,
        download_name=download_name,
        mimetype=mime_type or mimetypes.guess_type(download_name)[0],
    )
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@admin_bp.route('/documents/<int:document_id>/review/decision', methods=['POST'])
@login_required
@admin_required
def document_review_decision(document_id):
    document = ActorDocument.query.get_or_404(document_id)
    action = clean_admin_form_value('action')
    if action not in ADMIN_REVIEW_ACTIONS:
        flash('Please choose a supported review action.', 'error')
        return redirect(url_for('admin.document_review_detail', document_id=document.id))

    notes = decision_notes_for_action(action)
    if action == 'request_correction' and not notes:
        flash('Correction reason is required when requesting correction.', 'error')
        return redirect(url_for('admin.document_review_detail', document_id=document.id))
    if action == 'reject' and not notes:
        flash('Rejection reason is required when rejecting a document.', 'error')
        return redirect(url_for('admin.document_review_detail', document_id=document.id))

    before_values = document_review_snapshot(document)
    version = current_document_version(document)
    config = apply_admin_review_action(document, action, notes)

    review_entry = DocumentReview(
        actor_document_id=document.id,
        actor_document_version_id=version.id if version else None,
        reviewer_user_id=current_user.id,
        status=config['review_entry_status'],
        notes=notes or None,
        reviewed_at=datetime.utcnow(),
    )
    db.session.add(review_entry)
    db.session.flush()

    after_values = document_review_snapshot(document)
    after_values.update({
        'review_entry_id': review_entry.id,
        'review_action': action,
        'actor_id': document.market_actor_id,
        'partner_organization_id': document.partner_organization_id,
        'external_subscriber_access_changed': before_values['subscriber_access_level'] != after_values['subscriber_access_level'],
        'external_visibility_changed': before_values['visibility_level'] != after_values['visibility_level'],
    })
    add_admin_document_audit(
        document,
        config['audit_action'],
        before_values={
            'document': before_values,
            'actor_id': document.market_actor_id,
            'partner_organization_id': document.partner_organization_id,
        },
        after_values=after_values,
    )
    db.session.commit()

    flash('Admin document review decision saved.', 'success')
    return redirect(url_for('admin.document_review_detail', document_id=document.id))


@admin_bp.route('/users')
@login_required
@admin_required
def users():
    all_users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=all_users)


def parse_reference_option_form(existing_option=None):
    errors = []
    category = request.form.get('category', '').strip()
    code = request.form.get('code', '').strip().lower().replace(' ', '_')
    label = request.form.get('label', '').strip()
    description = request.form.get('description', '').strip()
    metadata_text = request.form.get('metadata_json', '').strip()

    try:
        sort_order = int(request.form.get('sort_order') or 0)
    except ValueError:
        sort_order = 0
        errors.append('Sort order must be a number.')

    if existing_option:
        category = existing_option.category
        code = existing_option.code
    else:
        if category not in REFERENCE_OPTION_CATEGORIES:
            errors.append('Please choose a supported reference category.')
        if not code:
            errors.append('Code is required.')

    if not label:
        errors.append('Label is required.')

    metadata_json = None
    if metadata_text:
        try:
            metadata_json = json.loads(metadata_text)
        except json.JSONDecodeError:
            errors.append('Metadata must be valid JSON.')

    return errors, {
        'category': category,
        'code': code,
        'label': label,
        'description': description or None,
        'sort_order': sort_order,
        'active': request.form.get('active') == 'true',
        'is_default': request.form.get('is_default') == 'true',
        'metadata_json': metadata_json,
        'metadata_text': metadata_text,
    }


def apply_reference_option_values(option, values):
    option.category = values['category']
    option.code = values['code']
    option.label = values['label']
    option.description = values['description']
    option.sort_order = values['sort_order']
    option.active = values['active']
    option.is_default = values['is_default']
    option.metadata_json = values['metadata_json']


def clear_other_default_options(option):
    if not option.is_default:
        return

    ReferenceOption.query.filter(
        ReferenceOption.category == option.category,
        ReferenceOption.id != option.id,
    ).update({'is_default': False})


@admin_bp.route('/reference-options')
@login_required
@admin_required
def reference_options():
    selected_category = request.args.get('category', '').strip()
    query = ReferenceOption.query
    if selected_category:
        query = query.filter_by(category=selected_category)

    options = query.order_by(ReferenceOption.category, ReferenceOption.sort_order, ReferenceOption.label).all()
    return render_template(
        'admin/reference_options.html',
        options=options,
        categories=REFERENCE_OPTION_CATEGORIES,
        selected_category=selected_category,
    )


@admin_bp.route('/reference-options/new', methods=['GET', 'POST'])
@login_required
@admin_required
def new_reference_option():
    if request.method == 'POST':
        errors, values = parse_reference_option_form()
        if not errors:
            existing = ReferenceOption.query.filter_by(category=values['category'], code=values['code']).first()
            if existing:
                errors.append('A reference option with this category and code already exists.')

        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('admin/reference_option_form.html', option=None, categories=REFERENCE_OPTION_CATEGORIES, values=values)

        option = ReferenceOption()
        apply_reference_option_values(option, values)
        db.session.add(option)
        db.session.flush()
        clear_other_default_options(option)
        db.session.commit()

        flash('Reference option created.', 'success')
        return redirect(url_for('admin.reference_options', category=option.category))

    return render_template('admin/reference_option_form.html', option=None, categories=REFERENCE_OPTION_CATEGORIES, values={})


@admin_bp.route('/reference-options/<int:option_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_reference_option(option_id):
    option = ReferenceOption.query.get_or_404(option_id)

    if request.method == 'POST':
        errors, values = parse_reference_option_form(existing_option=option)
        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('admin/reference_option_form.html', option=option, categories=REFERENCE_OPTION_CATEGORIES, values=values)

        apply_reference_option_values(option, values)
        clear_other_default_options(option)
        db.session.commit()

        flash('Reference option updated.', 'success')
        return redirect(url_for('admin.reference_options', category=option.category))

    values = {
        'category': option.category,
        'code': option.code,
        'label': option.label,
        'description': option.description,
        'sort_order': option.sort_order,
        'active': option.active,
        'is_default': option.is_default,
        'metadata_text': json.dumps(option.metadata_json, indent=2) if option.metadata_json else '',
    }
    return render_template('admin/reference_option_form.html', option=option, categories=REFERENCE_OPTION_CATEGORIES, values=values)


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
