"""Admin routes"""

import csv
import io
import json
import mimetypes
from collections import Counter
from datetime import datetime, timedelta
from flask import Blueprint, abort, render_template, redirect, send_file, url_for, flash, request
from flask_login import login_required, current_user
from functools import wraps
from models import (
    ActorConsentRecord,
    ActorDocument,
    ApiClient,
    ApiKey,
    ApiUsageEvent,
    AuditLog,
    COMMERCIAL_FULFILMENT_ACTION_TYPES,
    COMMERCIAL_REQUEST_STATUSES,
    CommercialFulfilmentAction,
    CommercialRequest,
    DOCUMENT_ACCESS_FULFILMENT_ACTION_TYPES,
    DOCUMENT_ACCESS_REQUEST_STATUSES,
    DocumentAccessLog,
    DocumentAccessFulfilmentAction,
    DocumentAccessRequest,
    DocumentExtractionRun,
    DocumentFieldReconciliation,
    DocumentPublishControl,
    DocumentReview,
    DocumentType,
    DOCUMENT_PUBLISH_CONTROL_STATUSES,
    DOCUMENT_PUBLISH_TARGETS,
    DOCUMENT_REDACTION_STATUSES,
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
    LicensedPack,
    LiveIntelligenceAccess,
    ReferenceOption,
    REFERENCE_OPTION_CATEGORIES,
    get_region_from_state,
    NIGERIA_REGIONS,
    actor_can_share_documents,
    consent_document_category_for_document_type,
    get_active_actor_consent,
)
from document_access import (
    ACCESS_REQUEST_TARGET_BY_TYPE,
    document_metadata_access_decision,
    document_publish_control,
    request_target_allows,
    safe_document_metadata_payload,
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

DOCUMENT_REDACTION_STATUS_OPTIONS = [
    ('not_required', 'Not Required'),
    ('required', 'Required'),
    ('in_progress', 'In Progress'),
    ('completed', 'Completed'),
    ('waived', 'Waived'),
    ('failed', 'Failed'),
    ('not_redacted', 'Legacy: Not Redacted'),
    ('redaction_required', 'Legacy: Redaction Required'),
]

DOCUMENT_PUBLISH_TARGET_CONFIG = [
    {
        'code': 'verified_metadata',
        'label': 'Verified Metadata',
        'description': 'Internal verified document metadata eligibility for future controlled publish flows.',
        'channel': 'admin_review',
        'requires_file': False,
        'requires_redaction': False,
    },
    {
        'code': 'licensed_data_pack_metadata',
        'label': 'Licensed Data Pack Metadata',
        'description': 'Eligibility for future licensed data pack metadata inclusion.',
        'channel': 'licensed_data_pack',
        'requires_file': False,
        'requires_redaction': False,
    },
    {
        'code': 'live_intelligence_metadata',
        'label': 'Live Intelligence Metadata',
        'description': 'Eligibility for future live intelligence metadata inclusion.',
        'channel': 'live_intelligence',
        'requires_file': False,
        'requires_redaction': False,
    },
    {
        'code': 'subscriber_portal_metadata',
        'label': 'Subscriber Portal Metadata',
        'description': 'Eligibility for future subscriber-facing document metadata.',
        'channel': 'subscriber_portal',
        'requires_file': False,
        'requires_redaction': False,
    },
    {
        'code': 'api_metadata',
        'label': 'API Metadata',
        'description': 'Eligibility for future API document metadata output.',
        'channel': 'api',
        'requires_file': False,
        'requires_redaction': False,
    },
    {
        'code': 'redacted_document_candidate',
        'label': 'Redacted Document Candidate',
        'description': 'Eligibility marker for a future redacted document access workflow.',
        'channel': 'subscriber_portal',
        'requires_file': True,
        'requires_redaction': True,
    },
    {
        'code': 'full_document_restricted_candidate',
        'label': 'Full Document Restricted Candidate',
        'description': 'Eligibility marker for future approved buyer due-diligence access.',
        'channel': 'approved_buyer_due_diligence',
        'requires_file': True,
        'requires_redaction': True,
    },
]

DOCUMENT_PUBLISH_TARGET_CONFIG_BY_CODE = {
    config['code']: config
    for config in DOCUMENT_PUBLISH_TARGET_CONFIG
}

DOCUMENT_HIGH_RISK_FLAGS = {
    'expired_document',
    'metadata_mismatch',
    'missing_reference_number',
    'missing_issuing_body',
    'no_fields_extracted',
}

REDACTION_CLEAR_STATUSES = {'not_required', 'completed', 'waived'}

COMMERCIAL_DECISION_STATUSES = [
    'in_review',
    'contacted',
    'approved_for_fulfilment',
    'rejected',
    'closed',
    'cancelled',
]

COMMERCIAL_STATUS_LABELS = {
    status: status.replace('_', ' ').title()
    for status in COMMERCIAL_REQUEST_STATUSES
}

COMMERCIAL_FULFILMENT_LABELS = {
    'api_client_setup': 'API Client Setup Record',
    'live_intelligence_access': 'Live Intelligence Access',
    'upgrade_followup': 'Upgrade Follow-up',
    'manual_note': 'Manual Note',
}

COMMERCIAL_FULFILMENT_REQUEST_TYPES = {
    'api_client_setup': 'api_access',
    'live_intelligence_access': 'live_intelligence',
    'upgrade_followup': 'upgrade',
}

DUE_DILIGENCE_DECISION_STATUSES = [
    'in_review',
    'needs_information',
    'approved_for_redacted_access',
    'rejected',
    'closed',
    'cancelled',
]

DUE_DILIGENCE_STATUS_LABELS = {
    status: status.replace('_', ' ').title()
    for status in DOCUMENT_ACCESS_REQUEST_STATUSES
}

DUE_DILIGENCE_FULFILMENT_LABELS = {
    'redacted_access_recorded': 'Redacted Access Fulfilment Recorded',
    'restricted_full_document_review_recorded': 'Restricted Full-Document Review Recorded',
    'manual_note': 'Manual Note',
}

DUE_DILIGENCE_VISIBILITY_LABELS = {
    'metadata_only': 'Metadata Only Visibility',
    'redacted_document_candidate': 'Redacted Access Candidate',
    'full_document_restricted_candidate': 'Restricted Full-Document Candidate',
}

COMMERCIAL_REPORT_WINDOWS = {
    '7d': {'label': 'Last 7 days', 'days': 7},
    '30d': {'label': 'Last 30 days', 'days': 30},
    '90d': {'label': 'Last 90 days', 'days': 90},
    'all': {'label': 'All time', 'days': None},
}

COMMERCIAL_REPORT_DEFAULT_WINDOW = '30d'

COMMERCIAL_REPORT_OPEN_STATUSES = {
    'pending',
    'in_review',
    'contacted',
    'approved_for_fulfilment',
}

DUE_DILIGENCE_REPORT_OPEN_STATUSES = {
    'pending',
    'in_review',
    'needs_information',
    'approved_for_redacted_access',
}

COMMERCIAL_REPORT_CONVERSION_STATUSES = {
    'approved_for_fulfilment',
    'closed',
}


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


def document_publish_control_snapshot(control):
    if not control:
        return None
    return {
        'id': control.id,
        'actor_document_id': control.actor_document_id,
        'publish_target': control.publish_target,
        'status': control.status,
        'admin_decision': control.admin_decision,
        'notes': control.notes,
        'blocking_reasons_json': control.blocking_reasons_json or [],
        'decided_by_user_id': control.decided_by_user_id,
        'decided_at': control.decided_at.isoformat() if control.decided_at else None,
        'last_evaluated_at': control.last_evaluated_at.isoformat() if control.last_evaluated_at else None,
    }


def add_publish_check(checks, blocking_reasons, blocking_keys, key, label, passed, message, required=True, status=None):
    check_status = status or ('pass' if passed else ('fail' if required else 'warning'))
    check = {
        'key': key,
        'label': label,
        'status': check_status,
        'required': required,
        'message': message,
    }
    checks.append(check)
    if required and check_status == 'fail':
        blocking_reasons.append(message)
        blocking_keys.append(key)


def document_private_file_exists(document, version=None):
    storage_path, _download_name, _mime_type, _extension = document_version_file_metadata(document, version=version)
    if not storage_path:
        return False
    try:
        file_path = resolve_document_storage_path(storage_path)
    except Exception:
        return False
    return file_path.exists() and file_path.is_file()


def normalized_redaction_status(document):
    return document.redaction_status or 'not_redacted'


def redaction_is_acceptable_for_target(document, target_code, target_config):
    redaction_status = normalized_redaction_status(document)
    document_is_sensitive = bool(document.document_type and document.document_type.sensitive)
    redaction_required = bool(target_config['requires_redaction'] or document_is_sensitive)

    if not redaction_required:
        return True, 'Redaction is not required for this non-sensitive metadata target.'
    if target_code == 'redacted_document_candidate':
        if redaction_status == 'completed':
            return True, 'Redaction is completed for this redacted document candidate.'
        return False, 'Redaction must be completed before this document can be marked as a redacted document candidate.'
    if redaction_status in REDACTION_CLEAR_STATUSES:
        return True, 'Redaction status is acceptable for this target.'
    return False, 'Redaction is required, in progress, failed, or not yet resolved for this target.'


def extraction_is_acceptable(extraction_run, reconciliation_rows):
    if not extraction_run:
        return False, 'No extraction run exists for this document.'
    if extraction_run.status != 'completed':
        return False, 'Latest extraction run is not completed.'
    if extraction_run.document_intelligence_status not in {'extracted', 'reconciled'}:
        return False, 'Document intelligence status is not extracted or reconciled.'
    pending_count = len([row for row in reconciliation_rows if row.status == 'pending'])
    if pending_count:
        return False, f'{pending_count} reconciliation row(s) are still pending.'
    return True, 'Extraction and reconciliation are acceptable.'


def expiry_is_acceptable(document, extraction_run):
    today = datetime.utcnow().date()
    if document.expires_at and document.expires_at < today:
        return False, 'Document expiry date is in the past.'
    if document.document_type and document.document_type.requires_expiry_date and not document.expires_at:
        return False, 'This document type requires an expiry date.'

    expiry_readiness = extraction_run.expiry_renewal_json if extraction_run and extraction_run.expiry_renewal_json else {}
    if expiry_readiness.get('status') == 'expired':
        return False, 'Extraction expiry readiness marks this document as expired.'
    return True, 'Document expiry readiness is acceptable.'


def evaluate_publish_readiness(document, target_code):
    target_config = DOCUMENT_PUBLISH_TARGET_CONFIG_BY_CODE.get(target_code)
    if not target_config:
        abort(404)

    checks = []
    blocking_reasons = []
    blocking_keys = []
    actor = document.market_actor
    document_category = consent_document_category_for_document_type(document.document_type)
    active_consent = get_active_actor_consent(actor)
    consent_document_categories = active_consent.permitted_document_categories_json if active_consent else []
    consent_channels = active_consent.sharing_channels_json if active_consent else []
    extraction_run = latest_document_extraction_run(document)
    reconciliation_rows = reconciliation_rows_for_run(extraction_run)
    version = current_document_version(document)

    add_publish_check(
        checks,
        blocking_reasons,
        blocking_keys,
        'active_consent',
        'Active actor consent',
        active_consent is not None,
        'Active actor consent exists.' if active_consent else 'No active actor consent exists.',
    )
    add_publish_check(
        checks,
        blocking_reasons,
        blocking_keys,
        'consent_document_category',
        'Consent allows document category',
        document_category in consent_document_categories,
        f'Consent allows {document_category}.' if document_category in consent_document_categories else f'Consent does not allow document category {document_category}.',
    )
    add_publish_check(
        checks,
        blocking_reasons,
        blocking_keys,
        'consent_sharing_channel',
        'Consent allows sharing channel',
        target_config['channel'] in consent_channels,
        f"Consent allows {target_config['channel']}." if target_config['channel'] in consent_channels else f"Consent does not allow sharing channel {target_config['channel']}.",
    )
    add_publish_check(
        checks,
        blocking_reasons,
        blocking_keys,
        'admin_review',
        'Admin review approved',
        document.review_status == 'approved' and document.document_status == 'approved',
        'Admin review and document status are approved.' if document.review_status == 'approved' and document.document_status == 'approved' else 'Admin review/document status is not approved.',
    )
    add_publish_check(
        checks,
        blocking_reasons,
        blocking_keys,
        'verification_status',
        'Verification status acceptable',
        document.verification_status == 'verified',
        'Document is verified.' if document.verification_status == 'verified' else 'Document verification status is not verified.',
    )

    expiry_ok, expiry_message = expiry_is_acceptable(document, extraction_run)
    add_publish_check(
        checks,
        blocking_reasons,
        blocking_keys,
        'expiry_readiness',
        'Expiry readiness',
        expiry_ok,
        expiry_message,
    )

    extraction_ok, extraction_message = extraction_is_acceptable(extraction_run, reconciliation_rows)
    add_publish_check(
        checks,
        blocking_reasons,
        blocking_keys,
        'extraction_reconciliation',
        'Extraction and reconciliation',
        extraction_ok,
        extraction_message,
    )

    redaction_ok, redaction_message = redaction_is_acceptable_for_target(document, target_code, target_config)
    add_publish_check(
        checks,
        blocking_reasons,
        blocking_keys,
        'redaction_status',
        'Redaction status',
        redaction_ok,
        redaction_message,
    )

    if target_config['requires_file']:
        file_exists = document_private_file_exists(document, version=version)
        add_publish_check(
            checks,
            blocking_reasons,
            blocking_keys,
            'private_file_exists',
            'Private file exists',
            file_exists,
            'Private current-version file exists.' if file_exists else 'Private current-version file is missing.',
        )
    else:
        checks.append({
            'key': 'private_file_exists',
            'label': 'Private file exists',
            'status': 'not_applicable',
            'required': False,
            'message': 'Private file existence is not required for metadata-only targets.',
        })

    risk_flags = extraction_run.risk_flags_json if extraction_run and extraction_run.risk_flags_json else []
    high_risk_flags = [flag for flag in risk_flags if flag in DOCUMENT_HIGH_RISK_FLAGS]
    add_publish_check(
        checks,
        blocking_reasons,
        blocking_keys,
        'high_risk_flags',
        'Unresolved high-risk flags',
        not high_risk_flags,
        'No unresolved high-risk flags are present.' if not high_risk_flags else f"Unresolved high-risk flags: {', '.join(high_risk_flags)}.",
    )

    return {
        'target': target_config,
        'target_code': target_code,
        'document_category': document_category,
        'checks': checks,
        'blocking_reasons': blocking_reasons,
        'blocking_keys': blocking_keys,
        'computed_status': 'ready' if not blocking_reasons else 'blocked',
        'active_consent': active_consent,
        'extraction_run': extraction_run,
        'reconciliation_rows': reconciliation_rows,
        'risk_flags': risk_flags,
        'high_risk_flags': high_risk_flags,
    }


def get_or_create_publish_control(document, target_code):
    control = DocumentPublishControl.query.filter_by(
        actor_document_id=document.id,
        publish_target=target_code,
    ).first()
    if control:
        return control

    control = DocumentPublishControl(
        actor_document_id=document.id,
        publish_target=target_code,
        status='not_evaluated',
        readiness_checks_json=[],
        blocking_reasons_json=[],
    )
    db.session.add(control)
    db.session.flush()
    return control


def persist_publish_control_evaluation(document, target_code, evaluation, admin_decision='evaluated', notes=None, status=None):
    control = get_or_create_publish_control(document, target_code)
    now = datetime.utcnow()
    control.status = status or evaluation['computed_status']
    control.readiness_checks_json = evaluation['checks']
    control.blocking_reasons_json = evaluation['blocking_reasons']
    control.admin_decision = admin_decision
    if notes is not None:
        control.notes = notes or None
    control.decided_by_user_id = current_user.id
    control.decided_at = now
    control.last_evaluated_at = now
    return control


def publish_control_context(document):
    target_items = []
    for target_code in DOCUMENT_PUBLISH_TARGETS:
        evaluation = evaluate_publish_readiness(document, target_code)
        control = DocumentPublishControl.query.filter_by(
            actor_document_id=document.id,
            publish_target=target_code,
        ).first()
        target_items.append({
            **evaluation,
            'control': control,
            'stored_status': control.status if control else 'not_evaluated',
            'stored_blocking_reasons': control.blocking_reasons_json if control else [],
        })
    return target_items


def add_admin_publish_control_audit(document, control, action, before_values, after_values):
    db.session.add(AuditLog(
        user_id=current_user.id,
        organization_type='partner_organization',
        organization_id=document.partner_organization_id,
        action=action,
        entity_type='document_publish_control',
        entity_id=control.id if control else None,
        before_values=before_values,
        after_values=after_values,
        ip_address=request.headers.get('X-Forwarded-For', request.remote_addr),
        user_agent=request.headers.get('User-Agent'),
    ))


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


def commercial_request_snapshot(commercial_request):
    return {
        'id': commercial_request.id,
        'user_id': commercial_request.user_id,
        'request_type': commercial_request.request_type,
        'requested_product': commercial_request.requested_product,
        'dataset_code': commercial_request.dataset_code,
        'region_code': commercial_request.region_code,
        'crop_name': commercial_request.crop_name,
        'status': commercial_request.status,
        'reviewed_by_user_id': commercial_request.reviewed_by_user_id,
        'reviewed_at': commercial_request.reviewed_at.isoformat() if commercial_request.reviewed_at else None,
        'review_notes': commercial_request.review_notes,
    }


def add_admin_commercial_request_audit(commercial_request, action, before_values=None, after_values=None):
    db.session.add(AuditLog(
        user_id=current_user.id,
        organization_type='commercial_operations',
        organization_id=commercial_request.user_id,
        action=action,
        entity_type='commercial_request',
        entity_id=commercial_request.id,
        before_values=before_values,
        after_values=after_values,
        ip_address=request.headers.get('X-Forwarded-For', request.remote_addr),
        user_agent=request.headers.get('User-Agent'),
    ))


def commercial_request_queue_counts():
    counts = {}
    for status in COMMERCIAL_REQUEST_STATUSES:
        counts[status] = CommercialRequest.query.filter_by(status=status).count()
    return counts


def commercial_request_related_context(commercial_request):
    api_clients = []
    live_accesses = []
    if commercial_request.user_id:
        api_clients = (
            ApiClient.query.filter_by(owner_user_id=commercial_request.user_id)
            .order_by(ApiClient.created_at.desc())
            .limit(20)
            .all()
        )
        live_accesses = (
            LiveIntelligenceAccess.query.filter_by(user_id=commercial_request.user_id)
            .order_by(LiveIntelligenceAccess.created_at.desc())
            .limit(20)
            .all()
        )
    fulfilment_actions = (
        CommercialFulfilmentAction.query.filter_by(commercial_request_id=commercial_request.id)
        .order_by(CommercialFulfilmentAction.created_at.desc(), CommercialFulfilmentAction.id.desc())
        .all()
    )
    return {
        'api_clients': api_clients,
        'live_accesses': live_accesses,
        'fulfilment_history': fulfilment_actions,
    }


def block_commercial_fulfilment(commercial_request, action_type, reason):
    add_admin_commercial_request_audit(
        commercial_request,
        'admin_commercial_request_fulfilment_blocked',
        before_values=commercial_request_snapshot(commercial_request),
        after_values={
            'action_type': action_type,
            'reason': reason,
            'api_client_created': False,
            'api_key_created': False,
            'live_intelligence_access_created': False,
            'payment_flow_changed': False,
        },
    )


def commercial_api_client_slug(commercial_request):
    return f"commercial-request-{commercial_request.id}-api-client"


def commercial_api_client_name(commercial_request):
    owner = commercial_request.organization_name or (commercial_request.user.email if commercial_request.user else 'Subscriber')
    return f"{owner} API Metadata Client"


def parse_commercial_date(field_name):
    value = clean_admin_form_value(field_name)
    if not value:
        return None
    return datetime.strptime(value, '%Y-%m-%d')


def parse_commercial_crops():
    crops_text = clean_admin_form_value('crops')
    return [crop.strip() for crop in crops_text.split(',') if crop.strip()]


def create_commercial_fulfilment_action(commercial_request, action_type, notes, resulting_api_client=None, resulting_live_access=None, metadata=None):
    fulfilment_action = CommercialFulfilmentAction(
        commercial_request_id=commercial_request.id,
        action_type=action_type,
        status='recorded',
        notes=notes,
        performed_by_user_id=current_user.id,
        resulting_api_client_id=resulting_api_client.id if resulting_api_client else None,
        resulting_live_intelligence_access_id=resulting_live_access.id if resulting_live_access else None,
        metadata_json=metadata or {},
    )
    db.session.add(fulfilment_action)
    db.session.flush()
    add_admin_commercial_request_audit(
        commercial_request,
        'admin_commercial_request_fulfilment_recorded',
        before_values=None,
        after_values={
            'fulfilment_action_id': fulfilment_action.id,
            'action_type': action_type,
            'resulting_api_client_id': fulfilment_action.resulting_api_client_id,
            'resulting_live_intelligence_access_id': fulfilment_action.resulting_live_intelligence_access_id,
            'api_key_created': False,
            'api_secret_exposed': False,
            'api_key_hash_exposed': False,
            'payment_flow_changed': False,
            'auto_granted_on_submission': False,
            **(metadata or {}),
        },
    )
    return fulfilment_action


def ensure_api_client_setup_record(commercial_request, notes):
    slug = commercial_api_client_slug(commercial_request)
    api_client = ApiClient.query.filter_by(slug=slug).first()
    created = False
    if not api_client:
        requested_scopes = []
        if isinstance(commercial_request.context_json, dict):
            requested_scopes = commercial_request.context_json.get('requested_scopes') or []
        api_client = ApiClient(
            name=commercial_api_client_name(commercial_request),
            slug=slug,
            owner_user_id=commercial_request.user_id,
            status='pending',
            scopes=requested_scopes or ['document_metadata:read'],
            notes=f"Created from commercial request #{commercial_request.id}. No API keys are created by Phase 4.2 fulfilment.",
        )
        db.session.add(api_client)
        db.session.flush()
        created = True
    create_commercial_fulfilment_action(
        commercial_request,
        'api_client_setup',
        notes,
        resulting_api_client=api_client,
        metadata={
            'api_client_created': created,
            'api_client_status': api_client.status,
            'api_key_created': False,
            'raw_secret_available': False,
        },
    )
    return api_client


def create_or_update_live_intelligence_from_request(commercial_request, notes):
    start = parse_commercial_date('start_date')
    end = parse_commercial_date('end_date')
    regions = request.form.getlist('regions')
    crops = parse_commercial_crops()
    if not start or not end:
        raise ValueError('Start date and end date are required for Live Intelligence fulfilment.')
    if end <= start:
        raise ValueError('End date must be after start date.')
    if not regions:
        raise ValueError('Select at least one region for Live Intelligence fulfilment.')

    live_access = None
    existing_id = clean_admin_form_value('live_access_id')
    if existing_id:
        live_access = LiveIntelligenceAccess.query.filter_by(
            id=int(existing_id),
            user_id=commercial_request.user_id,
        ).first()
    if not live_access:
        live_access = LiveIntelligenceAccess(user_id=commercial_request.user_id)
        db.session.add(live_access)

    live_access.regions_allowed = len(regions)
    live_access.crops_allowed = len(crops) if crops else None
    live_access.regions_selected = regions
    live_access.crops_selected = crops
    live_access.start_date = start
    live_access.end_date = end
    live_access.active = True
    live_access.notes = notes or f"Created from commercial request #{commercial_request.id}."
    db.session.flush()

    create_commercial_fulfilment_action(
        commercial_request,
        'live_intelligence_access',
        notes,
        resulting_live_access=live_access,
        metadata={
            'live_intelligence_access_id': live_access.id,
            'regions_selected': regions,
            'crops_selected': crops,
            'active': live_access.active,
            'explicit_admin_fulfilment': True,
        },
    )
    return live_access


def due_diligence_request_snapshot(access_request):
    return {
        'id': access_request.id,
        'actor_document_id': access_request.actor_document_id,
        'user_id': access_request.user_id,
        'api_client_id': access_request.api_client_id,
        'request_type': access_request.request_type,
        'request_channel': access_request.request_channel,
        'organization_name': access_request.organization_name,
        'status': access_request.status,
        'reviewed_by_user_id': access_request.reviewed_by_user_id,
        'reviewed_at': access_request.reviewed_at.isoformat() if access_request.reviewed_at else None,
        'review_notes': access_request.review_notes,
    }


def add_admin_due_diligence_audit(access_request, action, before_values=None, after_values=None):
    db.session.add(AuditLog(
        user_id=current_user.id,
        organization_type='due_diligence',
        organization_id=access_request.user_id,
        action=action,
        entity_type='document_access_request',
        entity_id=access_request.id,
        before_values=before_values,
        after_values=after_values,
        ip_address=request.headers.get('X-Forwarded-For', request.remote_addr),
        user_agent=request.headers.get('User-Agent'),
    ))


def due_diligence_request_counts():
    counts = {}
    for status in DOCUMENT_ACCESS_REQUEST_STATUSES:
        counts[status] = DocumentAccessRequest.query.filter_by(status=status).count()
    return counts


def due_diligence_review_history(access_request):
    return (
        AuditLog.query.filter_by(entity_type='document_access_request', entity_id=access_request.id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .all()
    )


def due_diligence_fulfilment_history(access_request):
    return (
        DocumentAccessFulfilmentAction.query.filter_by(document_access_request_id=access_request.id)
        .order_by(DocumentAccessFulfilmentAction.created_at.desc(), DocumentAccessFulfilmentAction.id.desc())
        .all()
    )


def due_diligence_request_context(access_request):
    document = access_request.actor_document
    user = access_request.user
    metadata_allowed = False
    metadata_reasons = ['No requester user is linked to this access request.']
    metadata_control = None
    extraction_run = None
    if user and document:
        metadata_allowed, metadata_reasons, metadata_control, extraction_run = document_metadata_access_decision(
            user,
            document,
            'subscriber_portal',
        )

    target_allowed = False
    target_reason = 'No document is linked to this access request.'
    target_control = None
    if document:
        target_allowed, target_reason, target_control = request_target_allows(document, access_request.request_type)

    document_category = consent_document_category_for_document_type(document.document_type) if document else None
    actor = document.market_actor if document else None
    active_consent = get_active_actor_consent(actor)
    consent_ok = bool(document and actor_can_share_documents(actor, 'subscriber_portal', document_category))
    buyer_consent_ok = bool(document and actor_can_share_documents(actor, 'approved_buyer_due_diligence', document_category))

    redacted_control = document_publish_control(document, 'redacted_document_candidate') if document else None
    full_control = document_publish_control(document, 'full_document_restricted_candidate') if document else None
    safe_metadata = safe_document_metadata_payload(document, 'subscriber_portal', publish_control=metadata_control) if document else {}

    return {
        'document': document,
        'safe_metadata': safe_metadata,
        'metadata_allowed': metadata_allowed,
        'metadata_reasons': metadata_reasons,
        'metadata_control': metadata_control,
        'target_allowed': target_allowed,
        'target_reason': target_reason,
        'target_control': target_control,
        'target_code': ACCESS_REQUEST_TARGET_BY_TYPE.get(access_request.request_type),
        'redacted_control': redacted_control,
        'full_control': full_control,
        'document_category': document_category,
        'active_consent': active_consent,
        'consent_ok': consent_ok,
        'buyer_consent_ok': buyer_consent_ok,
        'extraction_run': extraction_run,
        'approval_allowed': bool(metadata_allowed and target_allowed),
        'review_history': due_diligence_review_history(access_request),
        'fulfilment_history': due_diligence_fulfilment_history(access_request),
    }


def block_due_diligence_decision(access_request, requested_status, context, reason):
    add_admin_due_diligence_audit(
        access_request,
        'admin_due_diligence_decision_blocked',
        before_values=due_diligence_request_snapshot(access_request),
        after_values={
            'requested_status': requested_status,
            'reason': reason,
            'metadata_allowed': context.get('metadata_allowed'),
            'metadata_reasons': context.get('metadata_reasons'),
            'target_allowed': context.get('target_allowed'),
            'target_reason': context.get('target_reason'),
            'access_granted': False,
            'file_exposed': False,
        },
    )


def block_due_diligence_fulfilment(access_request, action_type, context, reason):
    add_admin_due_diligence_audit(
        access_request,
        'admin_due_diligence_fulfilment_blocked',
        before_values=due_diligence_request_snapshot(access_request),
        after_values={
            'action_type': action_type,
            'reason': reason,
            'metadata_allowed': context.get('metadata_allowed'),
            'target_allowed': context.get('target_allowed'),
            'file_exposed': False,
            'storage_path_exposed': False,
        },
    )


def create_due_diligence_fulfilment_action(access_request, action_type, notes, visibility_level, context):
    fulfilment_action = DocumentAccessFulfilmentAction(
        document_access_request_id=access_request.id,
        action_type=action_type,
        status='recorded',
        visibility_level=visibility_level,
        notes=notes,
        performed_by_user_id=current_user.id,
        metadata_json={
            'target_code': context.get('target_code'),
            'metadata_allowed': context.get('metadata_allowed'),
            'target_allowed': context.get('target_allowed'),
            'file_exposed': False,
            'download_created': False,
            'storage_path_exposed': False,
            'original_filename_exposed': False,
            'hash_exposed': False,
        },
    )
    db.session.add(fulfilment_action)
    db.session.flush()

    if access_request.actor_document:
        db.session.add(DocumentAccessLog(
            actor_document_id=access_request.actor_document_id,
            user_id=access_request.user_id,
            api_client_id=access_request.api_client_id,
            access_type='admin_due_diligence_fulfilment_recorded',
            access_channel='admin_due_diligence',
            subscriber_organization_name=access_request.organization_name,
            visibility_level=visibility_level,
            ip_address=request.headers.get('X-Forwarded-For', request.remote_addr),
            user_agent=request.headers.get('User-Agent'),
        ))

    add_admin_due_diligence_audit(
        access_request,
        'admin_due_diligence_fulfilment_recorded',
        before_values=None,
        after_values={
            'fulfilment_action_id': fulfilment_action.id,
            'action_type': action_type,
            'visibility_level': visibility_level,
            'target_code': context.get('target_code'),
            'file_exposed': False,
            'download_created': False,
            'storage_path_exposed': False,
            'payment_flow_changed': False,
        },
    )
    return fulfilment_action


def commercial_report_window_context(window_key=None):
    selected = window_key or request.args.get('window', COMMERCIAL_REPORT_DEFAULT_WINDOW).strip()
    if selected not in COMMERCIAL_REPORT_WINDOWS:
        selected = COMMERCIAL_REPORT_DEFAULT_WINDOW
    config = COMMERCIAL_REPORT_WINDOWS[selected]
    cutoff = None
    if config['days'] is not None:
        cutoff = datetime.utcnow() - timedelta(days=config['days'])
    return {
        'key': selected,
        'label': config['label'],
        'cutoff': cutoff,
        'options': [
            {'key': key, 'label': value['label']}
            for key, value in COMMERCIAL_REPORT_WINDOWS.items()
        ],
    }


def report_filter_created(query, model, cutoff):
    if cutoff is not None:
        return query.filter(model.created_at >= cutoff)
    return query


def report_unknown(value):
    return value if value not in (None, '') else 'Unspecified'


def report_count_items(records, field_name, limit=None):
    counter = Counter(report_unknown(getattr(record, field_name, None)) for record in records)
    items = [
        {'label': label, 'count': count}
        for label, count in sorted(counter.items(), key=lambda item: (-item[1], str(item[0])))
    ]
    return items[:limit] if limit else items


def report_date_items(records, field_name='created_at', limit=None):
    counter = Counter()
    for record in records:
        value = getattr(record, field_name, None)
        label = value.strftime('%Y-%m-%d') if value else 'Unknown date'
        counter[label] += 1
    items = [
        {'label': label, 'count': count}
        for label, count in sorted(counter.items(), key=lambda item: item[0], reverse=True)
    ]
    return items[:limit] if limit else items


def report_percentage(numerator, denominator):
    if not denominator:
        return 0
    return round((numerator / denominator) * 100, 1)


def commercial_request_scope_label(commercial_request):
    return (
        commercial_request.requested_product
        or commercial_request.dataset_code
        or commercial_request.region_code
        or commercial_request.crop_name
        or 'General request'
    )


def safe_commercial_followup_item(commercial_request):
    return {
        'id': commercial_request.id,
        'kind': commercial_request.request_type.replace('_', ' ').title(),
        'status': commercial_request.status.replace('_', ' ').title() if commercial_request.status else 'Unknown',
        'scope': commercial_request_scope_label(commercial_request),
        'created_at': commercial_request.created_at,
        'age_days': (datetime.utcnow() - commercial_request.created_at).days if commercial_request.created_at else None,
        'url': url_for('admin.commercial_request_detail', request_id=commercial_request.id),
    }


def safe_due_diligence_followup_item(access_request):
    return {
        'id': access_request.id,
        'kind': access_request.request_type.replace('_', ' ').title() if access_request.request_type else 'Document Access',
        'status': access_request.status.replace('_', ' ').title() if access_request.status else 'Unknown',
        'scope': access_request.organization_name or f"Request #{access_request.id}",
        'created_at': access_request.created_at,
        'age_days': (datetime.utcnow() - access_request.created_at).days if access_request.created_at else None,
        'url': url_for('admin.due_diligence_request_detail', request_id=access_request.id),
    }


def build_commercial_report_context(window_key=None):
    window = commercial_report_window_context(window_key=window_key)
    cutoff = window['cutoff']

    commercial_requests = report_filter_created(
        CommercialRequest.query,
        CommercialRequest,
        cutoff,
    ).order_by(CommercialRequest.created_at.desc(), CommercialRequest.id.desc()).all()
    due_diligence_requests = report_filter_created(
        DocumentAccessRequest.query,
        DocumentAccessRequest,
        cutoff,
    ).order_by(DocumentAccessRequest.created_at.desc(), DocumentAccessRequest.id.desc()).all()
    subscriptions = report_filter_created(
        Subscription.query,
        Subscription,
        cutoff,
    ).order_by(Subscription.created_at.desc()).all()
    licenses = report_filter_created(
        License.query,
        License,
        cutoff,
    ).order_by(License.created_at.desc()).all()
    api_clients = report_filter_created(
        ApiClient.query,
        ApiClient,
        cutoff,
    ).order_by(ApiClient.created_at.desc()).all()
    live_accesses = report_filter_created(
        LiveIntelligenceAccess.query,
        LiveIntelligenceAccess,
        cutoff,
    ).order_by(LiveIntelligenceAccess.created_at.desc()).all()

    api_enquiries = [item for item in commercial_requests if item.request_type == 'api_access']
    live_requests = [item for item in commercial_requests if item.request_type == 'live_intelligence']
    upgrade_requests = [item for item in commercial_requests if item.request_type == 'upgrade']

    open_commercial_requests = [
        item for item in commercial_requests
        if item.status in COMMERCIAL_REPORT_OPEN_STATUSES
    ]
    open_due_diligence_requests = [
        item for item in due_diligence_requests
        if item.status in DUE_DILIGENCE_REPORT_OPEN_STATUSES
    ]

    commercial_request_ids = [item.id for item in commercial_requests]
    fulfilled_commercial_request_ids = set()
    if commercial_request_ids:
        fulfilment_rows = CommercialFulfilmentAction.query.filter(
            CommercialFulfilmentAction.commercial_request_id.in_(commercial_request_ids)
        ).all()
        fulfilled_commercial_request_ids = {item.commercial_request_id for item in fulfilment_rows}

    active_subscriptions = [item for item in subscriptions if item.status == 'active']
    active_licenses = [item for item in licenses if item.status == 'active']
    active_packs = LicensedPack.query.filter_by(active=True).order_by(LicensedPack.price_usd).all()
    active_api_clients = [item for item in api_clients if item.status == 'active']
    active_live_accesses = [item for item in live_accesses if item.active]

    license_value_usd = sum(
        (license_record.licensed_pack.price_usd or 0)
        for license_record in active_licenses
        if license_record.licensed_pack
    )
    license_value_ngn = sum(
        (license_record.licensed_pack.price_ngn or 0)
        for license_record in active_licenses
        if license_record.licensed_pack
    )
    pack_catalogue_value_usd = sum(pack.price_usd or 0 for pack in active_packs)
    pack_catalogue_value_ngn = sum(pack.price_ngn or 0 for pack in active_packs)
    conversion_ready_count = len([
        item for item in commercial_requests
        if item.status in COMMERCIAL_REPORT_CONVERSION_STATUSES
    ])

    pipeline_summary = [
        {
            'label': 'Commercial Requests',
            'count': len(commercial_requests),
            'detail': f"{len(open_commercial_requests)} open",
            'url': url_for('admin.commercial_requests'),
        },
        {
            'label': 'Due Diligence Requests',
            'count': len(due_diligence_requests),
            'detail': f"{len(open_due_diligence_requests)} open",
            'url': url_for('admin.due_diligence_requests'),
        },
        {
            'label': 'API Enquiries',
            'count': len(api_enquiries),
            'detail': f"{len([item for item in api_enquiries if item.status in COMMERCIAL_REPORT_OPEN_STATUSES])} open",
            'url': url_for('admin.api_dashboard'),
        },
        {
            'label': 'Live Intelligence Requests',
            'count': len(live_requests),
            'detail': f"{len(active_live_accesses)} active grants in window",
            'url': url_for('admin.live_intelligence'),
        },
        {
            'label': 'Upgrade Requests',
            'count': len(upgrade_requests),
            'detail': f"{len([item for item in upgrade_requests if item.status in COMMERCIAL_REPORT_CONVERSION_STATUSES])} conversion-ready",
            'url': url_for('admin.commercial_requests', request_type='upgrade'),
        },
        {
            'label': 'Licences',
            'count': len(active_licenses),
            'detail': f"${license_value_usd:,} active pack value",
            'url': url_for('admin.commercial_dashboard'),
        },
        {
            'label': 'Subscriptions',
            'count': len(active_subscriptions),
            'detail': 'active subscriptions',
            'url': url_for('admin.users'),
        },
        {
            'label': 'Data Pack Activity',
            'count': len(active_packs),
            'detail': f"{len(licenses)} licence events in window",
            'url': url_for('admin.commercial_dashboard'),
        },
    ]

    request_funnel = {
        'commercial_by_status': report_count_items(commercial_requests, 'status'),
        'commercial_by_type': report_count_items(commercial_requests, 'request_type'),
        'commercial_by_product': report_count_items(commercial_requests, 'requested_product', limit=12),
        'commercial_by_region': report_count_items(commercial_requests, 'region_code'),
        'commercial_by_crop': report_count_items(commercial_requests, 'crop_name', limit=12),
        'commercial_by_date': report_date_items(commercial_requests, limit=14),
        'due_diligence_by_status': report_count_items(due_diligence_requests, 'status'),
        'due_diligence_by_type': report_count_items(due_diligence_requests, 'request_type'),
        'due_diligence_by_date': report_date_items(due_diligence_requests, limit=14),
    }

    revenue_readiness = {
        'active_pack_count': len(active_packs),
        'pack_catalogue_value_usd': pack_catalogue_value_usd,
        'pack_catalogue_value_ngn': pack_catalogue_value_ngn,
        'active_subscription_count': len(active_subscriptions),
        'active_license_count': len(active_licenses),
        'license_value_usd': license_value_usd,
        'license_value_ngn': license_value_ngn,
        'conversion_ready_count': conversion_ready_count,
        'fulfilled_commercial_request_count': len(fulfilled_commercial_request_ids),
        'conversion_rate_percent': report_percentage(len(fulfilled_commercial_request_ids), len(commercial_requests)),
        'active_api_client_count': len(active_api_clients),
        'active_live_intelligence_count': len(active_live_accesses),
        'subscriptions_by_plan': report_count_items(active_subscriptions, 'plan_code'),
        'licenses_by_pack': [],
    }
    license_pack_counter = Counter(
        license_record.licensed_pack.name if license_record.licensed_pack else 'Unspecified pack'
        for license_record in active_licenses
    )
    revenue_readiness['licenses_by_pack'] = [
        {'label': label, 'count': count}
        for label, count in sorted(license_pack_counter.items(), key=lambda item: (-item[1], item[0]))
    ]

    follow_up_queues = {
        'commercial': [safe_commercial_followup_item(item) for item in open_commercial_requests[:20]],
        'due_diligence': [safe_due_diligence_followup_item(item) for item in open_due_diligence_requests[:20]],
        'api': [safe_commercial_followup_item(item) for item in api_enquiries if item.status in COMMERCIAL_REPORT_OPEN_STATUSES][:20],
        'live_intelligence': [safe_commercial_followup_item(item) for item in live_requests if item.status in COMMERCIAL_REPORT_OPEN_STATUSES][:20],
    }

    return {
        'window': window,
        'pipeline_summary': pipeline_summary,
        'request_funnel': request_funnel,
        'revenue_readiness': revenue_readiness,
        'follow_up_queues': follow_up_queues,
        'commercial_requests': commercial_requests,
        'due_diligence_requests': due_diligence_requests,
        'api_enquiries': api_enquiries,
        'live_requests': live_requests,
        'upgrade_requests': upgrade_requests,
        'licenses': licenses,
        'subscriptions': subscriptions,
    }


def commercial_report_csv_rows(context):
    rows = []
    for item in context['pipeline_summary']:
        rows.append({
            'section': 'pipeline_summary',
            'metric': item['label'],
            'segment': 'total',
            'count': item['count'],
            'detail': item['detail'],
            'window': context['window']['label'],
        })

    for group_name, items in context['request_funnel'].items():
        for item in items:
            rows.append({
                'section': 'request_funnel',
                'metric': group_name,
                'segment': item['label'],
                'count': item['count'],
                'detail': '',
                'window': context['window']['label'],
            })

    revenue = context['revenue_readiness']
    for metric in [
        'active_pack_count',
        'pack_catalogue_value_usd',
        'pack_catalogue_value_ngn',
        'active_subscription_count',
        'active_license_count',
        'license_value_usd',
        'license_value_ngn',
        'conversion_ready_count',
        'fulfilled_commercial_request_count',
        'conversion_rate_percent',
        'active_api_client_count',
        'active_live_intelligence_count',
    ]:
        rows.append({
            'section': 'revenue_readiness',
            'metric': metric,
            'segment': 'total',
            'count': revenue[metric],
            'detail': '',
            'window': context['window']['label'],
        })

    for queue_name, items in context['follow_up_queues'].items():
        rows.append({
            'section': 'follow_up_queue',
            'metric': queue_name,
            'segment': 'open_items',
            'count': len(items),
            'detail': 'Aggregate only; restricted fields excluded',
            'window': context['window']['label'],
        })
    return rows


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
    pending_document_access_requests = DocumentAccessRequest.query.filter_by(status='pending').count()
    active_due_diligence_requests = DocumentAccessRequest.query.filter(
        DocumentAccessRequest.status.in_(['pending', 'in_review', 'needs_information'])
    ).count()
    pending_commercial_requests = CommercialRequest.query.filter_by(status='pending').count()
    commercial_requests_ready_for_fulfilment = CommercialRequest.query.filter_by(status='approved_for_fulfilment').count()
    commercial_report_followups = pending_commercial_requests + active_due_diligence_requests
    
    recent_exports = ExportLog.query.order_by(ExportLog.exported_at.desc()).limit(10).all()
    
    return render_template('admin/dashboard.html',
                           total_users=total_users,
                           active_subs=active_subs,
                           total_datasets=total_datasets,
                           total_exports=total_exports,
                           pending_document_reviews=pending_document_reviews,
                           pending_document_access_requests=pending_document_access_requests,
                           active_due_diligence_requests=active_due_diligence_requests,
                           pending_commercial_requests=pending_commercial_requests,
                           commercial_requests_ready_for_fulfilment=commercial_requests_ready_for_fulfilment,
                           commercial_report_followups=commercial_report_followups,
                           recent_exports=recent_exports)


@admin_bp.route('/commercial-dashboard')
@login_required
@admin_required
def commercial_dashboard():
    active_packs = LicensedPack.query.filter_by(active=True).order_by(LicensedPack.price_usd).all()
    active_subscriptions = Subscription.query.filter_by(status='active').order_by(Subscription.created_at.desc()).limit(20).all()
    recent_licenses = License.query.order_by(License.created_at.desc()).limit(20).all()
    live_accesses = LiveIntelligenceAccess.query.order_by(LiveIntelligenceAccess.created_at.desc()).limit(20).all()
    api_clients = ApiClient.query.order_by(ApiClient.created_at.desc()).limit(20).all()
    access_requests = DocumentAccessRequest.query.order_by(DocumentAccessRequest.created_at.desc()).limit(20).all()
    commercial_requests = CommercialRequest.query.order_by(CommercialRequest.created_at.desc()).limit(30).all()
    recent_gated_audit_events = (
        AuditLog.query.filter(
            AuditLog.action.in_([
                'commercial_live_intelligence_request_created',
                'commercial_api_access_request_created',
                'commercial_upgrade_request_created',
                'admin_commercial_request_status_updated',
                'admin_commercial_request_fulfilment_recorded',
                'admin_commercial_request_fulfilment_blocked',
                'subscriber_document_access_request_blocked',
                'subscriber_document_access_requested',
                'api_document_metadata_unauthorized',
            ])
        )
        .order_by(AuditLog.created_at.desc())
        .limit(20)
        .all()
    )
    recent_gated_document_events = (
        DocumentAccessLog.query.filter(
            DocumentAccessLog.access_type.like('%blocked%')
        )
        .order_by(DocumentAccessLog.accessed_at.desc())
        .limit(20)
        .all()
    )

    return render_template(
        'admin/commercial_dashboard.html',
        active_packs=active_packs,
        active_subscriptions=active_subscriptions,
        recent_licenses=recent_licenses,
        live_accesses=live_accesses,
        api_clients=api_clients,
        access_requests=access_requests,
        commercial_requests=commercial_requests,
        recent_gated_audit_events=recent_gated_audit_events,
        recent_gated_document_events=recent_gated_document_events,
    )


@admin_bp.route('/commercial-reports')
@login_required
@admin_required
def commercial_reports():
    context = build_commercial_report_context()
    return render_template('admin/commercial_reports.html', **context)


@admin_bp.route('/commercial-reports/pipeline.csv')
@login_required
@admin_required
def commercial_reports_pipeline_csv():
    context = build_commercial_report_context()
    output = io.StringIO()
    fieldnames = ['section', 'metric', 'segment', 'count', 'detail', 'window']
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(commercial_report_csv_rows(context))

    data = io.BytesIO(output.getvalue().encode('utf-8'))
    filename = f"fieldsight_commercial_pipeline_{context['window']['key']}.csv"
    return send_file(
        data,
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename,
    )


@admin_bp.route('/commercial-requests')
@login_required
@admin_required
def commercial_requests():
    status_filter = request.args.get('status', '').strip()
    type_filter = request.args.get('request_type', '').strip()

    query = CommercialRequest.query
    if status_filter in COMMERCIAL_REQUEST_STATUSES:
        query = query.filter_by(status=status_filter)
    else:
        status_filter = ''
    if type_filter:
        query = query.filter_by(request_type=type_filter)

    requests = (
        query.order_by(CommercialRequest.created_at.desc(), CommercialRequest.id.desc())
        .all()
    )
    return render_template(
        'admin/commercial_requests.html',
        commercial_requests=requests,
        selected_status=status_filter,
        selected_type=type_filter,
        statuses=COMMERCIAL_REQUEST_STATUSES,
        status_labels=COMMERCIAL_STATUS_LABELS,
        counts=commercial_request_queue_counts(),
    )


@admin_bp.route('/commercial-requests/<int:request_id>')
@login_required
@admin_required
def commercial_request_detail(request_id):
    commercial_request = CommercialRequest.query.get_or_404(request_id)
    return render_template(
        'admin/commercial_request_detail.html',
        commercial_request=commercial_request,
        status_options=COMMERCIAL_DECISION_STATUSES,
        status_labels=COMMERCIAL_STATUS_LABELS,
        fulfilment_action_types=COMMERCIAL_FULFILMENT_ACTION_TYPES,
        fulfilment_labels=COMMERCIAL_FULFILMENT_LABELS,
        regions=NIGERIA_REGIONS,
        **commercial_request_related_context(commercial_request),
    )


@admin_bp.route('/commercial-requests/<int:request_id>/decision', methods=['POST'])
@login_required
@admin_required
def commercial_request_decision(request_id):
    commercial_request = CommercialRequest.query.get_or_404(request_id)
    selected_status = clean_admin_form_value('status')
    if selected_status not in COMMERCIAL_DECISION_STATUSES:
        flash('Please choose a supported commercial request status.', 'error')
        return redirect(url_for('admin.commercial_request_detail', request_id=commercial_request.id))

    before_values = commercial_request_snapshot(commercial_request)
    commercial_request.status = selected_status
    commercial_request.review_notes = clean_admin_form_value('review_notes')
    commercial_request.reviewed_by_user_id = current_user.id
    commercial_request.reviewed_at = datetime.utcnow()
    after_values = commercial_request_snapshot(commercial_request)
    add_admin_commercial_request_audit(
        commercial_request,
        'admin_commercial_request_status_updated',
        before_values=before_values,
        after_values={
            **after_values,
            'access_granted': False,
            'payment_flow_changed': False,
        },
    )
    db.session.commit()
    flash('Commercial request status updated.', 'success')
    return redirect(url_for('admin.commercial_request_detail', request_id=commercial_request.id))


@admin_bp.route('/commercial-requests/<int:request_id>/fulfilment', methods=['POST'])
@login_required
@admin_required
def commercial_request_fulfilment(request_id):
    commercial_request = CommercialRequest.query.get_or_404(request_id)
    action_type = clean_admin_form_value('action_type')
    notes = clean_admin_form_value('notes')

    if action_type not in COMMERCIAL_FULFILMENT_ACTION_TYPES:
        flash('Please choose a supported fulfilment action.', 'error')
        return redirect(url_for('admin.commercial_request_detail', request_id=commercial_request.id))

    required_request_type = COMMERCIAL_FULFILMENT_REQUEST_TYPES.get(action_type)
    if required_request_type and commercial_request.request_type != required_request_type:
        reason = f"{action_type} is only valid for {required_request_type} requests."
        block_commercial_fulfilment(commercial_request, action_type, reason)
        db.session.commit()
        flash(reason, 'error')
        return redirect(url_for('admin.commercial_request_detail', request_id=commercial_request.id))

    if action_type != 'manual_note' and commercial_request.status != 'approved_for_fulfilment':
        reason = 'Fulfilment actions require approved for fulfilment status.'
        block_commercial_fulfilment(commercial_request, action_type, reason)
        db.session.commit()
        flash(reason, 'error')
        return redirect(url_for('admin.commercial_request_detail', request_id=commercial_request.id))

    try:
        if action_type == 'api_client_setup':
            api_client = ensure_api_client_setup_record(commercial_request, notes)
            flash(f'API client setup record captured for {api_client.name}. No API key was created.', 'success')
        elif action_type == 'live_intelligence_access':
            live_access = create_or_update_live_intelligence_from_request(commercial_request, notes)
            flash(f'Live Intelligence access recorded through {live_access.end_date.strftime("%Y-%m-%d")}.', 'success')
        elif action_type == 'upgrade_followup':
            create_commercial_fulfilment_action(
                commercial_request,
                action_type,
                notes,
                metadata={
                    'payment_flow_changed': False,
                    'subscription_created': False,
                    'license_created': False,
                    'upgrade_status_recorded_only': True,
                },
            )
            flash('Upgrade follow-up recorded. Payment provider flows were not changed.', 'success')
        else:
            create_commercial_fulfilment_action(
                commercial_request,
                'manual_note',
                notes,
                metadata={
                    'manual_note_only': True,
                    'access_created': False,
                    'payment_flow_changed': False,
                },
            )
            flash('Commercial fulfilment note recorded.', 'success')
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'error')
    return redirect(url_for('admin.commercial_request_detail', request_id=commercial_request.id))


@admin_bp.route('/api-dashboard')
@login_required
@admin_required
def api_dashboard():
    api_clients = ApiClient.query.order_by(ApiClient.created_at.desc()).limit(50).all()
    api_keys = ApiKey.query.order_by(ApiKey.created_at.desc()).limit(100).all()
    usage_events = ApiUsageEvent.query.order_by(ApiUsageEvent.occurred_at.desc()).limit(50).all()
    blocked_document_events = (
        DocumentAccessLog.query.filter(DocumentAccessLog.access_type.like('api_%blocked%'))
        .order_by(DocumentAccessLog.accessed_at.desc())
        .limit(50)
        .all()
    )
    unauthorized_events = (
        AuditLog.query.filter_by(action='api_document_metadata_unauthorized')
        .order_by(AuditLog.created_at.desc())
        .limit(50)
        .all()
    )
    api_enquiries = (
        CommercialRequest.query.filter_by(request_type='api_access')
        .order_by(CommercialRequest.created_at.desc())
        .limit(50)
        .all()
    )
    return render_template(
        'admin/api_dashboard.html',
        api_clients=api_clients,
        api_keys=api_keys,
        usage_events=usage_events,
        blocked_document_events=blocked_document_events,
        unauthorized_events=unauthorized_events,
        api_enquiries=api_enquiries,
    )


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


@admin_bp.route('/document-access-requests')
@login_required
@admin_required
def document_access_requests():
    status_filter = request.args.get('status', '').strip()
    query = DocumentAccessRequest.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    requests = query.order_by(DocumentAccessRequest.created_at.desc(), DocumentAccessRequest.id.desc()).all()
    return render_template(
        'admin/document_access_requests.html',
        access_requests=requests,
        selected_status=status_filter,
        statuses=DOCUMENT_ACCESS_REQUEST_STATUSES,
    )


@admin_bp.route('/due-diligence-requests')
@login_required
@admin_required
def due_diligence_requests():
    status_filter = request.args.get('status', '').strip()
    type_filter = request.args.get('request_type', '').strip()

    query = DocumentAccessRequest.query
    if status_filter in DOCUMENT_ACCESS_REQUEST_STATUSES:
        query = query.filter_by(status=status_filter)
    else:
        status_filter = ''
    if type_filter:
        query = query.filter_by(request_type=type_filter)

    requests = query.order_by(DocumentAccessRequest.created_at.desc(), DocumentAccessRequest.id.desc()).all()
    return render_template(
        'admin/due_diligence_requests.html',
        access_requests=requests,
        statuses=DOCUMENT_ACCESS_REQUEST_STATUSES,
        selected_status=status_filter,
        selected_type=type_filter,
        status_labels=DUE_DILIGENCE_STATUS_LABELS,
        counts=due_diligence_request_counts(),
    )


@admin_bp.route('/due-diligence-requests/<int:request_id>')
@login_required
@admin_required
def due_diligence_request_detail(request_id):
    access_request = DocumentAccessRequest.query.get_or_404(request_id)
    return render_template(
        'admin/due_diligence_request_detail.html',
        access_request=access_request,
        status_options=DUE_DILIGENCE_DECISION_STATUSES,
        status_labels=DUE_DILIGENCE_STATUS_LABELS,
        fulfilment_action_types=DOCUMENT_ACCESS_FULFILMENT_ACTION_TYPES,
        fulfilment_labels=DUE_DILIGENCE_FULFILMENT_LABELS,
        visibility_labels=DUE_DILIGENCE_VISIBILITY_LABELS,
        **due_diligence_request_context(access_request),
    )


@admin_bp.route('/due-diligence-requests/<int:request_id>/decision', methods=['POST'])
@login_required
@admin_required
def due_diligence_request_decision(request_id):
    access_request = DocumentAccessRequest.query.get_or_404(request_id)
    selected_status = clean_admin_form_value('status')
    if selected_status not in DUE_DILIGENCE_DECISION_STATUSES:
        flash('Please choose a supported due diligence status.', 'error')
        return redirect(url_for('admin.due_diligence_request_detail', request_id=access_request.id))

    context = due_diligence_request_context(access_request)
    if selected_status == 'approved_for_redacted_access' and not context['approval_allowed']:
        reason = 'Approval requires metadata entitlement plus the requested document access publish target to be ready or waived.'
        block_due_diligence_decision(access_request, selected_status, context, reason)
        db.session.commit()
        flash(reason, 'error')
        return redirect(url_for('admin.due_diligence_request_detail', request_id=access_request.id))

    before_values = due_diligence_request_snapshot(access_request)
    access_request.status = selected_status
    access_request.review_notes = clean_admin_form_value('review_notes')
    access_request.reviewed_by_user_id = current_user.id
    access_request.reviewed_at = datetime.utcnow()
    after_values = due_diligence_request_snapshot(access_request)
    add_admin_due_diligence_audit(
        access_request,
        'admin_due_diligence_request_status_updated',
        before_values=before_values,
        after_values={
            **after_values,
            'metadata_allowed': context['metadata_allowed'],
            'target_allowed': context['target_allowed'],
            'access_granted': False,
            'file_exposed': False,
            'payment_flow_changed': False,
        },
    )
    db.session.commit()
    flash('Due diligence request status updated.', 'success')
    return redirect(url_for('admin.due_diligence_request_detail', request_id=access_request.id))


@admin_bp.route('/due-diligence-requests/<int:request_id>/fulfilment', methods=['POST'])
@login_required
@admin_required
def due_diligence_request_fulfilment(request_id):
    access_request = DocumentAccessRequest.query.get_or_404(request_id)
    action_type = clean_admin_form_value('action_type')
    notes = clean_admin_form_value('notes')
    visibility_level = clean_admin_form_value('visibility_level') or 'redacted_document_candidate'

    if action_type not in DOCUMENT_ACCESS_FULFILMENT_ACTION_TYPES:
        flash('Please choose a supported due diligence fulfilment action.', 'error')
        return redirect(url_for('admin.due_diligence_request_detail', request_id=access_request.id))
    if visibility_level not in DUE_DILIGENCE_VISIBILITY_LABELS:
        flash('Please choose a supported visibility level.', 'error')
        return redirect(url_for('admin.due_diligence_request_detail', request_id=access_request.id))

    context = due_diligence_request_context(access_request)
    if action_type != 'manual_note':
        if access_request.status != 'approved_for_redacted_access':
            reason = 'Controlled document access fulfilment requires approved for redacted access status.'
            block_due_diligence_fulfilment(access_request, action_type, context, reason)
            db.session.commit()
            flash(reason, 'error')
            return redirect(url_for('admin.due_diligence_request_detail', request_id=access_request.id))
        if not context['approval_allowed']:
            reason = 'Current consent, entitlement, redaction, or publish-readiness gates no longer allow fulfilment.'
            block_due_diligence_fulfilment(access_request, action_type, context, reason)
            db.session.commit()
            flash(reason, 'error')
            return redirect(url_for('admin.due_diligence_request_detail', request_id=access_request.id))
        if action_type == 'redacted_access_recorded':
            visibility_level = 'redacted_document_candidate'
        elif action_type == 'restricted_full_document_review_recorded':
            visibility_level = 'full_document_restricted_candidate'

    create_due_diligence_fulfilment_action(
        access_request,
        action_type,
        notes,
        visibility_level,
        context,
    )
    db.session.commit()
    flash('Due diligence fulfilment action recorded. No document file or download link was exposed.', 'success')
    return redirect(url_for('admin.due_diligence_request_detail', request_id=access_request.id))


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


@admin_bp.route('/documents/<int:document_id>/redaction', methods=['GET', 'POST'])
@login_required
@admin_required
def document_redaction_controls(document_id):
    document = ActorDocument.query.get_or_404(document_id)
    context = document_admin_review_context(document)

    if request.method == 'POST':
        redaction_status = clean_admin_form_value('redaction_status')
        notes = clean_admin_form_value('redaction_notes')
        if redaction_status not in DOCUMENT_REDACTION_STATUSES:
            flash('Please choose a supported redaction status.', 'error')
            return redirect(url_for('admin.document_redaction_controls', document_id=document.id))

        before_values = document_review_snapshot(document)
        version = current_document_version(document)
        document.redaction_status = redaction_status
        document.reviewed_by_user_id = current_user.id
        document.reviewed_at = datetime.utcnow()
        if notes:
            document.review_comments = notes

        review_entry = DocumentReview(
            actor_document_id=document.id,
            actor_document_version_id=version.id if version else None,
            reviewer_user_id=current_user.id,
            status=f'redaction_{redaction_status}'[:50],
            notes=notes or None,
            reviewed_at=datetime.utcnow(),
        )
        db.session.add(review_entry)
        db.session.flush()

        after_values = document_review_snapshot(document)
        after_values.update({
            'review_entry_id': review_entry.id,
            'redaction_status': redaction_status,
            'actor_id': document.market_actor_id,
            'partner_organization_id': document.partner_organization_id,
            'external_access_changed': False,
        })
        add_admin_document_audit(
            document,
            'admin_document_redaction_updated',
            before_values={
                'document': before_values,
                'actor_id': document.market_actor_id,
                'partner_organization_id': document.partner_organization_id,
            },
            after_values=after_values,
        )
        db.session.commit()
        flash('Redaction status updated. No subscriber or API access was created.', 'success')
        return redirect(url_for('admin.document_redaction_controls', document_id=document.id))

    return render_template(
        'admin/document_redaction.html',
        **context,
        redaction_status_options=DOCUMENT_REDACTION_STATUS_OPTIONS,
    )


@admin_bp.route('/documents/<int:document_id>/publish-controls')
@login_required
@admin_required
def document_publish_controls(document_id):
    document = ActorDocument.query.get_or_404(document_id)
    context = document_admin_review_context(document)
    return render_template(
        'admin/document_publish_controls.html',
        **context,
        publish_targets=publish_control_context(document),
        publish_statuses=DOCUMENT_PUBLISH_CONTROL_STATUSES,
    )


@admin_bp.route('/documents/<int:document_id>/publish-controls/evaluate', methods=['POST'])
@login_required
@admin_required
def document_publish_controls_evaluate(document_id):
    document = ActorDocument.query.get_or_404(document_id)
    before_values = {
        item.publish_target: document_publish_control_snapshot(item)
        for item in DocumentPublishControl.query.filter_by(actor_document_id=document.id).all()
    }
    evaluated_controls = []
    for target_code in DOCUMENT_PUBLISH_TARGETS:
        evaluation = evaluate_publish_readiness(document, target_code)
        control = persist_publish_control_evaluation(
            document,
            target_code,
            evaluation,
            admin_decision='evaluated',
            status=evaluation['computed_status'],
        )
        evaluated_controls.append(control)

    db.session.flush()
    after_values = {
        control.publish_target: document_publish_control_snapshot(control)
        for control in evaluated_controls
    }
    add_admin_document_audit(
        document,
        'admin_document_publish_readiness_evaluated',
        before_values={
            'publish_controls': before_values,
            'actor_id': document.market_actor_id,
            'partner_organization_id': document.partner_organization_id,
        },
        after_values={
            'publish_controls': after_values,
            'actor_id': document.market_actor_id,
            'partner_organization_id': document.partner_organization_id,
            'external_access_created': False,
        },
    )
    db.session.commit()
    flash('Publish readiness was evaluated for all targets. No external access was created.', 'success')
    return redirect(url_for('admin.document_publish_controls', document_id=document.id))


@admin_bp.route('/documents/<int:document_id>/publish-controls/decision', methods=['POST'])
@login_required
@admin_required
def document_publish_controls_decision(document_id):
    document = ActorDocument.query.get_or_404(document_id)
    target_code = clean_admin_form_value('publish_target')
    decision = clean_admin_form_value('decision')
    notes = clean_admin_form_value('decision_notes')

    if target_code not in DOCUMENT_PUBLISH_TARGETS:
        flash('Please choose a supported publish target.', 'error')
        return redirect(url_for('admin.document_publish_controls', document_id=document.id))
    if decision not in {'evaluate', 'mark_ready', 'mark_blocked', 'waive_high_risk_flags'}:
        flash('Please choose a supported publish-control decision.', 'error')
        return redirect(url_for('admin.document_publish_controls', document_id=document.id))

    evaluation = evaluate_publish_readiness(document, target_code)
    control = get_or_create_publish_control(document, target_code)
    before_values = document_publish_control_snapshot(control)

    if decision == 'mark_ready':
        if evaluation['blocking_reasons']:
            status = 'blocked'
            flash('This target still has blocking readiness checks and was kept blocked.', 'error')
        else:
            status = 'ready'
            flash('Publish target marked ready for a future controlled workflow. No external access was created.', 'success')
    elif decision == 'mark_blocked':
        status = 'blocked'
        flash('Publish target marked blocked.', 'success')
    elif decision == 'waive_high_risk_flags':
        non_waivable_keys = [key for key in evaluation['blocking_keys'] if key != 'high_risk_flags']
        if non_waivable_keys or not evaluation['high_risk_flags']:
            status = 'blocked'
            flash('Only unresolved high-risk flags can be waived, and only after all other gates pass.', 'error')
        else:
            status = 'waived'
            flash('High-risk flags were explicitly waived for this target. No external access was created.', 'warning')
    else:
        status = evaluation['computed_status']
        flash('Publish target readiness was re-evaluated.', 'success')

    control = persist_publish_control_evaluation(
        document,
        target_code,
        evaluation,
        admin_decision=decision,
        notes=notes,
        status=status,
    )
    db.session.flush()
    after_values = document_publish_control_snapshot(control)
    after_values.update({
        'computed_status': evaluation['computed_status'],
        'blocking_keys': evaluation['blocking_keys'],
        'actor_id': document.market_actor_id,
        'partner_organization_id': document.partner_organization_id,
        'external_access_created': False,
    })
    add_admin_publish_control_audit(
        document,
        control,
        'admin_document_publish_readiness_decision',
        before_values=before_values,
        after_values=after_values,
    )
    db.session.commit()
    return redirect(url_for('admin.document_publish_controls', document_id=document.id))


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
