"""Partner data portal routes."""

import hashlib
import mimetypes
import re
import uuid
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from models import (
    ACTOR_TYPES,
    COMMON_STATUSES,
    CONSENT_DATA_CATEGORY_OPTIONS,
    CONSENT_DOCUMENT_CATEGORY_OPTIONS,
    CONSENT_METHODS,
    CONSENT_REVIEW_STATUSES,
    CONSENT_SCOPE_OPTIONS,
    CONSENT_SHARING_CHANNEL_OPTIONS,
    CONSENT_STATUSES,
    DOCUMENT_EXTRACTION_STATUSES,
    DOCUMENT_INTELLIGENCE_STATUSES,
    DOCUMENT_RECONCILIATION_STATUSES,
    DOCUMENT_VISIBILITY_LEVELS,
    PARTNER_DATASET_TYPES,
    PARTNER_ROLES,
    ActorCertification,
    ActorContact,
    ActorConstraint,
    ActorConsentRecord,
    ActorDocument,
    ActorDocumentVersion,
    ActorExportProfile,
    ActorLocation,
    AuditLog,
    CertificationType,
    Commodity,
    Crop,
    DocumentAccessLog,
    DocumentExtractionRun,
    DocumentFieldReconciliation,
    DocumentType,
    LGA,
    MarketActor,
    Port,
    PartnerOrganization,
    PartnerRecordChange,
    PartnerUpdateBatch,
    PartnerUserProfile,
    ReferenceOption,
    Region,
    State,
    TradeDestination,
    actor_can_share_data,
    actor_can_share_documents,
    actor_has_active_consent,
    calculate_actor_quality_score,
    consent_document_category_for_document_type,
    get_active_actor_consent,
    db,
)

partner_bp = Blueprint("partner", __name__, url_prefix="/partner")

EDITOR_ROLES = ("partner_admin", "data_editor")
SUBMITTER_ROLES = ("partner_admin", "data_reviewer")
RESTRICTED_CONTACT_ROLES = ("partner_admin", "data_editor", "data_reviewer")
DOCUMENT_DOWNLOAD_ROLES = ("partner_admin", "data_editor", "data_reviewer")
ALLOWED_DOCUMENT_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "csv", "xls", "xlsx"}
PREVIEWABLE_DOCUMENT_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "csv"}
TEXT_EXTRACTION_EXTENSIONS = {"csv", "txt"}
SAFE_EXCERPT_BYTES = 16384
EXTERNAL_SHARING_CHANNELS = (
    "licensed_data_pack",
    "live_intelligence",
    "subscriber_portal",
    "api",
    "approved_buyer_due_diligence",
)

CERTIFICATE_OF_ORIGIN_FIELDS = [
    ("document_reference_number", "Document Reference Number"),
    ("issuing_body", "Issuing Body"),
    ("issued_at", "Issued Date"),
    ("expires_at", "Expiry Date"),
    ("exporter_name", "Exporter Name"),
    ("consignee_name", "Consignee Name"),
    ("origin_country", "Origin Country"),
    ("destination_country", "Destination Country"),
    ("crop_or_commodity", "Crop Or Commodity"),
    ("quantity", "Quantity"),
    ("port_of_exit", "Port Of Exit"),
    ("certificate_type", "Certificate Type"),
]
GENERIC_EXTRACTION_FIELDS = [
    ("document_reference_number", "Document Reference Number"),
    ("issuing_body", "Issuing Body"),
    ("issued_at", "Issued Date"),
    ("expires_at", "Expiry Date"),
    ("crop_or_commodity", "Crop Or Commodity"),
]
RECONCILABLE_DOCUMENT_FIELDS = {
    "document_reference_number": "document_reference_number",
    "issuing_body": "issuing_body",
    "issued_at": "issued_at",
    "expires_at": "expires_at",
}
FIELD_ALIASES = {
    "reference_number": "document_reference_number",
    "document_reference": "document_reference_number",
    "certificate_number": "document_reference_number",
    "certificate_reference": "document_reference_number",
    "issuing_authority": "issuing_body",
    "issuer": "issuing_body",
    "issued_date": "issued_at",
    "issue_date": "issued_at",
    "expiry_date": "expires_at",
    "expiration_date": "expires_at",
    "valid_until": "expires_at",
    "exporter": "exporter_name",
    "consignee": "consignee_name",
    "country_of_origin": "origin_country",
    "destination": "destination_country",
    "commodity": "crop_or_commodity",
    "crop": "crop_or_commodity",
    "port": "port_of_exit",
    "exit_port": "port_of_exit",
    "type": "certificate_type",
}


def get_partner_profile_for_user(user):
    if not user or not getattr(user, "is_authenticated", False):
        return None

    return (
        PartnerUserProfile.query.join(PartnerOrganization)
        .filter(
            PartnerUserProfile.user_id == user.id,
            PartnerUserProfile.status == "active",
            PartnerUserProfile.partner_role.in_(PARTNER_ROLES),
            PartnerOrganization.status == "active",
        )
        .order_by(PartnerUserProfile.updated_at.desc())
        .first()
    )


def get_current_partner_profile():
    return get_partner_profile_for_user(current_user)


def get_current_partner_org():
    profile = get_current_partner_profile()
    if not profile:
        return None
    return profile.partner_organization


def require_partner_user(func):
    @wraps(func)
    def decorated_function(*args, **kwargs):
        profile = get_current_partner_profile()
        if not profile:
            flash("Partner portal access requires an active partner profile.", "error")
            return redirect(url_for("subscriber.dashboard"))
        return func(*args, **kwargs)

    return decorated_function


def require_partner_role(*allowed_roles):
    def decorator(func):
        @wraps(func)
        def decorated_function(*args, **kwargs):
            profile = get_current_partner_profile()
            if not profile:
                flash("Partner portal access requires an active partner profile.", "error")
                return redirect(url_for("subscriber.dashboard"))
            if profile.partner_role != "partner_admin" and profile.partner_role not in allowed_roles:
                flash("Your partner role does not allow that action.", "error")
                return redirect(url_for("partner.dashboard"))
            return func(*args, **kwargs)

        return decorated_function

    return decorator


def can_view_restricted_contacts(profile):
    return bool(profile and profile.partner_role in RESTRICTED_CONTACT_ROLES)


def can_edit_partner_records(profile):
    return bool(profile and profile.partner_role in EDITOR_ROLES)


def can_submit_partner_batches(profile):
    return bool(profile and profile.partner_role in SUBMITTER_ROLES)


def can_download_partner_documents(profile):
    return bool(profile and profile.partner_role in DOCUMENT_DOWNLOAD_ROLES)


def get_partner_actor_or_404(actor_id, profile):
    actor = MarketActor.query.filter_by(
        id=actor_id,
        partner_organization_id=profile.partner_organization_id,
    ).first()
    if not actor:
        abort(404)
    return actor


def get_partner_document_or_404(document_id, profile):
    document = (
        ActorDocument.query.join(MarketActor)
        .filter(
            ActorDocument.id == document_id,
            ActorDocument.partner_organization_id == profile.partner_organization_id,
            MarketActor.partner_organization_id == profile.partner_organization_id,
        )
        .first()
    )
    if not document:
        abort(404)
    return document


def get_partner_consent_or_404(actor_id, consent_id, profile):
    consent_record = (
        ActorConsentRecord.query.join(MarketActor)
        .filter(
            ActorConsentRecord.id == consent_id,
            ActorConsentRecord.market_actor_id == actor_id,
            ActorConsentRecord.partner_organization_id == profile.partner_organization_id,
            MarketActor.partner_organization_id == profile.partner_organization_id,
        )
        .first()
    )
    if not consent_record:
        abort(404)
    return consent_record


def get_partner_batch_or_404(batch_id, profile):
    batch = PartnerUpdateBatch.query.filter_by(
        id=batch_id,
        partner_organization_id=profile.partner_organization_id,
    ).first()
    if not batch:
        abort(404)
    return batch


def clean_form_value(field_name):
    value = request.form.get(field_name, "")
    if value is None:
        return ""
    return value.strip()


def parse_optional_int(field_name, label, errors):
    value = clean_form_value(field_name)
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        errors.append(f"{label} must be a number.")
        return None


def get_reference_options(category):
    return (
        ReferenceOption.query.filter_by(category=category, active=True)
        .order_by(ReferenceOption.sort_order, ReferenceOption.label)
        .all()
    )


