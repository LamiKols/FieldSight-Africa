"""Safe intelligence insight generation and review helpers."""

from datetime import datetime

from models import (
    AuditLog,
    INTELLIGENCE_INSIGHT_PUBLISHING_CANDIDATE_STATUSES,
    INTELLIGENCE_INSIGHT_STATUSES,
    IntelligenceInsight,
    db,
    get_active_actor_consent,
)


ELIGIBLE_AUTOMATION_OUTCOME_STATUSES = {"completed", "needs_review"}
SAFE_TEXT_LIMIT = 2000
SAFE_TITLE_LIMIT = 255


def clean_safe_text(value, limit=SAFE_TEXT_LIMIT):
    cleaned = (value or "").strip()
    if len(cleaned) > limit:
        return cleaned[:limit].rstrip()
    return cleaned


def safe_code(value, limit=120):
    cleaned = "".join(
        character
        for character in str(value or "").strip().lower().replace(" ", "_")
        if character.isalnum() or character in {"_", "-"}
    )
    return cleaned[:limit]


def safe_code_list(values, limit=30):
    safe_values = []
    for value in values or []:
        cleaned = safe_code(value)
        if cleaned and cleaned not in safe_values:
            safe_values.append(cleaned)
        if len(safe_values) >= limit:
            break
    return safe_values


def consent_allows_insight_generation(document):
    actor = document.market_actor if document else None
    consent = get_active_actor_consent(actor)
    if not consent:
        return False
    scopes = consent.consent_scope_json or []
    channels = consent.sharing_channels_json or []
    return bool(
        "use_documents_for_extraction_quality" in scopes
        or "admin_review" in channels
        or "internal_review" in channels
    )


def mismatch_field_names(extraction_run):
    field_names = []
    for mismatch in extraction_run.metadata_mismatches_json or []:
        if isinstance(mismatch, dict):
            field_name = safe_code(mismatch.get("field_name"))
            if field_name and field_name not in field_names:
                field_names.append(field_name)
    return field_names


def insight_safe_summary(automation_run):
    document = automation_run.actor_document
    actor = document.market_actor if document else None
    extraction_run = automation_run.extraction_run
    confidence = automation_run.confidence_summary_json or {}
    mismatch_fields = mismatch_field_names(extraction_run) if extraction_run else []
    risk_flags = safe_code_list(extraction_run.risk_flags_json if extraction_run else [])
    return {
        "automation_run_id": automation_run.id,
        "automation_run_status": automation_run.status,
        "actor_document_id": document.id if document else None,
        "actor_public_id": actor.public_id if actor else None,
        "document_type": document.document_type.name if document and document.document_type else "Unknown type",
        "document_review_status": document.review_status if document else None,
        "document_verification_status": document.verification_status if document else None,
        "document_redaction_status": document.redaction_status if document else None,
        "extraction_run_id": extraction_run.id if extraction_run else None,
        "extraction_status": extraction_run.status if extraction_run else None,
        "document_intelligence_status": extraction_run.document_intelligence_status if extraction_run else None,
        "quality_score": extraction_run.quality_score if extraction_run else confidence.get("quality_score"),
        "average_confidence": confidence.get("average_confidence"),
        "field_count": confidence.get("field_count", 0),
        "accepted_count": confidence.get("accepted_count", 0),
        "pending_count": confidence.get("pending_count", 0),
        "rejected_count": confidence.get("rejected_count", 0),
        "manual_override_count": confidence.get("manual_override_count", 0),
        "mismatch_count": len(mismatch_fields),
        "mismatch_fields": mismatch_fields,
        "risk_flag_count": len(risk_flags),
        "risk_flags": risk_flags,
        "internal_review_only": True,
        "auto_published": False,
        "external_access_created": False,
        "file_exposed": False,
        "storage_path_exposed": False,
        "source_filename_exposed": False,
        "raw_extraction_text_exposed": False,
        "restricted_fields_exposed": False,
        "api_secret_exposed": False,
    }


def insight_key_findings(summary):
    findings = []
    if summary.get("average_confidence") is not None:
        findings.append({
            "type": "confidence",
            "label": "Average confidence",
            "value": summary["average_confidence"],
        })
    if summary.get("quality_score") is not None:
        findings.append({
            "type": "quality",
            "label": "Extraction quality score",
            "value": summary["quality_score"],
        })
    if summary.get("mismatch_count"):
        findings.append({
            "type": "metadata_mismatch",
            "label": "Metadata mismatches",
            "value": summary["mismatch_count"],
            "fields": summary.get("mismatch_fields", []),
        })
    if summary.get("risk_flag_count"):
        findings.append({
            "type": "risk_flags",
            "label": "Risk flags",
            "value": summary["risk_flag_count"],
            "codes": summary.get("risk_flags", []),
        })
    if not findings:
        findings.append({
            "type": "clear",
            "label": "No automation risks detected",
            "value": "clear",
        })
    return findings


