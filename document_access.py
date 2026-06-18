"""Shared Phase 3.4 document metadata access helpers."""

from datetime import datetime

from models import (
    ActorDocument,
    ApiClient,
    ApiKey,
    ApiUsageEvent,
    DocumentAccessLog,
    DocumentEntitlement,
    DocumentExtractionRun,
    DocumentPublishControl,
    db,
    actor_can_share_documents,
    consent_document_category_for_document_type,
    get_user_entitlements,
)

METADATA_TARGET_BY_CHANNEL = {
    "subscriber_portal": "subscriber_portal_metadata",
    "api": "api_metadata",
    "licensed_data_pack": "licensed_data_pack_metadata",
    "live_intelligence": "live_intelligence_metadata",
}

ACCESS_REQUEST_TARGET_BY_TYPE = {
    "redacted_document": "redacted_document_candidate",
    "full_document_restricted": "full_document_restricted_candidate",
}

HIGH_RISK_FLAGS = {
    "expired_document",
    "metadata_mismatch",
    "missing_reference_number",
    "missing_issuing_body",
    "no_fields_extracted",
}

METADATA_SCOPE_VALUES = {
    "metadata",
    "metadata_only",
    "document_metadata",
    "verified_metadata",
    "all",
}

METADATA_VISIBILITY_VALUES = {
    "metadata_only",
    "redacted_document",
    "full_document",
}


def latest_document_extraction_run(document):
    return (
        DocumentExtractionRun.query.filter_by(actor_document_id=document.id)
        .order_by(DocumentExtractionRun.created_at.desc(), DocumentExtractionRun.id.desc())
        .first()
    )


def document_publish_control(document, target):
    return DocumentPublishControl.query.filter_by(
        actor_document_id=document.id,
        publish_target=target,
    ).first()


def publish_control_allows(document, target):
    control = document_publish_control(document, target)
    if not control:
        return False, "Publish target has not been evaluated.", None
    if control.status not in {"ready", "waived"}:
        return False, f"Publish target is {control.status}.", control
    return True, "Publish target is eligible.", control


def actor_region_code(actor):
    location = actor.location if actor else None
    if location and location.region:
        return location.region.code
    return None


def actor_region_name(actor):
    location = actor.location if actor else None
    if location and location.region:
        return location.region.name
    if location:
        return location.location_text or location.location
    return None


def document_crop_name(document):
    if document.linked_crop:
        return document.linked_crop.name
    actor = document.market_actor
    if actor and actor.crop:
        return actor.crop.name
    if document.linked_commodity and document.linked_commodity.crop:
        return document.linked_commodity.crop.name
    return None


def document_commodity_name(document):
    if document.linked_commodity:
        return document.linked_commodity.name
    actor = document.market_actor
    if actor and actor.commodity:
        return actor.commodity.name
    return None


def actor_scope_allowed(document, entitlements):
    actor = document.market_actor
    region_code = actor_region_code(actor)
    crop_name = document_crop_name(document)

    allowed_regions = entitlements.get("regions") or []
    if allowed_regions:
        if not region_code:
            return False, "Actor region is missing."
        if region_code not in allowed_regions:
            return False, "Actor region is outside the user's entitlement."

    allowed_crops = entitlements.get("crops")
    if allowed_crops:
        if not crop_name:
            return False, "Document crop is missing."
        if crop_name not in allowed_crops:
            return False, "Document crop is outside the user's entitlement."

    return True, "Actor region and crop are in scope."


def active_document_entitlement_allows(user, document, entitlements):
    if not user:
        return False

    now = datetime.utcnow()
    entitlement_rows = DocumentEntitlement.query.filter_by(active=True).filter(
        ((DocumentEntitlement.starts_at.is_(None)) | (DocumentEntitlement.starts_at <= now)),
        ((DocumentEntitlement.ends_at.is_(None)) | (DocumentEntitlement.ends_at >= now)),
    ).all()

    current_source = entitlements.get("source")
    for entitlement in entitlement_rows:
        if entitlement.document_type_id and entitlement.document_type_id != document.document_type_id:
            continue
        if entitlement.access_scope not in METADATA_SCOPE_VALUES:
            continue
        if entitlement.visibility_level not in METADATA_VISIBILITY_VALUES:
            continue
        if entitlement.user_id == user.id:
            return True
        if entitlement.payment_plan_id and entitlements.get("access_type") == "subscription":
            plan = user.get_plan()
            if plan and entitlement.payment_plan_id == plan.id:
                return True
        if entitlement.licensed_pack_id and entitlements.get("access_type") == "license":
            if current_source and entitlement.licensed_pack_id == current_source.licensed_pack_id:
                return True
    return False