def get_reference_options_by_category():
    categories = [
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
    return {category: get_reference_options(category) for category in categories}


def reference_option_codes(category):
    return {option.code for option in get_reference_options(category)}


def validate_reference_value(category, value, label, errors, allow_free_text=True):
    if not value:
        return

    codes = reference_option_codes(category)
    if codes and value not in codes and not allow_free_text:
        errors.append(f"Please select a supported {label}.")


def get_optional_model(model, model_id, label, errors):
    if not model_id:
        return None

    record = db.session.get(model, model_id)
    if not record:
        errors.append(f"Selected {label} was not found.")
        return None
    return record


def parse_optional_date(field_name, label, errors):
    value = clean_form_value(field_name)
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        errors.append(f"{label} must use YYYY-MM-DD format.")
        return None


def parse_optional_datetime(field_name, label, errors):
    value = clean_form_value(field_name)
    if not value:
        return None
    for date_format in ("%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            parsed_value = datetime.strptime(value, date_format)
            if date_format == "%Y-%m-%d":
                return parsed_value.replace(hour=0, minute=0)
            return parsed_value
        except ValueError:
            continue
    errors.append(f"{label} must use YYYY-MM-DD or YYYY-MM-DD HH:MM format.")
    return None


def option_codes(options):
    return {code for code, _label in options}


def clean_multi_values(field_name, allowed_codes):
    values = []
    for value in request.form.getlist(field_name):
        cleaned_value = value.strip()
        if cleaned_value and cleaned_value in allowed_codes and cleaned_value not in values:
            values.append(cleaned_value)
    return values


def private_upload_root():
    configured_root = Path(current_app.config.get("PRIVATE_UPLOAD_ROOT", "private_uploads"))
    if configured_root.is_absolute():
        return configured_root
    return Path(current_app.root_path) / configured_root


def ensure_private_storage_path(path):
    root = private_upload_root().resolve()
    resolved_path = path.resolve()
    try:
        resolved_path.relative_to(root)
    except ValueError:
        abort(404)
    return resolved_path


def storage_path_for_db(file_path):
    configured_root = Path(current_app.config.get("PRIVATE_UPLOAD_ROOT", "private_uploads"))
    root = private_upload_root().resolve()
    relative_path = file_path.resolve().relative_to(root)
    if configured_root.is_absolute():
        return str(file_path.resolve())
    return (configured_root / relative_path).as_posix()


def resolve_document_storage_path(storage_path):
    path = Path(storage_path)
    if not path.is_absolute():
        path = Path(current_app.root_path) / path
    return ensure_private_storage_path(path)


def clean_original_filename(filename):
    name = (filename or "").rsplit("\\", 1)[-1].rsplit("/", 1)[-1].strip()
    return name


def validate_document_upload(file_storage):
    errors = []
    if not file_storage or not file_storage.filename:
        return None, ["Please choose a document file."]

    original_filename = clean_original_filename(file_storage.filename)
    safe_filename = secure_filename(original_filename)
    extension = safe_filename.rsplit(".", 1)[-1].lower() if "." in safe_filename else ""
    if extension not in ALLOWED_DOCUMENT_EXTENSIONS:
        errors.append("Document file type is not allowed.")

    content = file_storage.read()
    file_storage.seek(0)
    if not content:
        errors.append("Document file cannot be empty.")

    max_bytes = int(current_app.config.get("MAX_DOCUMENT_UPLOAD_MB", 10)) * 1024 * 1024
    if len(content) > max_bytes:
        errors.append(f"Document file must be {current_app.config.get('MAX_DOCUMENT_UPLOAD_MB', 10)} MB or smaller.")

    if errors:
        return None, errors

    mime_type = file_storage.mimetype or mimetypes.guess_type(safe_filename)[0] or "application/octet-stream"
    return {
        "original_filename": original_filename,
        "safe_filename": safe_filename,
        "mime_type": mime_type,
        "file_size": len(content),
        "file_hash": hashlib.sha256(content).hexdigest(),
        "content": content,
    }, []


def save_document_upload(actor, document, upload_data, version_number):
    actor_token = secure_filename(actor.public_id or f"actor-{actor.id}")
    folder = private_upload_root() / "actors" / actor_token / "documents" / f"document-{document.id}" / f"v{version_number}"
    folder = ensure_private_storage_path(folder)
    folder.mkdir(parents=True, exist_ok=True)

    stored_filename = f"{uuid.uuid4().hex}_{upload_data['safe_filename']}"
    file_path = ensure_private_storage_path(folder / stored_filename)
    file_path.write_bytes(upload_data["content"])

    return {
        "original_filename": upload_data["original_filename"],
        "stored_filename": stored_filename,
        "storage_path": storage_path_for_db(file_path),
        "mime_type": upload_data["mime_type"],
        "file_size": upload_data["file_size"],
        "file_hash": upload_data["file_hash"],
    }


def get_document_type_for_actor(document_type_id, actor, errors):
    if not document_type_id:
        errors.append("Document type is required.")
        return None

    document_type = DocumentType.query.filter_by(id=document_type_id, active=True).first()
    if not document_type:
        errors.append("Selected document type was not found.")
        return None

    applies_to = document_type.applies_to_actor_types or []
    if applies_to and actor.actor_type not in applies_to:
        errors.append("Selected document type does not apply to this actor type.")
    return document_type


def parse_document_form(actor):
    errors = []
    document_type_id = parse_optional_int("document_type_id", "Document type", errors)
    document_type = get_document_type_for_actor(document_type_id, actor, errors)
    title = clean_form_value("title")
    description = clean_form_value("description")
    reference_number = clean_form_value("document_reference_number")
    issuing_body = clean_form_value("issuing_body")
    issued_at = parse_optional_date("issued_at", "Issued date", errors)
    expires_at = parse_optional_date("expires_at", "Expiry date", errors)
    linked_crop_id = parse_optional_int("linked_crop_id", "Linked crop", errors)
    linked_commodity_id = parse_optional_int("linked_commodity_id", "Linked commodity", errors)

    if not title:
        errors.append("Document title is required.")

    if linked_crop_id:
        get_optional_model(Crop, linked_crop_id, "linked crop", errors)
    if linked_commodity_id:
        get_optional_model(Commodity, linked_commodity_id, "linked commodity", errors)

    if document_type:
        if document_type.requires_reference_number and not reference_number:
            errors.append("Reference number is required for this document type.")
        if document_type.requires_issuing_body and not issuing_body:
            errors.append("Issuing body is required for this document type.")
        if document_type.requires_expiry_date and not expires_at:
            errors.append("Expiry date is required for this document type.")

    if issued_at and expires_at and expires_at < issued_at:
        errors.append("Expiry date cannot be before issued date.")

    default_visibility = document_type.default_visibility_level if document_type else "metadata_only"
    subscriber_access_level = clean_form_value("subscriber_access_level") or default_visibility or "metadata_only"
    if document_type and document_type.sensitive:
        subscriber_access_level = "hidden"
    if not actor_has_active_consent(actor):
        subscriber_access_level = "hidden"

    if subscriber_access_level not in DOCUMENT_VISIBILITY_LEVELS:
        errors.append("Please select a supported subscriber access level.")

    return errors, {
        "document_type": document_type,
        "title": title,
        "description": description or None,
        "document_reference_number": reference_number or None,
        "issuing_body": issuing_body or None,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "linked_crop_id": linked_crop_id,
        "linked_commodity_id": linked_commodity_id,
        "subscriber_access_level": subscriber_access_level,
        "visibility_level": subscriber_access_level,
    }


def apply_document_metadata(document, values):
    document.document_type_id = values["document_type"].id
    document.title = values["title"]
    document.description = values["description"]
    document.document_reference_number = values["document_reference_number"]
    document.issuing_body = values["issuing_body"]
    document.issued_at = values["issued_at"]
    document.expires_at = values["expires_at"]
    document.linked_crop_id = values["linked_crop_id"]
    document.linked_commodity_id = values["linked_commodity_id"]
    document.subscriber_access_level = values["subscriber_access_level"]
    document.visibility_level = values["visibility_level"]
    if values["document_type"].default_verification_status:
        document.verification_status = values["document_type"].default_verification_status


def document_form_context(profile, actor=None, document=None):
    document_types = DocumentType.query.filter_by(active=True).order_by(DocumentType.category, DocumentType.name).all()
    if actor:
        document_types = [
            document_type for document_type in document_types
            if not document_type.applies_to_actor_types or actor.actor_type in document_type.applies_to_actor_types
        ]

    return {
        "profile": profile,
        "organization": profile.partner_organization,
        "actor": actor or document.market_actor,
        "document": document,
        "document_types": document_types,
        "visibility_levels": DOCUMENT_VISIBILITY_LEVELS,
        "crops": Crop.query.filter_by(active=True).order_by(Crop.name).all(),
        "commodities": Commodity.query.filter_by(active=True).order_by(Commodity.name).all(),
        "max_upload_mb": current_app.config.get("MAX_DOCUMENT_UPLOAD_MB", 10),
        "allowed_extensions": sorted(ALLOWED_DOCUMENT_EXTENSIONS),
        "can_edit": can_edit_partner_records(profile),
        "can_download": can_download_partner_documents(profile),
    }


def current_document_version(document):
    return ActorDocumentVersion.query.filter_by(
        actor_document_id=document.id,
        version_number=document.version_number,
    ).first()


def document_snapshot(document):
    return {
        "id": document.id,
        "market_actor_id": document.market_actor_id,
        "partner_organization_id": document.partner_organization_id,
        "document_type_id": document.document_type_id,
        "title": document.title,
        "document_reference_number": document.document_reference_number,
        "issuing_body": document.issuing_body,
        "linked_crop_id": document.linked_crop_id,
        "linked_commodity_id": document.linked_commodity_id,
        "document_status": document.document_status,
        "verification_status": document.verification_status,
        "redaction_status": document.redaction_status,
        "subscriber_access_level": document.subscriber_access_level,
        "review_status": document.review_status,
        "visibility_level": document.visibility_level,
        "issued_at": iso_date(document.issued_at),
        "expires_at": iso_date(document.expires_at),
        "original_filename": document.original_filename,
        "stored_filename": document.stored_filename,
        "mime_type": document.mime_type,
        "file_size": document.file_size,
        "file_hash": document.file_hash,
        "version_number": document.version_number,
    }


def add_document_access_log(document, access_type, version=None):
    db.session.add(DocumentAccessLog(
        actor_document_id=document.id,
        actor_document_version_id=version.id if version else None,
        user_id=current_user.id,
        access_type=access_type,
        access_channel="partner_portal",
        visibility_level=document.visibility_level or document.subscriber_access_level or "metadata_only",
        ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
        user_agent=request.headers.get("User-Agent"),
    ))


def latest_consent_record(actor):
    return (
        ActorConsentRecord.query.filter_by(
            market_actor_id=actor.id,
            partner_organization_id=actor.partner_organization_id,
        )
        .order_by(ActorConsentRecord.updated_at.desc(), ActorConsentRecord.id.desc())
        .first()
    )


def consent_status_for_actor(actor):
    active_consent = get_active_actor_consent(actor)
    if active_consent:
        return active_consent.consent_status, active_consent
    latest_record = latest_consent_record(actor)
    if latest_record:
        if latest_record.consent_status == "granted" and latest_record.expires_at and latest_record.expires_at < datetime.utcnow():
            return "expired", latest_record
        return latest_record.consent_status, latest_record
    return "not_requested", None


def actor_data_is_externally_shareable(actor):
    return any(actor_can_share_data(actor, channel) for channel in EXTERNAL_SHARING_CHANNELS)


def actor_documents_are_externally_shareable(actor):
    return any(actor_can_share_documents(actor, channel) for channel in EXTERNAL_SHARING_CHANNELS)


def consent_choices_context():
    return {
        "consent_statuses": CONSENT_STATUSES,
        "consent_methods": CONSENT_METHODS,
        "review_statuses": CONSENT_REVIEW_STATUSES,
        "consent_scope_options": CONSENT_SCOPE_OPTIONS,
        "data_category_options": CONSENT_DATA_CATEGORY_OPTIONS,
        "document_category_options": CONSENT_DOCUMENT_CATEGORY_OPTIONS,
        "sharing_channel_options": CONSENT_SHARING_CHANNEL_OPTIONS,
    }


def consent_form_context(profile, actor, consent_record=None):
    context = consent_choices_context()
    context.update({
        "profile": profile,
        "organization": profile.partner_organization,
        "actor": actor,
        "consent_record": consent_record,
        "actor_documents": (
            ActorDocument.query.filter_by(
                market_actor_id=actor.id,
                partner_organization_id=profile.partner_organization_id,
            )
            .order_by(ActorDocument.updated_at.desc())
            .all()
        ),
    })
    return context


def parse_consent_form(actor, profile):
    errors = []
    consent_status = clean_form_value("consent_status") or "requested"
    consent_method = clean_form_value("consent_method")
    review_status = clean_form_value("review_status") or "pending_review"
    consent_document_id = parse_optional_int("consent_document_id", "Consent document", errors)
    granted_at = parse_optional_datetime("granted_at", "Granted at", errors)
    expires_at = parse_optional_datetime("expires_at", "Expiry date", errors)

    if consent_status not in CONSENT_STATUSES:
        errors.append("Please select a supported consent status.")
    if consent_method and consent_method not in CONSENT_METHODS:
        errors.append("Please select a supported consent method.")
    if review_status not in CONSENT_REVIEW_STATUSES:
        errors.append("Please select a supported review status.")

    consent_document = None
    if consent_document_id:
        consent_document = ActorDocument.query.filter_by(
            id=consent_document_id,
            market_actor_id=actor.id,
            partner_organization_id=profile.partner_organization_id,
        ).first()
        if not consent_document:
            errors.append("Selected consent document must belong to this actor and partner organization.")

    consent_scope = clean_multi_values("consent_scope_json", option_codes(CONSENT_SCOPE_OPTIONS))
    data_categories = clean_multi_values("permitted_data_categories_json", option_codes(CONSENT_DATA_CATEGORY_OPTIONS))
    document_categories = clean_multi_values("permitted_document_categories_json", option_codes(CONSENT_DOCUMENT_CATEGORY_OPTIONS))
    sharing_channels = clean_multi_values("sharing_channels_json", option_codes(CONSENT_SHARING_CHANNEL_OPTIONS))

    if consent_status == "granted":
        if not consent_method:
            errors.append("Consent method is required when consent is granted.")
        if not clean_form_value("granted_by_name"):
            errors.append("Granted by name is required when consent is granted.")
        if not granted_at:
            granted_at = datetime.utcnow()
    if expires_at and granted_at and expires_at < granted_at:
        errors.append("Consent expiry cannot be before the granted date.")

    return errors, {
        "consent_status": consent_status,
        "consent_scope_json": consent_scope,
        "permitted_data_categories_json": data_categories,
        "permitted_document_categories_json": document_categories,
        "sharing_channels_json": sharing_channels,
        "consent_method": consent_method or None,
        "consent_reference": clean_form_value("consent_reference") or None,
        "consent_document_id": consent_document.id if consent_document else None,
        "granted_by_name": clean_form_value("granted_by_name") or None,
        "granted_by_role": clean_form_value("granted_by_role") or None,
        "granted_by_email": clean_form_value("granted_by_email") or None,
        "granted_by_phone": clean_form_value("granted_by_phone") or None,
        "granted_at": granted_at,
        "expires_at": expires_at,
        "review_status": review_status,
        "review_notes": clean_form_value("review_notes") or None,
    }


def apply_consent_values(consent_record, values):
    consent_record.consent_status = values["consent_status"]
    consent_record.consent_scope_json = values["consent_scope_json"]
    consent_record.permitted_data_categories_json = values["permitted_data_categories_json"]
    consent_record.permitted_document_categories_json = values["permitted_document_categories_json"]
    consent_record.sharing_channels_json = values["sharing_channels_json"]
    consent_record.consent_method = values["consent_method"]
    consent_record.consent_reference = values["consent_reference"]
    consent_record.consent_document_id = values["consent_document_id"]
    consent_record.granted_by_name = values["granted_by_name"]
    consent_record.granted_by_role = values["granted_by_role"]
    consent_record.granted_by_email = values["granted_by_email"]
    consent_record.granted_by_phone = values["granted_by_phone"]
    consent_record.granted_at = values["granted_at"]
    consent_record.expires_at = values["expires_at"]
    consent_record.review_status = values["review_status"]
    consent_record.review_notes = values["review_notes"]


def deactivate_prior_actor_consents(actor, profile):
    ActorConsentRecord.query.filter(
        ActorConsentRecord.market_actor_id == actor.id,
        ActorConsentRecord.partner_organization_id == profile.partner_organization_id,
        ActorConsentRecord.active.is_(True),
    ).update({"active": False}, synchronize_session=False)


def consent_snapshot(consent_record):
    return {
        "id": consent_record.id,
        "market_actor_id": consent_record.market_actor_id,
        "partner_organization_id": consent_record.partner_organization_id,
        "consent_status": consent_record.consent_status,
        "consent_scope_json": consent_record.consent_scope_json,
        "permitted_data_categories_json": consent_record.permitted_data_categories_json,
        "permitted_document_categories_json": consent_record.permitted_document_categories_json,
        "sharing_channels_json": consent_record.sharing_channels_json,
        "consent_method": consent_record.consent_method,
        "consent_reference": consent_record.consent_reference,
        "consent_document_id": consent_record.consent_document_id,
        "granted_by_name": consent_record.granted_by_name,
        "granted_by_role": consent_record.granted_by_role,
        "granted_by_email": consent_record.granted_by_email,
        "granted_by_phone": consent_record.granted_by_phone,
        "granted_at": consent_record.granted_at.isoformat() if consent_record.granted_at else None,
        "expires_at": consent_record.expires_at.isoformat() if consent_record.expires_at else None,
        "withdrawn_at": consent_record.withdrawn_at.isoformat() if consent_record.withdrawn_at else None,
        "withdrawal_reason": consent_record.withdrawal_reason,
        "captured_by_user_id": consent_record.captured_by_user_id,
        "review_status": consent_record.review_status,
        "review_notes": consent_record.review_notes,
        "active": consent_record.active,
    }


def parse_actor_form(profile):
    errors = []
    name = clean_form_value("name")
    actor_type = clean_form_value("actor_type")
    status = clean_form_value("status") or "active"
    registration_status = clean_form_value("registration_status")
    source_reference_type = clean_form_value("source_reference_type")
    commodity_category = clean_form_value("commodity_category")
    source_reference = clean_form_value("source_reference")
    date_of_registration = parse_optional_date("date_of_registration", "Date of registration", errors)
    crop_id = parse_optional_int("crop_id", "Crop", errors)
    commodity_id = parse_optional_int("commodity_id", "Commodity", errors)
    region_id = parse_optional_int("region_id", "Region", errors)
    state_id = parse_optional_int("state_id", "State", errors)
    lga_id = parse_optional_int("lga_id", "LGA", errors)
    years_in_export_trade = parse_optional_int("years_in_export_trade", "Years in export trade", errors)
    trade_destination_id = parse_optional_int("trade_destination_id", "Trade destination", errors)
    port_id = parse_optional_int("port_id", "Port", errors)
    certification_type_id = parse_optional_int("certification_type_id", "Certification type", errors)

    if not name:
        errors.append("Actor name is required.")
    if actor_type not in ACTOR_TYPES:
        errors.append("Please select a supported actor type.")
    validate_reference_value("actor_status", status, "actor status", errors, allow_free_text=False)
    validate_reference_value("registration_status", registration_status, "registration status", errors, allow_free_text=False)
    validate_reference_value("source_reference_type", source_reference_type, "source reference type", errors, allow_free_text=False)
    validate_reference_value("contact_role", clean_form_value("contact_role"), "contact role", errors, allow_free_text=True)
    validate_reference_value("capacity_unit", clean_form_value("export_capacity_unit"), "capacity unit", errors, allow_free_text=True)
    validate_reference_value("certification_verification_status", clean_form_value("certification_verification_status"), "certification verification status", errors, allow_free_text=False)
    validate_reference_value("certification_status", clean_form_value("certification_status"), "certification status", errors, allow_free_text=False)
    validate_reference_value("constraint_category", clean_form_value("constraint_category"), "constraint category", errors, allow_free_text=True)
    validate_reference_value("constraint_severity", clean_form_value("constraint_severity"), "constraint severity", errors, allow_free_text=True)
    validate_reference_value("constraint_status", clean_form_value("constraint_status"), "constraint status", errors, allow_free_text=False)

    if status not in COMMON_STATUSES and not reference_option_codes("actor_status"):
        errors.append("Please select a supported actor status.")

    crop = None
    if crop_id:
        crop = get_optional_model(Crop, crop_id, "crop", errors)

    commodity = get_optional_model(Commodity, commodity_id, "commodity", errors)
    if commodity:
        commodity_category = commodity.category or commodity.name
        if not crop_id and commodity.crop_id:
            crop_id = commodity.crop_id

    region = None
    if region_id:
        region = get_optional_model(Region, region_id, "region", errors)

    state = get_optional_model(State, state_id, "state", errors)
    lga = get_optional_model(LGA, lga_id, "LGA", errors)
    if lga:
        state_id = lga.state_id
        state = lga.state
    if state:
        state_id = state.id
        region_id = state.region_id
        region = state.region

    trade_destination = get_optional_model(TradeDestination, trade_destination_id, "trade destination", errors)
    port = get_optional_model(Port, port_id, "port", errors)
    certification_type = get_optional_model(CertificationType, certification_type_id, "certification type", errors)

    constraint_values = [
        clean_form_value("constraint_category"),
        clean_form_value("constraint_text"),
        clean_form_value("constraint_severity"),
    ]
    if any(constraint_values) and not clean_form_value("constraint_text"):
        errors.append("Constraint text is required when adding a constraint.")

    batch_id = parse_optional_int("batch_id", "Draft batch", errors)
    selected_batch = None
    if batch_id:
        selected_batch = PartnerUpdateBatch.query.filter_by(
            id=batch_id,
            partner_organization_id=profile.partner_organization_id,
            status="draft",
        ).first()
        if not selected_batch:
            errors.append("Selected batch must be a draft batch for your partner organization.")

    return errors, {
        "name": name,
        "actor_type": actor_type,
        "status": status,
        "registration_status": registration_status or None,
        "source_reference_type": source_reference_type or None,
        "commodity_id": commodity_id,
        "commodity_category": commodity_category or (crop.name if crop else None),
        "source_reference": source_reference or None,
        "date_of_registration": date_of_registration,
        "crop_id": crop_id,
        "region_id": region_id,
        "state_id": state_id,
        "state_name": state.name if state else clean_form_value("state_name") or None,
        "lga_id": lga_id,
        "lga_name": lga.name if lga else clean_form_value("lga_name") or None,
        "years_in_export_trade": years_in_export_trade,
        "trade_destination_id": trade_destination_id,
        "trade_destination_name": trade_destination.name if trade_destination else clean_form_value("trade_destination_name") or None,
        "port_id": port_id,
        "port_of_exit": port.name if port else clean_form_value("port_of_exit") or None,
        "certification_type_id": certification_type_id,
        "certification_name": certification_type.name if certification_type else clean_form_value("certification_name") or None,
        "selected_batch": selected_batch,
    }


def update_actor_core(actor, values, profile):
    actor.name = values["name"]
    actor.actor_type = values["actor_type"]
    actor.status = values["status"]
    actor.registration_status = values["registration_status"]
    actor.source_reference_type = values["source_reference_type"]
    actor.commodity_id = values["commodity_id"]
    actor.commodity_category = values["commodity_category"]
    actor.source_reference = values["source_reference"]
    actor.date_of_registration = values["date_of_registration"]
    actor.crop_id = values["crop_id"]
    actor.updated_by_id = current_user.id
    actor.partner_organization_id = profile.partner_organization_id


def form_has_any(*field_names):
    return any(clean_form_value(field_name) for field_name in field_names)


def update_actor_location(actor, values):
    if not form_has_any("location_text", "state_name", "lga_name") and not values["region_id"]:
        return

    location = actor.location
    if not location:
        location = ActorLocation(market_actor_id=actor.id)
        db.session.add(location)

    location.location_text = clean_form_value("location_text") or None
    location.location = location.location_text
    location.region_id = values["region_id"]
    location.state_id = values["state_id"]
    location.state_name = values["state_name"]
    location.lga_id = values["lga_id"]
    location.lga_name = values["lga_name"]
    location.country = clean_form_value("country") or "Nigeria"
    location.is_primary = True


def update_actor_contact(actor):
    if not form_has_any("contact_role", "contact_name", "contact_phone", "contact_email", "contact_notes"):
        return

    contact = actor.contacts[0] if actor.contacts else None
    if not contact:
        contact = ActorContact(market_actor_id=actor.id)
        db.session.add(contact)

    contact.contact_role = clean_form_value("contact_role") or None
    contact.contact_name = clean_form_value("contact_name") or None
    contact.phone = clean_form_value("contact_phone") or None
    contact.email = clean_form_value("contact_email") or None
    contact.notes = clean_form_value("contact_notes") or None
    contact.restricted = request.form.get("contact_restricted", "true") == "true"
    contact.visibility_level = "hidden" if contact.restricted else "metadata_only"
    contact.is_primary = True


def update_actor_export_profile(actor, values):
    if not form_has_any("trade_destination_name", "export_capacity", "export_capacity_unit", "port_of_exit", "export_notes") and values["years_in_export_trade"] is None and not values["trade_destination_id"] and not values["port_id"]:
        return

    profile = actor.export_profile
    if not profile:
        profile = ActorExportProfile(market_actor_id=actor.id)
        db.session.add(profile)

    profile.years_in_export_trade = values["years_in_export_trade"]
    profile.trade_destination_id = values["trade_destination_id"]
    profile.trade_destination_name = values["trade_destination_name"]
    profile.export_capacity = clean_form_value("export_capacity") or None
    profile.export_capacity_unit = clean_form_value("export_capacity_unit") or None
    profile.port_id = values["port_id"]
    profile.port_of_exit = values["port_of_exit"]
    profile.notes = clean_form_value("export_notes") or None


def update_actor_certification(actor, values):
    if not form_has_any("certification_type_id", "certification_name", "certificate_number", "reference_number", "issuing_body", "certification_notes"):
        return

    certification = actor.certifications[0] if actor.certifications else None
    if not certification:
        certification = ActorCertification(market_actor_id=actor.id)
        db.session.add(certification)

    certification.certification_type_id = values["certification_type_id"]
    certification.certification_name = values["certification_name"]
    certification.certificate_number = clean_form_value("certificate_number") or None
    certification.reference_number = clean_form_value("reference_number") or None
    certification.issuing_body = clean_form_value("issuing_body") or None
    certification.verification_status = clean_form_value("certification_verification_status") or "unverified"
    certification.status = clean_form_value("certification_status") or "active"
    certification.notes = clean_form_value("certification_notes") or None


def update_actor_constraint(actor):
    if not form_has_any("constraint_category", "constraint_text", "constraint_severity") and not actor.constraints:
        return

    constraint = actor.constraints[0] if actor.constraints else None
    if not constraint:
        constraint = ActorConstraint(market_actor_id=actor.id)
        db.session.add(constraint)

    constraint.constraint_category = clean_form_value("constraint_category") or None
    constraint.constraint_text = clean_form_value("constraint_text")
    constraint.severity = clean_form_value("constraint_severity") or None
    constraint.status = clean_form_value("constraint_status") or "active"


def apply_actor_form(actor, values, profile):
    update_actor_core(actor, values, profile)
    update_actor_location(actor, values)
    update_actor_contact(actor)
    update_actor_export_profile(actor, values)
    update_actor_certification(actor, values)
    update_actor_constraint(actor)


def iso_date(value):
    return value.isoformat() if value else None


def actor_snapshot(actor):
    location = actor.location
    contact = actor.contacts[0] if actor.contacts else None
    export_profile = actor.export_profile
    certification = actor.certifications[0] if actor.certifications else None
    constraint = actor.constraints[0] if actor.constraints else None

    return {
        "id": actor.id,
        "public_id": actor.public_id,
        "partner_organization_id": actor.partner_organization_id,
        "actor_type": actor.actor_type,
        "name": actor.name,
        "crop_id": actor.crop_id,
        "commodity_id": actor.commodity_id,
        "commodity_category": actor.commodity_category,
        "registration_status": actor.registration_status,
        "date_of_registration": iso_date(actor.date_of_registration),
        "status": actor.status,
        "source_reference_type": actor.source_reference_type,
        "source_reference": actor.source_reference,
        "location": {
            "location_text": location.location_text if location else None,
            "region_id": location.region_id if location else None,
            "state_id": location.state_id if location else None,
            "state_name": location.state_name if location else None,
            "lga_id": location.lga_id if location else None,
            "lga_name": location.lga_name if location else None,
            "country": location.country if location else None,
        },
        "contact": {
            "contact_role": contact.contact_role if contact else None,
            "contact_name": contact.contact_name if contact else None,
            "phone": contact.phone if contact else None,
            "email": contact.email if contact else None,
            "restricted": contact.restricted if contact else None,
        },
        "export_profile": {
            "years_in_export_trade": export_profile.years_in_export_trade if export_profile else None,
            "trade_destination_id": export_profile.trade_destination_id if export_profile else None,
            "trade_destination_name": export_profile.trade_destination_name if export_profile else None,
            "export_capacity": export_profile.export_capacity if export_profile else None,
            "export_capacity_unit": export_profile.export_capacity_unit if export_profile else None,
            "port_id": export_profile.port_id if export_profile else None,
            "port_of_exit": export_profile.port_of_exit if export_profile else None,
        },
        "certification": {
            "certification_type_id": certification.certification_type_id if certification else None,
            "certification_name": certification.certification_name if certification else None,
            "certificate_number": certification.certificate_number if certification else None,
            "reference_number": certification.reference_number if certification else None,
            "issuing_body": certification.issuing_body if certification else None,
            "verification_status": certification.verification_status if certification else None,
            "status": certification.status if certification else None,
        },
        "constraint": {
            "constraint_category": constraint.constraint_category if constraint else None,
            "constraint_text": constraint.constraint_text if constraint else None,
            "severity": constraint.severity if constraint else None,
            "status": constraint.status if constraint else None,
        },
    }


def add_audit_log(action, entity_type, entity_id, before_values=None, after_values=None, organization_id=None):
    db.session.add(AuditLog(
        user_id=current_user.id,
        organization_type="partner_organization",
        organization_id=organization_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_values=before_values,
        after_values=after_values,
        ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
        user_agent=request.headers.get("User-Agent"),
    ))


def document_version_file_metadata(document, version=None):
    storage_path = document.storage_path
    download_name = document.original_filename or document.stored_filename or f"document-{document.id}"
    mime_type = document.mime_type

    if version:
        storage_path = version.storage_path or storage_path
        download_name = version.original_filename or download_name
        mime_type = version.content_type or mime_type

    extension_source = download_name or storage_path or ""
    extension = extension_source.rsplit(".", 1)[-1].lower() if "." in extension_source else ""
    return storage_path, download_name, mime_type, extension


def document_preview_policy(document, profile, version=None):
    _storage_path, _download_name, mime_type, extension = document_version_file_metadata(document, version=version)
    document_category = consent_document_category_for_document_type(document.document_type)
    subscriber_shareable = actor_can_share_documents(document.market_actor, "subscriber_portal", document_category)
    partner_shareable = actor_can_share_documents(document.market_actor, "partner_portal", document_category)
    sensitive = bool(document.document_type and document.document_type.sensitive)

    allowed = True
    message = "Preview is available for internal partner review."
    preview_kind = "file"

    if extension not in PREVIEWABLE_DOCUMENT_EXTENSIONS:
        allowed = False
        preview_kind = "unsupported"
        message = "Inline preview is not available for this file type."
    elif sensitive and profile.partner_role == "partner_viewer":
        allowed = False
        preview_kind = "metadata_only"
        message = "Sensitive document types remain metadata-only for partner viewers."

    if extension in {"png", "jpg", "jpeg"}:
        preview_kind = "image"
    elif extension == "pdf":
        preview_kind = "pdf"
    elif extension == "csv" or (mime_type or "").startswith("text/"):
        preview_kind = "text"

    return {
        "allowed": allowed,
        "message": message,
        "preview_kind": preview_kind,
        "sensitive": sensitive,
        "document_category": document_category,
        "partner_shareable": partner_shareable,
        "subscriber_shareable": subscriber_shareable,
        "consent_warning": None if subscriber_shareable else "External subscriber sharing remains blocked by consent.",
    }


def latest_document_extraction_run(document):
    return (
        DocumentExtractionRun.query.filter_by(actor_document_id=document.id)
        .order_by(DocumentExtractionRun.created_at.desc(), DocumentExtractionRun.id.desc())
        .first()
    )


def extraction_profile_for_document(document):
    document_type = document.document_type
    document_type_code = document_type.code if document_type else None
    document_type_name = (document_type.name if document_type else "").lower()
    if document_type_code == "certificate_of_origin" or "certificate of origin" in document_type_name:
        return "certificate_of_origin_v1", CERTIFICATE_OF_ORIGIN_FIELDS
    return "generic_document_metadata_v1", GENERIC_EXTRACTION_FIELDS


def normalized_field_key(value):
    cleaned = re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower()).strip("_")
    return FIELD_ALIASES.get(cleaned, cleaned)


def read_safe_text_excerpt(file_path):
    content = file_path.read_bytes()[:SAFE_EXCERPT_BYTES]
    return content.decode("utf-8", errors="ignore").replace("\x00", " ").strip()


def extract_key_value_fields(raw_text, allowed_fields):
    allowed = {field_name for field_name, _label in allowed_fields}
    extracted_fields = {}
    evidence = {}

    for line_number, line in enumerate((raw_text or "").splitlines(), start=1):
        if ":" in line:
            key, value = line.split(":", 1)
        elif "=" in line:
            key, value = line.split("=", 1)
        else:
            continue

        field_name = normalized_field_key(key)
        cleaned_value = value.strip()
        if field_name not in allowed or not cleaned_value or field_name in extracted_fields:
            continue

        extracted_fields[field_name] = cleaned_value[:500]
        evidence[field_name] = {
            "source": "text_excerpt",
            "line_number": line_number,
            "excerpt": line.strip()[:240],
            "page": None,
            "bounding_box": None,
        }

    return extracted_fields, evidence


def document_field_current_value(document, field_name):
    if field_name == "document_reference_number":
        return document.document_reference_number or ""
    if field_name == "issuing_body":
        return document.issuing_body or ""
    if field_name == "issued_at":
        return document.issued_at.isoformat() if document.issued_at else ""
    if field_name == "expires_at":
        return document.expires_at.isoformat() if document.expires_at else ""
    if field_name == "crop_or_commodity":
        if document.linked_commodity:
            return document.linked_commodity.name or ""
        if document.linked_crop:
            return document.linked_crop.name or ""
    metadata = document.metadata_json or {}
    value = metadata.get(field_name)
    return "" if value is None else str(value)


def normalized_comparison_value(value):
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def build_metadata_mismatches(document, extracted_fields):
    mismatches = []
    for field_name in RECONCILABLE_DOCUMENT_FIELDS:
        extracted_value = extracted_fields.get(field_name)
        if not extracted_value:
            continue
        current_value = document_field_current_value(document, field_name)
        if normalized_comparison_value(current_value) != normalized_comparison_value(extracted_value):
            mismatches.append({
                "field_name": field_name,
                "current_value": current_value,
                "extracted_value": extracted_value,
            })
    return mismatches


def parse_extracted_date(value):
    if not value:
        return None
    for date_format in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(str(value).strip(), date_format).date()
        except ValueError:
            continue
    return None


def build_extraction_risk_flags(document, extracted_fields, mismatches):
    risk_flags = []
    document_type = document.document_type

    if document_type and document_type.requires_reference_number and not extracted_fields.get("document_reference_number"):
        risk_flags.append("missing_reference_number")
    if document_type and document_type.requires_issuing_body and not extracted_fields.get("issuing_body"):
        risk_flags.append("missing_issuing_body")
    if mismatches:
        risk_flags.append("metadata_mismatch")

    expiry_value = extracted_fields.get("expires_at") or (document.expires_at.isoformat() if document.expires_at else "")
    expiry_date = parse_extracted_date(expiry_value)
    if expiry_date:
        days_until_expiry = (expiry_date - datetime.utcnow().date()).days
        if days_until_expiry < 0:
            risk_flags.append("expired_document")
        elif days_until_expiry <= 60:
            risk_flags.append("renewal_due_soon")

    if not extracted_fields:
        risk_flags.append("no_fields_extracted")

    return risk_flags


def build_expiry_renewal_status(document, extracted_fields):
    expiry_value = extracted_fields.get("expires_at") or (document.expires_at.isoformat() if document.expires_at else "")
    expiry_date = parse_extracted_date(expiry_value)
    if not expiry_date:
        return {"status": "not_available", "expires_at": None, "days_until_expiry": None}

    days_until_expiry = (expiry_date - datetime.utcnow().date()).days
    if days_until_expiry < 0:
        status = "expired"
    elif days_until_expiry <= 60:
        status = "renewal_due_soon"
    else:
        status = "current"
    return {
        "status": status,
        "expires_at": expiry_date.isoformat(),
        "days_until_expiry": days_until_expiry,
    }


def calculate_extraction_quality_score(profile_fields, extracted_fields, confidence_json, mismatches, risk_flags):
    total_fields = max(len(profile_fields), 1)
    coverage = len([field_name for field_name, _label in profile_fields if extracted_fields.get(field_name)]) / total_fields
    confidence_values = [confidence_json.get(field_name, 0) for field_name, _label in profile_fields]
    average_confidence = sum(confidence_values) / len(confidence_values) if confidence_values else 0
    penalty = min((len(mismatches) * 5) + (len(risk_flags) * 3), 35)
    return max(0, min(100, round((coverage * 55) + (average_confidence * 45) - penalty)))


def document_extraction_payload(document, version, file_path):
    profile_code, profile_fields = extraction_profile_for_document(document)
    raw_text_excerpt = read_safe_text_excerpt(file_path)
    extracted_fields, evidence = extract_key_value_fields(raw_text_excerpt, profile_fields)
    confidence_json = {
        field_name: (0.86 if extracted_fields.get(field_name) else 0.0)
        for field_name, _label in profile_fields
    }
    provenance = {
        field_name: {
            "extractor_type": "template",
            "template_profile_code": profile_code,
            "source": "current_document_version",
            "actor_document_version_id": version.id if version else None,
        }
        for field_name, _label in profile_fields
    }
    mismatches = build_metadata_mismatches(document, extracted_fields)
    risk_flags = build_extraction_risk_flags(document, extracted_fields, mismatches)
    expiry_renewal = build_expiry_renewal_status(document, extracted_fields)
    quality_score = calculate_extraction_quality_score(profile_fields, extracted_fields, confidence_json, mismatches, risk_flags)
    status = "needs_review" if mismatches or risk_flags else "completed"
    intelligence_status = "needs_reconciliation" if mismatches else "extracted"

    return {
        "template_profile_code": profile_code,
        "profile_fields": profile_fields,
        "status": status,
        "document_intelligence_status": intelligence_status,
        "raw_text_excerpt": raw_text_excerpt[:1000],
        "extracted_fields": extracted_fields,
        "confidence_json": confidence_json,
        "evidence": evidence,
        "provenance": provenance,
        "mismatches": mismatches,
        "risk_flags": risk_flags,
        "expiry_renewal": expiry_renewal,
        "quality_score": quality_score,
    }


def create_reconciliation_rows(document, extraction_run, payload):
    for field_name, field_label in payload["profile_fields"]:
        current_value = document_field_current_value(document, field_name)
        extracted_value = payload["extracted_fields"].get(field_name, "")
        db.session.add(DocumentFieldReconciliation(
            actor_document_id=document.id,
            extraction_run_id=extraction_run.id,
            field_name=field_name,
            field_label=field_label,
            current_value=current_value,
            extracted_value=extracted_value,
            confidence=payload["confidence_json"].get(field_name, 0.0),
            status="pending",
            evidence_json=payload["evidence"].get(field_name, {
                "source": "not_extracted",
                "page": None,
                "bounding_box": None,
            }),
            provenance_json=payload["provenance"].get(field_name, {}),
            risk_flags_json=[
                mismatch["field_name"]
                for mismatch in payload["mismatches"]
                if mismatch["field_name"] == field_name
            ],
            decision_history_json=[],
        ))


def latest_reconciliation_rows(extraction_run):
    if not extraction_run:
        return []
    return (
        DocumentFieldReconciliation.query.filter_by(extraction_run_id=extraction_run.id)
        .order_by(DocumentFieldReconciliation.id)
        .all()
    )


def apply_reconciled_document_value(document, field_name, value, errors):
    if field_name not in RECONCILABLE_DOCUMENT_FIELDS:
        return False

    cleaned_value = (value or "").strip()
    attribute = RECONCILABLE_DOCUMENT_FIELDS[field_name]
    if field_name in {"issued_at", "expires_at"}:
        parsed_date = parse_extracted_date(cleaned_value)
        if cleaned_value and not parsed_date:
            errors.append(f"{field_name.replace('_', ' ').title()} must use a supported date format.")
            return False
        setattr(document, attribute, parsed_date)
    else:
        setattr(document, attribute, cleaned_value or None)
    return True


def append_reconciliation_decision(row, action, accepted_value, notes):
    history = list(row.decision_history_json or [])
    history.append({
        "action": action,
        "accepted_value": accepted_value,
        "notes": notes or None,
        "reviewed_by_user_id": current_user.id,
        "reviewed_at": datetime.utcnow().isoformat(),
    })
    row.decision_history_json = history


def update_extraction_run_status(extraction_run):
    rows = latest_reconciliation_rows(extraction_run)
    if not rows:
        extraction_run.status = "completed"
        extraction_run.document_intelligence_status = "extracted"
        return

    if any(row.status == "pending" for row in rows):
        extraction_run.status = "needs_review"
        extraction_run.document_intelligence_status = "needs_reconciliation"
    else:
        extraction_run.status = "completed"
        extraction_run.document_intelligence_status = "reconciled"


def get_or_create_direct_change_batch(profile):
    month = datetime.utcnow().strftime("%Y-%m")
    title = f"Direct actor changes - {month}"
    batch = PartnerUpdateBatch.query.filter_by(
        partner_organization_id=profile.partner_organization_id,
        title=title,
        dataset_type="actor_registry",
        status="draft",
    ).first()

    if batch:
        return batch

    batch = PartnerUpdateBatch(
        partner_organization_id=profile.partner_organization_id,
        title=title,
        dataset_type="actor_registry",
        reporting_month=month,
        status="draft",
        notes="Auto-created by the partner actor form to track direct create/edit changes.",
    )
    db.session.add(batch)
    db.session.flush()
    add_audit_log(
        "partner_batch_created",
        "partner_update_batch",
        batch.id,
        after_values=batch_snapshot(batch),
        organization_id=profile.partner_organization_id,
    )
    return batch


def create_record_change(batch, actor, change_type, before_values, after_values):
    db.session.add(PartnerRecordChange(
        partner_update_batch_id=batch.id,
        market_actor_id=actor.id,
        created_by_user_id=current_user.id,
        entity_type="market_actor",
        entity_id=actor.id,
        change_type=change_type,
        before_values=before_values,
        after_values=after_values,
        status=batch.status,
    ))


def batch_snapshot(batch):
    return {
        "id": batch.id,
        "partner_organization_id": batch.partner_organization_id,
        "title": batch.title,
        "dataset_type": batch.dataset_type,
        "reporting_month": batch.reporting_month,
        "status": batch.status,
        "submitted_at": batch.submitted_at.isoformat() if batch.submitted_at else None,
    }


def actor_form_context(profile, actor=None):
    commodities = Commodity.query.filter_by(active=True).order_by(Commodity.name).all()
    states = State.query.filter_by(active=True).order_by(State.name).all()
    lgas = LGA.query.filter_by(active=True).order_by(LGA.name).all()
    trade_destinations = TradeDestination.query.filter_by(active=True).order_by(TradeDestination.name).all()
    ports = Port.query.filter_by(active=True).order_by(Port.name).all()
    certification_types = CertificationType.query.filter_by(active=True).order_by(CertificationType.name).all()

    return {
        "profile": profile,
        "organization": profile.partner_organization,
        "actor": actor,
        "actor_types": ACTOR_TYPES,
        "status_choices": COMMON_STATUSES,
        "reference_options": get_reference_options_by_category(),
        "regions": Region.query.filter_by(active=True).order_by(Region.name).all(),
        "crops": Crop.query.filter_by(active=True).order_by(Crop.name).all(),
        "commodities": commodities,
        "states": states,
        "lgas": lgas,
        "trade_destinations": trade_destinations,
        "ports": ports,
        "certification_types": certification_types,
        "draft_batches": PartnerUpdateBatch.query.filter_by(
            partner_organization_id=profile.partner_organization_id,
            status="draft",
        ).order_by(PartnerUpdateBatch.updated_at.desc()).all(),
    }


@partner_bp.route("/")
@login_required
@require_partner_user
def dashboard():
    profile = get_current_partner_profile()
    org = profile.partner_organization
    actor_rows = MarketActor.query.filter_by(partner_organization_id=org.id).all()
    actor_count = len(actor_rows)
    quality_scores = [calculate_actor_quality_score(actor) for actor in actor_rows]
    average_quality_score = round(sum(item["score"] for item in quality_scores) / actor_count) if actor_count else None
    draft_batch_count = PartnerUpdateBatch.query.filter_by(
        partner_organization_id=org.id,
        status="draft",
    ).count()
    submitted_batch_count = PartnerUpdateBatch.query.filter_by(
        partner_organization_id=org.id,
        status="submitted",
    ).count()

    return render_template(
        "partner/dashboard.html",
        profile=profile,
        organization=org,
        actor_count=actor_count,
        average_quality_score=average_quality_score,
        draft_batch_count=draft_batch_count,
        submitted_batch_count=submitted_batch_count,
        can_edit=can_edit_partner_records(profile),
        can_submit=can_submit_partner_batches(profile),
    )


@partner_bp.route("/actors")
@login_required
@require_partner_user
def actors():
    profile = get_current_partner_profile()
    actor_rows = (
        MarketActor.query.filter_by(partner_organization_id=profile.partner_organization_id)
        .order_by(MarketActor.updated_at.desc())
        .all()
    )
    quality_scores = {actor.id: calculate_actor_quality_score(actor) for actor in actor_rows}
    return render_template(
        "partner/actors.html",
        profile=profile,
        organization=profile.partner_organization,
        actors=actor_rows,
        quality_scores=quality_scores,
        can_edit=can_edit_partner_records(profile),
    )


@partner_bp.route("/actors/new", methods=["GET", "POST"])
@login_required
@require_partner_user
@require_partner_role(*EDITOR_ROLES)
def new_actor():
    profile = get_current_partner_profile()

    if request.method == "POST":
        errors, values = parse_actor_form(profile)
        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("partner/actor_form.html", **actor_form_context(profile))

        actor = MarketActor(
            partner_organization_id=profile.partner_organization_id,
            created_by_user_id=current_user.id,
            updated_by_id=current_user.id,
            actor_type=values["actor_type"],
            name=values["name"],
        )
        db.session.add(actor)
        db.session.flush()
        apply_actor_form(actor, values, profile)
        db.session.flush()

        after_values = actor_snapshot(actor)
        batch = values["selected_batch"] or get_or_create_direct_change_batch(profile)
        create_record_change(batch, actor, "create", None, after_values)
        add_audit_log(
            "partner_actor_created",
            "market_actor",
            actor.id,
            after_values=after_values,
            organization_id=profile.partner_organization_id,
        )
        db.session.commit()

        flash("Actor record created.", "success")
        return redirect(url_for("partner.actor_detail", actor_id=actor.id))

    return render_template("partner/actor_form.html", **actor_form_context(profile))


@partner_bp.route("/actors/<int:actor_id>")
@login_required
@require_partner_user
def actor_detail(actor_id):
    profile = get_current_partner_profile()
    actor = get_partner_actor_or_404(actor_id, profile)
    consent_status, current_consent = consent_status_for_actor(actor)
    return render_template(
        "partner/actor_detail.html",
        profile=profile,
        organization=profile.partner_organization,
        actor=actor,
        quality_score=calculate_actor_quality_score(actor),
        can_edit=can_edit_partner_records(profile),
        show_restricted_contacts=can_view_restricted_contacts(profile),
        consent_status=consent_status,
        current_consent=current_consent,
        active_consent=get_active_actor_consent(actor),
        data_shareable=actor_data_is_externally_shareable(actor),
        documents_shareable=actor_documents_are_externally_shareable(actor),
    )


@partner_bp.route("/actors/<int:actor_id>/consent")
@login_required
@require_partner_user
def actor_consent(actor_id):
    profile = get_current_partner_profile()
    actor = get_partner_actor_or_404(actor_id, profile)
    consent_status, current_consent = consent_status_for_actor(actor)
    consent_records = (
        ActorConsentRecord.query.filter_by(
            market_actor_id=actor.id,
            partner_organization_id=profile.partner_organization_id,
        )
        .order_by(ActorConsentRecord.updated_at.desc(), ActorConsentRecord.id.desc())
        .all()
    )
    return render_template(
        "partner/consent.html",
        profile=profile,
        organization=profile.partner_organization,
        actor=actor,
        consent_records=consent_records,
        consent_status=consent_status,
        current_consent=current_consent,
        active_consent=get_active_actor_consent(actor),
        data_shareable=actor_data_is_externally_shareable(actor),
        documents_shareable=actor_documents_are_externally_shareable(actor),
        can_edit=can_edit_partner_records(profile),
    )


@partner_bp.route("/actors/<int:actor_id>/consent/new", methods=["GET", "POST"])
@login_required
@require_partner_user
@require_partner_role(*EDITOR_ROLES)
def new_actor_consent(actor_id):
    profile = get_current_partner_profile()
    actor = get_partner_actor_or_404(actor_id, profile)

    if request.method == "POST":
        errors, values = parse_consent_form(actor, profile)
        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("partner/consent_form.html", **consent_form_context(profile, actor))

        deactivate_prior_actor_consents(actor, profile)
        consent_record = ActorConsentRecord(
            market_actor_id=actor.id,
            partner_organization_id=profile.partner_organization_id,
            captured_by_user_id=current_user.id,
            active=True,
        )
        apply_consent_values(consent_record, values)
        db.session.add(consent_record)
        db.session.flush()
        add_audit_log(
            "consent_created",
            "actor_consent_record",
            consent_record.id,
            after_values=consent_snapshot(consent_record),
            organization_id=profile.partner_organization_id,
        )
        db.session.commit()

        flash("Consent record created.", "success")
        return redirect(url_for("partner.actor_consent", actor_id=actor.id))

    return render_template("partner/consent_form.html", **consent_form_context(profile, actor))


@partner_bp.route("/actors/<int:actor_id>/consent/<int:consent_id>/withdraw", methods=["POST"])
@login_required
@require_partner_user
@require_partner_role(*EDITOR_ROLES)
def withdraw_actor_consent(actor_id, consent_id):
    profile = get_current_partner_profile()
    actor = get_partner_actor_or_404(actor_id, profile)
    consent_record = get_partner_consent_or_404(actor.id, consent_id, profile)
    withdrawal_reason = clean_form_value("withdrawal_reason")
    if not withdrawal_reason:
        flash("Withdrawal reason is required.", "error")
        return redirect(url_for("partner.actor_consent", actor_id=actor.id))

    before_values = consent_snapshot(consent_record)
    consent_record.consent_status = "withdrawn"
    consent_record.withdrawn_at = datetime.utcnow()
    consent_record.withdrawal_reason = withdrawal_reason
    consent_record.active = False
    db.session.flush()
    after_values = consent_snapshot(consent_record)
    add_audit_log(
        "consent_withdrawn",
        "actor_consent_record",
        consent_record.id,
        before_values=before_values,
        after_values=after_values,
        organization_id=profile.partner_organization_id,
    )
    db.session.commit()

    flash("Consent withdrawn.", "success")
    return redirect(url_for("partner.actor_consent", actor_id=actor.id))


@partner_bp.route("/actors/<int:actor_id>/documents")
@login_required
@require_partner_user
def actor_documents(actor_id):
    profile = get_current_partner_profile()
    actor = get_partner_actor_or_404(actor_id, profile)
    documents = (
        ActorDocument.query.filter_by(
            market_actor_id=actor.id,
            partner_organization_id=profile.partner_organization_id,
        )
        .order_by(ActorDocument.updated_at.desc())
        .all()
    )
    return render_template(
        "partner/documents.html",
        profile=profile,
        organization=profile.partner_organization,
        actor=actor,
        documents=documents,
        can_edit=can_edit_partner_records(profile),
        can_download=can_download_partner_documents(profile),
    )


@partner_bp.route("/actors/<int:actor_id>/documents/new", methods=["GET", "POST"])
@login_required
@require_partner_user
@require_partner_role(*EDITOR_ROLES)
def new_actor_document(actor_id):
    profile = get_current_partner_profile()
    actor = get_partner_actor_or_404(actor_id, profile)

    if request.method == "POST":
        errors, values = parse_document_form(actor)
        upload_data, upload_errors = validate_document_upload(request.files.get("file"))
        errors.extend(upload_errors)
        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("partner/document_form.html", **document_form_context(profile, actor=actor))

        document = ActorDocument(
            market_actor_id=actor.id,
            partner_organization_id=profile.partner_organization_id,
            document_type_id=values["document_type"].id,
            uploaded_by_user_id=current_user.id,
            title=values["title"],
            document_status="submitted",
            review_status="pending",
            redaction_status="not_redacted",
            version_number=1,
            is_current_version=True,
        )
        db.session.add(document)
        db.session.flush()
        apply_document_metadata(document, values)
        file_metadata = save_document_upload(actor, document, upload_data, version_number=1)
        for key, value in file_metadata.items():
            setattr(document, key, value)

        version = ActorDocumentVersion(
            actor_document_id=document.id,
            version_number=1,
            storage_backend=current_app.config.get("DOCUMENT_STORAGE_BACKEND", "local_private"),
            storage_path=document.storage_path,
            original_filename=document.original_filename,
            content_type=document.mime_type,
            file_size_bytes=document.file_size,
            checksum_sha256=document.file_hash,
            uploaded_by_user_id=current_user.id,
            document_status=document.document_status,
        )
        db.session.add(version)
        db.session.flush()
        add_audit_log(
            "partner_document_created",
            "actor_document",
            document.id,
            after_values=document_snapshot(document),
            organization_id=profile.partner_organization_id,
        )
        db.session.commit()

        flash("Document uploaded.", "success")
        return redirect(url_for("partner.document_detail", document_id=document.id))

    return render_template("partner/document_form.html", **document_form_context(profile, actor=actor))


@partner_bp.route("/documents/<int:document_id>")
@login_required
@require_partner_user
def document_detail(document_id):
    profile = get_current_partner_profile()
    document = get_partner_document_or_404(document_id, profile)
    actor = document.market_actor
    version = current_document_version(document)
    add_document_access_log(document, "metadata_view", version=version)
    db.session.commit()
    document_consent_category = consent_document_category_for_document_type(document.document_type)
    preview_policy = document_preview_policy(document, profile, version=version)
    latest_extraction_run = latest_document_extraction_run(document)
    return render_template(
        "partner/document_detail.html",
        profile=profile,
        organization=profile.partner_organization,
        document=document,
        actor=actor,
        current_version=version,
        can_edit=can_edit_partner_records(profile),
        can_download=can_download_partner_documents(profile),
        active_consent=get_active_actor_consent(actor),
        document_shareable=actor_can_share_documents(actor, "subscriber_portal", document_consent_category),
        document_consent_category=document_consent_category,
        preview_policy=preview_policy,
        latest_extraction_run=latest_extraction_run,
        extraction_rows=latest_reconciliation_rows(latest_extraction_run),
        can_extract=can_edit_partner_records(profile),
    )


@partner_bp.route("/documents/<int:document_id>/preview")
@login_required
@require_partner_user
def preview_document(document_id):
    profile = get_current_partner_profile()
    document = get_partner_document_or_404(document_id, profile)
    version = current_document_version(document)
    preview_policy = document_preview_policy(document, profile, version=version)
    if not preview_policy["allowed"]:
        abort(403 if preview_policy["preview_kind"] == "metadata_only" else 415)

    storage_path, download_name, mime_type, _extension = document_version_file_metadata(document, version=version)
    if not storage_path:
        abort(404)

    file_path = resolve_document_storage_path(storage_path)
    if not file_path.exists() or not file_path.is_file():
        abort(404)

    add_document_access_log(document, "preview", version=version)
    db.session.commit()

    response = send_file(
        file_path,
        as_attachment=False,
        download_name=download_name,
        mimetype=mime_type or mimetypes.guess_type(download_name)[0],
    )
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-FieldSight-External-Shareable"] = "true" if preview_policy["subscriber_shareable"] else "false"
    return response


@partner_bp.route("/documents/<int:document_id>/extract", methods=["POST"])
@login_required
@require_partner_user
@require_partner_role(*EDITOR_ROLES)
def extract_document(document_id):
    profile = get_current_partner_profile()
    document = get_partner_document_or_404(document_id, profile)
    version = current_document_version(document)
    storage_path, download_name, _mime_type, _extension = document_version_file_metadata(document, version=version)
    if not storage_path:
        abort(404)

    file_path = resolve_document_storage_path(storage_path)
    if not file_path.exists() or not file_path.is_file():
        abort(404)

    document_category = consent_document_category_for_document_type(document.document_type)
    externally_shareable = actor_can_share_documents(document.market_actor, "subscriber_portal", document_category)
    payload = document_extraction_payload(document, version, file_path)
    if payload["status"] not in DOCUMENT_EXTRACTION_STATUSES:
        payload["status"] = "needs_review"
    if payload["document_intelligence_status"] not in DOCUMENT_INTELLIGENCE_STATUSES:
        payload["document_intelligence_status"] = "needs_reconciliation"

    extraction_run = DocumentExtractionRun(
        actor_document_id=document.id,
        actor_document_version_id=version.id if version else None,
        status=payload["status"],
        extractor_type="template",
        document_type_code=document.document_type.code if document.document_type else None,
        template_profile_code=payload["template_profile_code"],
        source_filename=download_name,
        extracted_fields_json=payload["extracted_fields"],
        confidence_json=payload["confidence_json"],
        field_evidence_json=payload["evidence"],
        provenance_json=payload["provenance"],
        metadata_mismatches_json=payload["mismatches"],
        risk_flags_json=payload["risk_flags"],
        expiry_renewal_json=payload["expiry_renewal"],
        quality_score=payload["quality_score"],
        document_intelligence_status=payload["document_intelligence_status"],
        raw_text_excerpt=payload["raw_text_excerpt"],
        created_by_user_id=current_user.id,
    )
    db.session.add(extraction_run)
    db.session.flush()
    create_reconciliation_rows(document, extraction_run, payload)
    add_audit_log(
        "partner_document_extraction_created",
        "actor_document",
        document.id,
        after_values={
            "extraction_run_id": extraction_run.id,
            "status": extraction_run.status,
            "template_profile_code": extraction_run.template_profile_code,
            "quality_score": extraction_run.quality_score,
            "metadata_mismatch_count": len(payload["mismatches"]),
            "external_subscriber_shareable": externally_shareable,
        },
        organization_id=profile.partner_organization_id,
    )
    db.session.commit()

    if not externally_shareable:
        flash("Metadata was extracted for internal review. External sharing remains blocked unless active consent allows it.", "warning")
    else:
        flash("Metadata extraction run created for review.", "success")
    return redirect(url_for("partner.document_detail", document_id=document.id))


@partner_bp.route("/documents/<int:document_id>/reconcile", methods=["GET", "POST"])
@login_required
@require_partner_user
@require_partner_role(*EDITOR_ROLES)
def reconcile_document(document_id):
    profile = get_current_partner_profile()
    document = get_partner_document_or_404(document_id, profile)
    extraction_run = latest_document_extraction_run(document)
    if not extraction_run:
        flash("Run extraction before reconciling document fields.", "error")
        return redirect(url_for("partner.document_detail", document_id=document.id))

    rows = latest_reconciliation_rows(extraction_run)
    if request.method == "POST":
        before_values = document_snapshot(document)
        errors = []
        for row in rows:
            action = clean_form_value(f"action_{row.id}")
            notes = clean_form_value(f"notes_{row.id}")
            if not action:
                continue
            if action not in DOCUMENT_RECONCILIATION_STATUSES:
                errors.append(f"Unsupported reconciliation action for {row.field_label or row.field_name}.")
                continue

            accepted_value = row.extracted_value
            if action == "accepted":
                row.status = "accepted"
            elif action == "rejected":
                accepted_value = ""
                row.status = "rejected"
            elif action == "manually_overridden":
                accepted_value = clean_form_value(f"override_{row.id}")
                row.status = "manually_overridden"
            else:
                row.status = "pending"
                continue

            row.accepted_value = accepted_value or None
            row.manual_correction_notes = notes or None
            row.reviewed_by_user_id = current_user.id
            row.reviewed_at = datetime.utcnow()
            if row.status in {"accepted", "manually_overridden"}:
                apply_reconciled_document_value(document, row.field_name, accepted_value, errors)
            append_reconciliation_decision(row, row.status, accepted_value, notes)

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template(
                "partner/document_reconcile.html",
                profile=profile,
                organization=profile.partner_organization,
                document=document,
                actor=document.market_actor,
                extraction_run=extraction_run,
                rows=rows,
                reconcilable_fields=RECONCILABLE_DOCUMENT_FIELDS,
            )

        update_extraction_run_status(extraction_run)
        db.session.flush()
        after_values = document_snapshot(document)
        add_audit_log(
            "partner_document_reconciliation_updated",
            "actor_document",
            document.id,
            before_values=before_values,
            after_values={
                "document": after_values,
                "extraction_run_id": extraction_run.id,
                "document_intelligence_status": extraction_run.document_intelligence_status,
            },
            organization_id=profile.partner_organization_id,
        )
        db.session.commit()
        flash("Document field reconciliation saved.", "success")
        return redirect(url_for("partner.document_detail", document_id=document.id))

    return render_template(
        "partner/document_reconcile.html",
        profile=profile,
        organization=profile.partner_organization,
        document=document,
        actor=document.market_actor,
        extraction_run=extraction_run,
        rows=rows,
        reconcilable_fields=RECONCILABLE_DOCUMENT_FIELDS,
    )


@partner_bp.route("/documents/<int:document_id>/edit", methods=["GET", "POST"])
@login_required
@require_partner_user
@require_partner_role(*EDITOR_ROLES)
def edit_document(document_id):
    profile = get_current_partner_profile()
    document = get_partner_document_or_404(document_id, profile)
    actor = document.market_actor

    if request.method == "POST":
        errors, values = parse_document_form(actor)
        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("partner/document_form.html", **document_form_context(profile, actor=actor, document=document))

        before_values = document_snapshot(document)
        apply_document_metadata(document, values)
        db.session.flush()
        after_values = document_snapshot(document)
        add_audit_log(
            "partner_document_metadata_updated",
            "actor_document",
            document.id,
            before_values=before_values,
            after_values=after_values,
            organization_id=profile.partner_organization_id,
        )
        db.session.commit()

        flash("Document metadata updated.", "success")
        return redirect(url_for("partner.document_detail", document_id=document.id))

    return render_template("partner/document_form.html", **document_form_context(profile, actor=actor, document=document))


@partner_bp.route("/documents/<int:document_id>/versions/new", methods=["GET", "POST"])
@login_required
@require_partner_user
@require_partner_role(*EDITOR_ROLES)
def new_document_version(document_id):
    profile = get_current_partner_profile()
    document = get_partner_document_or_404(document_id, profile)
    actor = document.market_actor

    if request.method == "POST":
        upload_data, errors = validate_document_upload(request.files.get("file"))
        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("partner/document_version_form.html", **document_form_context(profile, actor=actor, document=document))

        before_values = document_snapshot(document)
        next_version_number = (document.version_number or 1) + 1
        file_metadata = save_document_upload(actor, document, upload_data, version_number=next_version_number)
        for key, value in file_metadata.items():
            setattr(document, key, value)
        document.version_number = next_version_number
        document.uploaded_by_user_id = current_user.id
        document.document_status = "submitted"
        document.review_status = "pending"
        document.is_current_version = True

        version = ActorDocumentVersion(
            actor_document_id=document.id,
            version_number=next_version_number,
            storage_backend=current_app.config.get("DOCUMENT_STORAGE_BACKEND", "local_private"),
            storage_path=document.storage_path,
            original_filename=document.original_filename,
            content_type=document.mime_type,
            file_size_bytes=document.file_size,
            checksum_sha256=document.file_hash,
            uploaded_by_user_id=current_user.id,
            document_status=document.document_status,
        )
        db.session.add(version)
        db.session.flush()
        after_values = document_snapshot(document)
        add_audit_log(
            "partner_document_version_uploaded",
            "actor_document",
            document.id,
            before_values=before_values,
            after_values=after_values,
            organization_id=profile.partner_organization_id,
        )
        db.session.commit()

        flash("New document version uploaded.", "success")
        return redirect(url_for("partner.document_detail", document_id=document.id))

    return render_template("partner/document_version_form.html", **document_form_context(profile, actor=actor, document=document))


@partner_bp.route("/documents/<int:document_id>/download")
@login_required
@require_partner_user
def download_document(document_id):
    profile = get_current_partner_profile()
    document = get_partner_document_or_404(document_id, profile)
    if not can_download_partner_documents(profile):
        flash("Your partner role does not allow document downloads.", "error")
        return redirect(url_for("partner.document_detail", document_id=document.id))

    version = current_document_version(document)
    storage_path = document.storage_path
    download_name = document.original_filename or document.stored_filename or f"document-{document.id}"
    if version and version.storage_path:
        storage_path = version.storage_path
        download_name = version.original_filename or download_name

    if not storage_path:
        abort(404)

    file_path = resolve_document_storage_path(storage_path)
    if not file_path.exists() or not file_path.is_file():
        abort(404)

    add_document_access_log(document, "download", version=version)
    db.session.commit()

    return send_file(
        file_path,
        as_attachment=True,
        download_name=download_name,
        mimetype=document.mime_type or (version.content_type if version else None),
    )


@partner_bp.route("/actors/<int:actor_id>/edit", methods=["GET", "POST"])
@login_required
@require_partner_user
@require_partner_role(*EDITOR_ROLES)
def edit_actor(actor_id):
    profile = get_current_partner_profile()
    actor = get_partner_actor_or_404(actor_id, profile)

    if request.method == "POST":
        errors, values = parse_actor_form(profile)
        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("partner/actor_form.html", **actor_form_context(profile, actor=actor))

        before_values = actor_snapshot(actor)
        apply_actor_form(actor, values, profile)
        db.session.flush()
        after_values = actor_snapshot(actor)
        batch = values["selected_batch"] or get_or_create_direct_change_batch(profile)
        create_record_change(batch, actor, "update", before_values, after_values)
        add_audit_log(
            "partner_actor_updated",
            "market_actor",
            actor.id,
            before_values=before_values,
            after_values=after_values,
            organization_id=profile.partner_organization_id,
        )
        db.session.commit()

        flash("Actor record updated.", "success")
        return redirect(url_for("partner.actor_detail", actor_id=actor.id))

    return render_template("partner/actor_form.html", **actor_form_context(profile, actor=actor))


@partner_bp.route("/batches")
@login_required
@require_partner_user
def batches():
    profile = get_current_partner_profile()
    batch_rows = (
        PartnerUpdateBatch.query.filter_by(partner_organization_id=profile.partner_organization_id)
        .order_by(PartnerUpdateBatch.updated_at.desc())
        .all()
    )
    return render_template(
        "partner/batches.html",
        profile=profile,
        organization=profile.partner_organization,
        batches=batch_rows,
        can_edit=can_edit_partner_records(profile),
    )


@partner_bp.route("/batches/new", methods=["GET", "POST"])
@login_required
@require_partner_user
@require_partner_role(*EDITOR_ROLES)
def new_batch():
    profile = get_current_partner_profile()

    if request.method == "POST":
        title = clean_form_value("title")
        dataset_type = clean_form_value("dataset_type") or "actor_registry"
        reporting_month = clean_form_value("reporting_month")
        notes = clean_form_value("notes")

        if not title:
            flash("Batch title is required.", "error")
            return render_template("partner/batch_form.html", profile=profile, organization=profile.partner_organization, dataset_types=PARTNER_DATASET_TYPES)
        if dataset_type not in PARTNER_DATASET_TYPES:
            flash("Please select a supported dataset type.", "error")
            return render_template("partner/batch_form.html", profile=profile, organization=profile.partner_organization, dataset_types=PARTNER_DATASET_TYPES)

        batch = PartnerUpdateBatch(
            partner_organization_id=profile.partner_organization_id,
            title=title,
            dataset_type=dataset_type,
            reporting_month=reporting_month or None,
            status="draft",
            notes=notes or None,
        )
        db.session.add(batch)
        db.session.flush()
        add_audit_log(
            "partner_batch_created",
            "partner_update_batch",
            batch.id,
            after_values=batch_snapshot(batch),
            organization_id=profile.partner_organization_id,
        )
        db.session.commit()

        flash("Draft batch created.", "success")
        return redirect(url_for("partner.batch_detail", batch_id=batch.id))

    return render_template(
        "partner/batch_form.html",
        profile=profile,
        organization=profile.partner_organization,
        dataset_types=PARTNER_DATASET_TYPES,
    )


@partner_bp.route("/batches/<int:batch_id>")
@login_required
@require_partner_user
def batch_detail(batch_id):
    profile = get_current_partner_profile()
    batch = get_partner_batch_or_404(batch_id, profile)
    return render_template(
        "partner/batch_detail.html",
        profile=profile,
        organization=profile.partner_organization,
        batch=batch,
        can_submit=can_submit_partner_batches(profile),
    )


@partner_bp.route("/batches/<int:batch_id>/submit", methods=["POST"])
@login_required
@require_partner_user
@require_partner_role(*SUBMITTER_ROLES)
def submit_batch(batch_id):
    profile = get_current_partner_profile()
    batch = get_partner_batch_or_404(batch_id, profile)

    if batch.status != "draft":
        flash("Only draft batches can be submitted.", "error")
        return redirect(url_for("partner.batch_detail", batch_id=batch.id))

    before_values = batch_snapshot(batch)
    batch.status = "submitted"
    batch.submitted_at = datetime.utcnow()
    batch.submitted_by_user_id = current_user.id
    for record_change in batch.record_changes:
        record_change.status = "submitted"
    db.session.flush()
    after_values = batch_snapshot(batch)
    add_audit_log(
        "partner_batch_submitted",
        "partner_update_batch",
        batch.id,
        before_values=before_values,
        after_values=after_values,
        organization_id=profile.partner_organization_id,
    )
    db.session.commit()

    flash("Batch submitted for review.", "success")
    return redirect(url_for("partner.batch_detail", batch_id=batch.id))