def governance_flags(summary):
    return [
        {"key": "internal_review_only", "status": "active", "message": "Insight is internal until separately reviewed and approved."},
        {"key": "no_auto_publish", "status": "active", "message": "Generating or approving this insight does not publish data."},
        {"key": "consent_gate", "status": "required", "message": "Consent remains required for any future external sharing."},
        {"key": "document_review_gate", "status": "required", "message": "Document review and verification gates remain authoritative."},
        {"key": "redaction_gate", "status": "required", "message": "Redaction controls remain authoritative."},
        {"key": "publish_readiness_gate", "status": "required", "message": "Publish-readiness controls remain authoritative."},
        {"key": "entitlement_gate", "status": "required", "message": "Entitlements remain required for subscriber, API, or buyer access."},
        {
            "key": "automation_risk",
            "status": "attention" if summary.get("risk_flag_count") or summary.get("mismatch_count") else "clear",
            "message": "Automation output requires review." if summary.get("risk_flag_count") or summary.get("mismatch_count") else "No automation risk flags were summarized.",
        },
    ]


def initial_candidate_status(automation_run, summary):
    document = automation_run.actor_document
    if automation_run.status != "completed":
        return "blocked"
    if summary.get("mismatch_count") or summary.get("risk_flag_count"):
        return "blocked"
    average_confidence = summary.get("average_confidence")
    if average_confidence is not None and average_confidence < 70:
        return "blocked"
    if not document or document.review_status != "approved" or document.verification_status != "verified":
        return "not_candidate"
    return "candidate_pending_review"


def insight_title(automation_run, summary):
    return clean_safe_text(
        f"Document intelligence insight for run #{automation_run.id} ({summary.get('document_type') or 'Unknown type'})",
        limit=SAFE_TITLE_LIMIT,
    )


def insight_summary_text(summary):
    mismatch_count = summary.get("mismatch_count", 0)
    risk_flag_count = summary.get("risk_flag_count", 0)
    confidence = summary.get("average_confidence")
    quality = summary.get("quality_score")
    return clean_safe_text(
        "Internal document intelligence summary generated from automation outcome "
        f"#{summary.get('automation_run_id')}. "
        f"Confidence: {confidence if confidence is not None else 'n/a'}; "
        f"quality: {quality if quality is not None else 'n/a'}; "
        f"mismatches: {mismatch_count}; risk flags: {risk_flag_count}. "
        "This insight is not externally published and does not grant subscriber, API, or buyer access."
    )


def insight_snapshot(insight):
    return {
        "id": insight.id,
        "automation_run_id": insight.automation_run_id,
        "actor_document_id": insight.actor_document_id,
        "extraction_run_id": insight.extraction_run_id,
        "insight_type": insight.insight_type,
        "status": insight.status,
        "title": insight.title,
        "publishing_candidate_status": insight.publishing_candidate_status,
        "safe_summary": insight.safe_summary_json or {},
        "generated_by_user_id": insight.generated_by_user_id,
        "reviewed_by_user_id": insight.reviewed_by_user_id,
        "reviewed_at": insight.reviewed_at.isoformat() if insight.reviewed_at else None,
        "archived_at": insight.archived_at.isoformat() if insight.archived_at else None,
        "file_exposed": False,
        "storage_path_exposed": False,
        "source_filename_exposed": False,
        "raw_extraction_text_exposed": False,
        "restricted_fields_exposed": False,
        "api_secret_exposed": False,
        "auto_published": False,
        "external_access_created": False,
    }


def add_insight_audit(insight, action, actor_user_id=None, before_values=None, after_values=None):
    document = insight.actor_document
    db.session.add(AuditLog(
        user_id=actor_user_id,
        organization_type="partner_organization",
        organization_id=document.partner_organization_id if document else None,
        action=action,
        entity_type="intelligence_insight",
        entity_id=insight.id,
        before_values=before_values,
        after_values=after_values,
    ))


def append_generation_event(automation_run, insight):
    events = list(automation_run.event_log_json or [])
    events.append({
        "event_type": "intelligence_insight_generated",
        "message": "Structured internal intelligence insight generated for admin review.",
        "metadata": {
            "intelligence_insight_id": insight.id,
            "auto_published": False,
            "external_access_created": False,
        },
        "recorded_at": datetime.utcnow().isoformat(),
    })
    automation_run.event_log_json = events


def active_insight_for_run(automation_run):
    return (
        IntelligenceInsight.query
        .filter_by(automation_run_id=automation_run.id)
        .filter(IntelligenceInsight.status != "archived")
        .order_by(IntelligenceInsight.created_at.desc(), IntelligenceInsight.id.desc())
        .first()
    )