def entitlement_allows_metadata(user, document, channel):
    entitlements = get_user_entitlements(user)
    if entitlements.get("access_type") == "free":
        return False, "No active subscription, license, live intelligence access, or document entitlement.", entitlements

    scope_allowed, scope_reason = actor_scope_allowed(document, entitlements)
    if not scope_allowed:
        return False, scope_reason, entitlements

    if active_document_entitlement_allows(user, document, entitlements):
        return True, "Document entitlement allows metadata access.", entitlements

    if entitlements.get("access_type") == "live_intelligence":
        return True, "Live intelligence entitlement allows metadata access.", entitlements
    if entitlements.get("access_type") == "license":
        return True, "Licensed data pack entitlement allows metadata access.", entitlements

    if entitlements.get("access_type") == "subscription":
        datasets = entitlements.get("datasets") or []
        if "actor_activity_status" in datasets:
            return True, "Subscription dataset tier allows actor document metadata.", entitlements
        return False, "Subscription tier does not include actor intelligence datasets.", entitlements

    return False, "No matching entitlement allows metadata access.", entitlements


def redaction_gate_allows(document):
    status = document.redaction_status or "not_redacted"
    if document.document_type and document.document_type.sensitive:
        if status in {"not_required", "completed", "waived"}:
            return True, "Sensitive document redaction gate passed."
        return False, "Sensitive document redaction gate has not passed."
    if status in {"required", "redaction_required", "in_progress", "failed"}:
        return False, "Document redaction status blocks external metadata."
    return True, "Document redaction status allows metadata."


def extraction_gate_allows(document, publish_control):
    extraction_run = latest_document_extraction_run(document)
    if not extraction_run:
        return False, "No extraction run is available.", None
    if extraction_run.status != "completed":
        return False, "Latest extraction run is not completed.", extraction_run
    if extraction_run.document_intelligence_status not in {"extracted", "reconciled"}:
        return False, "Document intelligence status is not extracted or reconciled.", extraction_run

    risk_flags = extraction_run.risk_flags_json or []
    high_risk_flags = [flag for flag in risk_flags if flag in HIGH_RISK_FLAGS]
    if high_risk_flags and (not publish_control or publish_control.status != "waived"):
        return False, f"Unresolved high-risk flags block metadata: {', '.join(high_risk_flags)}.", extraction_run
    return True, "Extraction, reconciliation, and risk gates passed.", extraction_run


def expiry_gate_allows(document, extraction_run=None):
    today = datetime.utcnow().date()
    if document.expires_at and document.expires_at < today:
        return False, "Document expiry date is in the past."
    if document.document_type and document.document_type.requires_expiry_date and not document.expires_at:
        return False, "Document type requires an expiry date."
    if extraction_run and extraction_run.expiry_renewal_json:
        if extraction_run.expiry_renewal_json.get("status") == "expired":
            return False, "Extraction expiry readiness marks this document as expired."
    return True, "Document expiry gate passed."


def document_metadata_access_decision(user, document, channel):
    target = METADATA_TARGET_BY_CHANNEL.get(channel)
    reasons = []
    if not target:
        return False, ["Unsupported metadata channel."], None, None

    publish_allowed, publish_reason, control = publish_control_allows(document, target)
    reasons.append(publish_reason)
    if not publish_allowed:
        return False, reasons, control, None

    document_category = consent_document_category_for_document_type(document.document_type)
    if not actor_can_share_documents(document.market_actor, channel, document_category):
        reasons.append("Actor consent does not allow this document category and channel.")
        return False, reasons, control, None
    reasons.append("Actor consent allows this document category and channel.")

    if document.archived_at:
        reasons.append("Document is archived.")
        return False, reasons, control, None
    if document.document_status != "approved" or document.review_status != "approved":
        reasons.append("Document is not admin approved.")
        return False, reasons, control, None
    if document.verification_status != "verified":
        reasons.append("Document is not verified.")
        return False, reasons, control, None
    reasons.append("Admin approval and verification gates passed.")

    expiry_allowed, expiry_reason = expiry_gate_allows(document)
    reasons.append(expiry_reason)
    if not expiry_allowed:
        return False, reasons, control, None

    redaction_allowed, redaction_reason = redaction_gate_allows(document)
    reasons.append(redaction_reason)
    if not redaction_allowed:
        return False, reasons, control, None

    extraction_allowed, extraction_reason, extraction_run = extraction_gate_allows(document, control)
    reasons.append(extraction_reason)
    if not extraction_allowed:
        return False, reasons, control, extraction_run

    expiry_allowed, expiry_reason = expiry_gate_allows(document, extraction_run=extraction_run)
    if not expiry_allowed:
        reasons.append(expiry_reason)
        return False, reasons, control, extraction_run

    entitlement_allowed, entitlement_reason, _entitlements = entitlement_allows_metadata(user, document, channel)
    reasons.append(entitlement_reason)
    if not entitlement_allowed:
        return False, reasons, control, extraction_run

    return True, reasons, control, extraction_run