def generation_eligibility(automation_run):
    if not automation_run:
        return False, "Automation run is unavailable."
    if automation_run.status not in ELIGIBLE_AUTOMATION_OUTCOME_STATUSES:
        return False, "Only completed or needs-review automation outcomes can generate insights."
    if not automation_run.actor_document:
        return False, "Automation run is not linked to a document."
    if not automation_run.extraction_run:
        return False, "Automation run has no extraction outcome to summarize."
    if not consent_allows_insight_generation(automation_run.actor_document):
        return False, "Active actor consent must permit internal review or extraction-quality use."
    return True, "Automation outcome is eligible for internal insight generation."


def generate_intelligence_insight(automation_run, actor_user_id=None):
    eligible, message = generation_eligibility(automation_run)
    if not eligible:
        return None, {"created": False, "eligible": False, "message": message}

    existing = active_insight_for_run(automation_run)
    if existing:
        return existing, {"created": False, "eligible": True, "message": "An active insight already exists for this run."}

    summary = insight_safe_summary(automation_run)
    insight = IntelligenceInsight(
        automation_run_id=automation_run.id,
        actor_document_id=automation_run.actor_document_id,
        extraction_run_id=automation_run.extraction_run_id,
        insight_type="document_intelligence_summary",
        status="generated",
        title=insight_title(automation_run, summary),
        summary=insight_summary_text(summary),
        safe_summary_json=summary,
        key_findings_json=insight_key_findings(summary),
        governance_flags_json=governance_flags(summary),
        publishing_candidate_status=initial_candidate_status(automation_run, summary),
        generated_by_user_id=actor_user_id,
        generated_at=datetime.utcnow(),
    )
    db.session.add(insight)
    db.session.flush()
    append_generation_event(automation_run, insight)
    add_insight_audit(
        insight,
        "intelligence_insight_generated",
        actor_user_id=actor_user_id,
        before_values=None,
        after_values=insight_snapshot(insight),
    )
    return insight, {"created": True, "eligible": True, "message": "Insight generated for admin review."}


def approved_candidate_allowed(insight):
    summary = insight.safe_summary_json or {}
    if insight.status != "approved":
        return False
    if summary.get("automation_run_status") != "completed":
        return False
    if summary.get("mismatch_count") or summary.get("risk_flag_count"):
        return False
    average_confidence = summary.get("average_confidence")
    if average_confidence is not None and average_confidence < 70:
        return False
    document = insight.actor_document
    return bool(document and document.review_status == "approved" and document.verification_status == "verified")


def requested_candidate_status(insight, requested_status):
    requested_status = safe_code(requested_status)
    if requested_status not in INTELLIGENCE_INSIGHT_PUBLISHING_CANDIDATE_STATUSES:
        requested_status = "not_candidate"
    if requested_status == "approved_candidate" and not approved_candidate_allowed(insight):
        return "blocked"
    return requested_status


def update_intelligence_insight_review(
    insight,
    action,
    actor_user_id=None,
    title=None,
    summary=None,
    review_notes=None,
    publishing_candidate_status=None,
):
    action = safe_code(action)
    if action not in {"edit", "approve", "reject", "archive"}:
        return False, "Unsupported insight review action."

    before_values = insight_snapshot(insight)
    if title is not None:
        cleaned_title = clean_safe_text(title, limit=SAFE_TITLE_LIMIT)
        if cleaned_title:
            insight.title = cleaned_title
    if summary is not None:
        cleaned_summary = clean_safe_text(summary)
        if cleaned_summary:
            insight.summary = cleaned_summary
    if review_notes is not None:
        insight.review_notes = clean_safe_text(review_notes)

    insight.reviewed_by_user_id = actor_user_id
    insight.reviewed_at = datetime.utcnow()

    if action == "edit":
        insight.status = "in_review"
        audit_action = "intelligence_insight_updated"
    elif action == "approve":
        insight.status = "approved"
        insight.publishing_candidate_status = requested_candidate_status(
            insight,
            publishing_candidate_status or "not_candidate",
        )
        audit_action = "intelligence_insight_approved"
    elif action == "reject":
        insight.status = "rejected"
        insight.publishing_candidate_status = "blocked"
        audit_action = "intelligence_insight_rejected"
    else:
        insight.status = "archived"
        insight.archived_at = datetime.utcnow()
        insight.publishing_candidate_status = "blocked"
        audit_action = "intelligence_insight_archived"

    if insight.status not in INTELLIGENCE_INSIGHT_STATUSES:
        insight.status = "in_review"
    add_insight_audit(
        insight,
        audit_action,
        actor_user_id=actor_user_id,
        before_values=before_values,
        after_values=insight_snapshot(insight),
    )
    return True, "Insight review decision recorded safely."