def request_target_allows(document, request_type):
    target = ACCESS_REQUEST_TARGET_BY_TYPE.get(request_type)
    if not target:
        return False, "Unsupported request type.", None
    return publish_control_allows(document, target)


def safe_document_metadata_payload(document, channel, publish_control=None):
    document_category = consent_document_category_for_document_type(document.document_type)
    target = METADATA_TARGET_BY_CHANNEL.get(channel)
    control = publish_control or document_publish_control(document, target)
    return {
        "document_id": document.id,
        "actor_public_id": document.market_actor.public_id if document.market_actor else None,
        "actor_type": document.market_actor.actor_type if document.market_actor else None,
        "document_type": document.document_type.name if document.document_type else None,
        "document_type_code": document.document_type.code if document.document_type else None,
        "document_category": document_category,
        "reference_number": document.document_reference_number,
        "issuing_body": document.issuing_body,
        "issued_at": document.issued_at.isoformat() if document.issued_at else None,
        "expires_at": document.expires_at.isoformat() if document.expires_at else None,
        "crop": document_crop_name(document),
        "commodity": document_commodity_name(document),
        "region_code": actor_region_code(document.market_actor),
        "region_name": actor_region_name(document.market_actor),
        "verification_status": document.verification_status,
        "review_status": document.review_status,
        "redaction_status": document.redaction_status,
        "publish_target": target,
        "publish_status": control.status if control else None,
        "metadata_only": True,
    }


def log_document_access_attempt(document, access_type, channel, user=None, api_client=None, subscriber_organization_name=None, ip_address=None, user_agent=None):
    db.session.add(DocumentAccessLog(
        actor_document_id=document.id,
        actor_document_version_id=None,
        user_id=user.id if user else None,
        api_client_id=api_client.id if api_client else None,
        access_type=access_type,
        access_channel=channel,
        subscriber_organization_name=subscriber_organization_name,
        visibility_level="metadata_only",
        ip_address=ip_address,
        user_agent=user_agent,
    ))


def authenticate_api_key(raw_secret):
    if not raw_secret:
        return None, None
    key_prefix = raw_secret[:8]
    api_key = ApiKey.query.filter_by(key_prefix=key_prefix, status="active").first()
    if not api_key:
        return None, None
    if api_key.revoked_at:
        return None, None
    if api_key.expires_at and api_key.expires_at < datetime.utcnow():
        return None, None
    if api_key.key_hash != ApiKey.hash_secret(raw_secret):
        return None, None

    api_client = api_key.api_client
    if not api_client or api_client.status != "active":
        return None, None
    key_scopes = set(api_key.scopes or [])
    client_scopes = set(api_client.scopes or [])
    if "document_metadata:read" not in key_scopes and "document_metadata:read" not in client_scopes:
        return None, None

    api_key.last_used_at = datetime.utcnow()
    return api_client, api_key


def record_api_usage(api_client, api_key, user, endpoint, method, status_code, row_count=0, filters=None, ip_address=None, user_agent=None):
    if not api_client:
        return
    db.session.add(ApiUsageEvent(
        api_client_id=api_client.id,
        api_key_id=api_key.id if api_key else None,
        user_id=user.id if user else None,
        endpoint=endpoint,
        method=method,
        dataset_type="document_metadata",
        filters_json=filters or {},
        row_count=row_count,
        status_code=status_code,
        units=max(row_count, 1),
        ip_address=ip_address,
        user_agent=user_agent,
    ))


def externally_candidate_documents():
    return ActorDocument.query.filter(ActorDocument.archived_at.is_(None)).all()
