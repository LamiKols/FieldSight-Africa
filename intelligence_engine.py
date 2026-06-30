"""Safe source ingestion and publication helpers for the intelligence engine."""

import json
from datetime import datetime, timedelta

from models import (
    AuditLog,
    INTELLIGENCE_ALERT_STATUSES,
    INTELLIGENCE_CHANGE_EVENT_STATUSES,
    INTELLIGENCE_INGESTION_RUN_STATUSES,
    INTELLIGENCE_PUBLICATION_CANDIDATE_STATUSES,
    INTELLIGENCE_SOURCE_CADENCES,
    INTELLIGENCE_SOURCE_CATEGORIES,
    INTELLIGENCE_SOURCE_STATUSES,
    INTELLIGENCE_SOURCE_TRUST_LEVELS,
    IntelligenceAlert,
    IntelligenceChangeEvent,
    IntelligenceIngestionRun,
    IntelligenceInsight,
    IntelligencePublicationCandidate,
    IntelligenceSource,
    SubscriberIntelligenceDigest,
    db,
)


SAFE_TEXT_LIMIT = 2000
SAFE_TITLE_LIMIT = 255
SAFE_CODE_LIMIT = 120
RUNNABLE_SOURCE_STATUSES = {"active"}
VISIBLE_DIGEST_STATUSES = {"approved", "published"}

UNSAFE_KEY_FRAGMENTS = (
    "secret",
    "password",
    "token",
    "api_key",
    "apikey",
    "key_hash",
    "hash",
    "private_path",
    "storage_path",
    "path",
    "filename",
    "file_name",
    "raw_text",
    "raw_extraction",
    "restricted",
    "contact",
    "email",
    "phone",
)

UNSAFE_VALUE_MARKERS = (
    "secret",
    "password",
    "token",
    "api key",
    "key hash",
    "private",
    "storage path",
    "raw extraction",
    "restricted_document",
    "raw secret",
    "checksum",
    ".csv",
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    "\\",
)


def clean_safe_text(value, limit=SAFE_TEXT_LIMIT):
    cleaned = " ".join(str(value or "").strip().split())
    if len(cleaned) > limit:
        return cleaned[:limit].rstrip()
    return cleaned


def safe_code(value, limit=SAFE_CODE_LIMIT):
    cleaned = "".join(
        character
        for character in str(value or "").strip().lower().replace(" ", "_")
        if character.isalnum() or character in {"_", "-"}
    )
    return cleaned[:limit]


def normalize_choice(value, allowed_values, default):
    cleaned = safe_code(value)
    return cleaned if cleaned in allowed_values else default


def unsafe_key(key):
    normalized = safe_code(key, limit=255)
    return any(fragment in normalized for fragment in UNSAFE_KEY_FRAGMENTS)


def unsafe_value(value):
    if value is None:
        return False
    if isinstance(value, (int, float, bool)):
        return False
    text = str(value).strip().lower()
    if "@" in text:
        return True
    if len(text) > SAFE_TEXT_LIMIT:
        return True
    return any(marker in text for marker in UNSAFE_VALUE_MARKERS)


def sanitize_value(value):
    if isinstance(value, dict):
        return sanitize_safe_config(value)
    if isinstance(value, list):
        sanitized = []
        for item in value[:50]:
            safe_item = sanitize_value(item)
            if safe_item not in (None, "", {}, []):
                sanitized.append(safe_item)
        return sanitized
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if unsafe_value(value):
        return None
    return clean_safe_text(value, limit=500)


def parse_config_text(value):
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    if not isinstance(value, str):
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        parsed = {}
        for line in value.splitlines():
            if ":" not in line:
                continue
            key, line_value = line.split(":", 1)
            parsed[key.strip()] = line_value.strip()
        return parsed


def sanitize_safe_config(value):
    raw_config = parse_config_text(value)
    sanitized = {}
    for key, raw_value in raw_config.items():
        safe_key = safe_code(key)
        if not safe_key or unsafe_key(safe_key):
            continue
        safe_value = sanitize_value(raw_value)
        if safe_value in (None, "", {}, []):
            continue
        sanitized[safe_key] = safe_value
    return sanitized


def sanitize_allowed_fields(value):
    if isinstance(value, str):
        raw_values = [item.strip() for item in value.replace("\n", ",").split(",")]
    else:
        raw_values = value or []
    safe_values = []
    for item in raw_values:
        cleaned = safe_code(item)
        if cleaned and not unsafe_key(cleaned) and cleaned not in safe_values:
            safe_values.append(cleaned)
        if len(safe_values) >= 30:
            break
    return safe_values


def safe_form_text(value, limit=500):
    sanitized = sanitize_value(value)
    if sanitized in (None, "", {}, []):
        return ""
    return clean_safe_text(sanitized, limit=limit)


def source_values_from_form(values, existing_source=None, actor_user_id=None):
    source_code = safe_code(values.get("source_code"))
    if unsafe_key(source_code):
        source_code = ""
    if not source_code and existing_source:
        source_code = existing_source.source_code
    if not source_code:
        source_code = safe_code(safe_form_text(values.get("name"), limit=80)) or f"source_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

    return {
        "source_code": source_code,
        "name": safe_form_text(values.get("name"), limit=180),
        "description": safe_form_text(values.get("description")),
        "category": normalize_choice(values.get("category"), INTELLIGENCE_SOURCE_CATEGORIES, "manual_research"),
        "status": normalize_choice(values.get("status"), INTELLIGENCE_SOURCE_STATUSES, "active"),
        "trust_level": normalize_choice(values.get("trust_level"), INTELLIGENCE_SOURCE_TRUST_LEVELS, "medium"),
        "cadence": normalize_choice(values.get("cadence"), INTELLIGENCE_SOURCE_CADENCES, "manual"),
        "owner_team": safe_form_text(values.get("owner_team"), limit=120),
        "public_reference_url": safe_form_text(values.get("public_reference_url"), limit=255),
        "safe_configuration_json": sanitize_safe_config(values.get("safe_configuration_json")),
        "allowed_summary_fields_json": sanitize_allowed_fields(values.get("allowed_summary_fields_json")),
        "updated_by_user_id": actor_user_id,
    }


def source_snapshot(source):
    return {
        "id": source.id,
        "source_code": source.source_code,
        "name": source.name,
        "category": source.category,
        "status": source.status,
        "trust_level": source.trust_level,
        "cadence": source.cadence,
        "owner_team": source.owner_team,
        "public_reference_url": source.public_reference_url,
        "safe_configuration": source.safe_configuration_json or {},
        "allowed_summary_fields": source.allowed_summary_fields_json or [],
        "last_run_at": source.last_run_at.isoformat() if source.last_run_at else None,
        "external_fetch_performed": False,
        "restricted_system_crawled": False,
        "source_file_exposed": False,
        "private_path_exposed": False,
        "filename_exposed": False,
        "file_hash_exposed": False,
        "contact_fields_exposed": False,
        "raw_extraction_text_exposed": False,
        "api_secret_exposed": False,
        "auto_published": False,
        "external_access_created": False,
    }


def add_engine_audit(action, entity_type, entity_id, actor_user_id=None, before_values=None, after_values=None):
    db.session.add(AuditLog(
        user_id=actor_user_id,
        organization_type="internal_intelligence",
        organization_id=None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_values=before_values,
        after_values=after_values,
    ))


def source_is_runnable(source):
    if not source:
        return False, "Source is unavailable."
    if source.status not in RUNNABLE_SOURCE_STATUSES:
        return False, f"Sources with status {source.status} cannot be run."
    return True, "Source is active and can be run manually."


def create_or_update_source(values, source=None, actor_user_id=None):
    before_values = source_snapshot(source) if source else None
    parsed = source_values_from_form(values, existing_source=source, actor_user_id=actor_user_id)
    if not parsed["name"]:
        return None, {"saved": False, "message": "Source name is required."}

    if source is None:
        source = IntelligenceSource(
            created_by_user_id=actor_user_id,
            **parsed,
        )
        db.session.add(source)
        action = "intelligence_source_created"
    else:
        for key, value in parsed.items():
            setattr(source, key, value)
        if source.status == "archived" and not source.archived_at:
            source.archived_at = datetime.utcnow()
        if source.status != "archived":
            source.archived_at = None
        action = "intelligence_source_updated"

    db.session.flush()
    add_engine_audit(
        action,
        "intelligence_source",
        source.id,
        actor_user_id=actor_user_id,
        before_values=before_values,
        after_values=source_snapshot(source),
    )
    return source, {"saved": True, "message": "Source saved safely."}


def run_safe_summary(source, linked_insight=None):
    summary = {
        "source": source_snapshot(source),
        "linked_intelligence_insight_id": linked_insight.id if linked_insight else None,
        "linked_intelligence_insight_status": linked_insight.status if linked_insight else None,
        "manual_ingestion_only": True,
        "deterministic_processing": True,
        "change_detection_foundation": True,
        "external_fetch_performed": False,
        "restricted_system_crawled": False,
        "raw_files_stored": False,
        "private_path_exposed": False,
        "filename_exposed": False,
        "file_hash_exposed": False,
        "contact_fields_exposed": False,
        "restricted_document_fields_exposed": False,
        "raw_extraction_text_exposed": False,
        "api_secret_exposed": False,
        "key_hash_exposed": False,
        "auto_published": False,
        "subscriber_access_created": False,
        "api_access_created": False,
        "buyer_access_created": False,
        "payment_flow_changed": False,
    }
    return summary


def severity_for_source(source):
    if source.trust_level in {"verified", "high"}:
        return "medium"
    if source.trust_level == "low":
        return "needs_review"
    return "medium"


def change_payload(source, run):
    return {
        "source_code": source.source_code,
        "category": source.category,
        "trust_level": source.trust_level,
        "cadence": source.cadence,
        "ingestion_run_id": run.id,
        "manual_ingestion_only": True,
        "raw_content_exposed": False,
        "restricted_fields_exposed": False,
    }


def create_change_event_for_run(run):
    source = run.source
    change_event = IntelligenceChangeEvent(
        source_id=source.id,
        ingestion_run_id=run.id,
        change_type=f"{source.category}_snapshot",
        severity=severity_for_source(source),
        status="detected",
        title=clean_safe_text(f"{source.name} source snapshot detected", limit=SAFE_TITLE_LIMIT),
        summary=clean_safe_text(
            f"Manual ingestion recorded a safe {source.category.replace('_', ' ')} snapshot for admin review."
        ),
        safe_payload_json=change_payload(source, run),
        detected_at=datetime.utcnow(),
    )
    db.session.add(change_event)
    db.session.flush()
    return change_event


def create_alert_for_change_event(change_event, linked_insight=None):
    alert = IntelligenceAlert(
        source_id=change_event.source_id,
        ingestion_run_id=change_event.ingestion_run_id,
        change_event_id=change_event.id,
        intelligence_insight_id=linked_insight.id if linked_insight else None,
        title=clean_safe_text(f"Review {change_event.title}", limit=SAFE_TITLE_LIMIT),
        summary=clean_safe_text(
            "Internal intelligence alert created from safe change detection. "
            "No external access or publication was created."
        ),
        severity=change_event.severity,
        status="open",
        safe_payload_json={
            **(change_event.safe_payload_json or {}),
            "change_event_id": change_event.id,
            "linked_intelligence_insight_id": linked_insight.id if linked_insight else None,
            "internal_review_only": True,
        },
    )
    change_event.status = "linked_to_alert"
    db.session.add(alert)
    db.session.flush()
    return alert


def resolve_linked_insight(insight_id):
    try:
        parsed_id = int(insight_id)
    except (TypeError, ValueError):
        return None
    insight = db.session.get(IntelligenceInsight, parsed_id)
    if not insight or insight.status == "archived":
        return None
    return insight


def create_manual_ingestion_run(source, actor_user_id=None, linked_insight_id=None):
    allowed, message = source_is_runnable(source)
    if not allowed:
        add_engine_audit(
            "intelligence_ingestion_run_blocked",
            "intelligence_source",
            source.id if source else None,
            actor_user_id=actor_user_id,
            after_values={
                "created": False,
                "reason": message,
                "auto_published": False,
                "external_access_created": False,
            },
        )
        return None, {"created": False, "message": message}

    linked_insight = resolve_linked_insight(linked_insight_id)
    run = IntelligenceIngestionRun(
        source_id=source.id,
        generated_insight_id=linked_insight.id if linked_insight else None,
        run_type="manual",
        trigger_source="admin_manual",
        status="completed",
        safe_summary_json=run_safe_summary(source, linked_insight=linked_insight),
        started_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
        requested_by_user_id=actor_user_id,
    )
    db.session.add(run)
    db.session.flush()

    change_event = create_change_event_for_run(run)
    alert = create_alert_for_change_event(change_event, linked_insight=linked_insight)
    run.detected_change_count = 1
    run.generated_alert_count = 1
    source.last_run_at = run.completed_at
    db.session.flush()

    add_engine_audit(
        "intelligence_ingestion_run_created",
        "intelligence_ingestion_run",
        run.id,
        actor_user_id=actor_user_id,
        after_values={
            **run.safe_summary_json,
            "change_event_id": change_event.id,
            "alert_id": alert.id,
        },
    )
    return run, {"created": True, "message": "Manual ingestion run created safely."}


def ingestion_run_snapshot(run):
    return {
        "id": run.id,
        "source_id": run.source_id,
        "generated_insight_id": run.generated_insight_id,
        "status": run.status,
        "detected_change_count": run.detected_change_count,
        "generated_alert_count": run.generated_alert_count,
        "safe_summary": run.safe_summary_json or {},
        "auto_published": False,
        "external_access_created": False,
    }


def safe_alert_item(alert):
    return {
        "alert": alert,
        "source": alert.source,
        "ingestion_run": alert.ingestion_run,
        "change_event": alert.change_event,
        "insight": alert.intelligence_insight,
        "safe_payload": alert.safe_payload_json or {},
        "publication_candidate_allowed": publication_candidate_allowed(alert)[0],
        "publication_candidate_message": publication_candidate_allowed(alert)[1],
    }


def alert_snapshot(alert):
    return {
        "id": alert.id,
        "source_id": alert.source_id,
        "ingestion_run_id": alert.ingestion_run_id,
        "change_event_id": alert.change_event_id,
        "intelligence_insight_id": alert.intelligence_insight_id,
        "title": alert.title,
        "status": alert.status,
        "severity": alert.severity,
        "safe_payload": alert.safe_payload_json or {},
        "auto_published": False,
        "external_access_created": False,
    }


def update_alert_review(alert, requested_status, review_notes=None, actor_user_id=None):
    requested_status = normalize_choice(requested_status, INTELLIGENCE_ALERT_STATUSES, "in_review")
    before_values = alert_snapshot(alert)
    alert.status = requested_status
    alert.review_notes = clean_safe_text(review_notes)
    alert.reviewed_by_user_id = actor_user_id
    alert.reviewed_at = datetime.utcnow()
    if alert.status == "archived":
        alert.archived_at = datetime.utcnow()
    add_engine_audit(
        f"intelligence_alert_{alert.status}",
        "intelligence_alert",
        alert.id,
        actor_user_id=actor_user_id,
        before_values=before_values,
        after_values=alert_snapshot(alert),
    )
    return True, "Alert review decision recorded safely."


def publication_candidate_allowed(alert):
    if not alert or alert.status != "approved":
        return False, "Alert must be approved before publication candidacy."
    insight = alert.intelligence_insight
    if insight:
        if insight.status != "approved":
            return False, "Linked insight must be approved."
        if insight.publishing_candidate_status != "approved_candidate":
            return False, "Linked insight must be an approved candidate."
    return True, "Alert is eligible for an internal publication candidate."


def candidate_payload_from_alert(alert):
    source = alert.source
    payload = {
        "alert_id": alert.id,
        "source_code": source.source_code if source else None,
        "source_category": source.category if source else None,
        "source_trust_level": source.trust_level if source else None,
        "source_cadence": source.cadence if source else None,
        "ingestion_run_id": alert.ingestion_run_id,
        "change_event_id": alert.change_event_id,
        "linked_intelligence_insight_id": alert.intelligence_insight_id,
        "summary_type": "safe_intelligence_digest",
        "metadata_only": True,
        "approved_intelligence_only": True,
        "document_file_exposed": False,
        "private_path_exposed": False,
        "raw_extraction_text_exposed": False,
        "contact_fields_exposed": False,
        "restricted_fields_exposed": False,
        "api_secret_exposed": False,
        "auto_published": False,
        "external_access_created": False,
    }
    if alert.safe_payload_json:
        payload["safe_alert_payload"] = {
            key: value
            for key, value in alert.safe_payload_json.items()
            if not unsafe_key(key) and not unsafe_value(value)
        }
    return payload


def create_publication_candidate_from_alert(alert, actor_user_id=None):
    allowed, message = publication_candidate_allowed(alert)
    if not allowed:
        add_engine_audit(
            "intelligence_publication_candidate_blocked",
            "intelligence_alert",
            alert.id if alert else None,
            actor_user_id=actor_user_id,
            after_values={"created": False, "reason": message},
        )
        return None, {"created": False, "message": message}

    existing = (
        IntelligencePublicationCandidate.query
        .filter_by(intelligence_alert_id=alert.id)
        .filter(IntelligencePublicationCandidate.status != "archived")
        .order_by(IntelligencePublicationCandidate.created_at.desc(), IntelligencePublicationCandidate.id.desc())
        .first()
    )
    if existing:
        return existing, {"created": False, "message": "An active publication candidate already exists."}

    candidate = IntelligencePublicationCandidate(
        intelligence_alert_id=alert.id,
        intelligence_insight_id=alert.intelligence_insight_id,
        candidate_type="subscriber_digest",
        status="draft",
        title=clean_safe_text(alert.title, limit=SAFE_TITLE_LIMIT),
        summary=clean_safe_text(alert.summary),
        safe_payload_json=candidate_payload_from_alert(alert),
    )
    db.session.add(candidate)
    db.session.flush()
    add_engine_audit(
        "intelligence_publication_candidate_created",
        "intelligence_publication_candidate",
        candidate.id,
        actor_user_id=actor_user_id,
        after_values=publication_candidate_snapshot(candidate),
    )
    return candidate, {"created": True, "message": "Publication candidate created for admin review."}


def publication_candidate_snapshot(candidate):
    return {
        "id": candidate.id,
        "intelligence_alert_id": candidate.intelligence_alert_id,
        "intelligence_insight_id": candidate.intelligence_insight_id,
        "candidate_type": candidate.candidate_type,
        "status": candidate.status,
        "title": candidate.title,
        "safe_payload": candidate.safe_payload_json or {},
        "auto_published": False,
        "external_access_created": False,
    }


def ensure_digest_for_candidate(candidate, actor_user_id=None):
    if candidate.status != "approved":
        return None
    digest = (
        SubscriberIntelligenceDigest.query
        .filter_by(publication_candidate_id=candidate.id)
        .filter(SubscriberIntelligenceDigest.status.in_(list(VISIBLE_DIGEST_STATUSES)))
        .first()
    )
    if digest:
        return digest
    now = datetime.utcnow()
    digest = SubscriberIntelligenceDigest(
        publication_candidate_id=candidate.id,
        title=clean_safe_text(candidate.title, limit=SAFE_TITLE_LIMIT),
        summary=clean_safe_text(candidate.summary),
        status="approved",
        safe_payload_json={
            **(candidate.safe_payload_json or {}),
            "subscriber_digest": True,
            "metadata_only": True,
            "approved_at": now.isoformat(),
        },
        approved_at=now,
        visible_from=now,
        visible_until=now + timedelta(days=90),
        created_by_user_id=actor_user_id,
    )
    db.session.add(digest)
    db.session.flush()
    add_engine_audit(
        "subscriber_intelligence_digest_created",
        "subscriber_intelligence_digest",
        digest.id,
        actor_user_id=actor_user_id,
        after_values=safe_subscriber_digest_payload(digest),
    )
    return digest


def update_publication_candidate(candidate, action, actor_user_id=None, title=None, summary=None, review_notes=None):
    action = safe_code(action)
    if action not in {"edit", "review", "approve", "reject", "archive"}:
        return False, "Unsupported publication candidate action."
    before_values = publication_candidate_snapshot(candidate)
    if title:
        candidate.title = clean_safe_text(title, limit=SAFE_TITLE_LIMIT)
    if summary:
        candidate.summary = clean_safe_text(summary)
    candidate.review_notes = clean_safe_text(review_notes)

    if action == "edit":
        candidate.status = "draft"
        audit_action = "intelligence_publication_candidate_updated"
    elif action == "review":
        candidate.status = "in_review"
        audit_action = "intelligence_publication_candidate_in_review"
    elif action == "approve":
        allowed = True
        if candidate.intelligence_alert:
            allowed, _message = publication_candidate_allowed(candidate.intelligence_alert)
        if not allowed:
            candidate.status = "rejected"
            audit_action = "intelligence_publication_candidate_rejected"
        else:
            candidate.status = "approved"
            candidate.approved_by_user_id = actor_user_id
            candidate.approved_at = datetime.utcnow()
            audit_action = "intelligence_publication_candidate_approved"
    elif action == "reject":
        candidate.status = "rejected"
        audit_action = "intelligence_publication_candidate_rejected"
    else:
        candidate.status = "archived"
        candidate.archived_at = datetime.utcnow()
        audit_action = "intelligence_publication_candidate_archived"

    if candidate.status not in INTELLIGENCE_PUBLICATION_CANDIDATE_STATUSES:
        candidate.status = "draft"
    db.session.flush()
    digest = ensure_digest_for_candidate(candidate, actor_user_id=actor_user_id) if candidate.status == "approved" else None
    after_values = publication_candidate_snapshot(candidate)
    after_values["subscriber_digest_id"] = digest.id if digest else None
    add_engine_audit(
        audit_action,
        "intelligence_publication_candidate",
        candidate.id,
        actor_user_id=actor_user_id,
        before_values=before_values,
        after_values=after_values,
    )
    return True, "Publication candidate decision recorded safely."


def visible_subscriber_digests(now=None):
    now = now or datetime.utcnow()
    return (
        SubscriberIntelligenceDigest.query
        .filter(SubscriberIntelligenceDigest.status.in_(list(VISIBLE_DIGEST_STATUSES)))
        .filter((SubscriberIntelligenceDigest.visible_from.is_(None)) | (SubscriberIntelligenceDigest.visible_from <= now))
        .filter((SubscriberIntelligenceDigest.visible_until.is_(None)) | (SubscriberIntelligenceDigest.visible_until >= now))
        .order_by(SubscriberIntelligenceDigest.approved_at.desc(), SubscriberIntelligenceDigest.id.desc())
        .all()
    )


def safe_subscriber_digest_payload(digest):
    candidate = digest.publication_candidate
    return {
        "id": digest.id,
        "title": digest.title,
        "summary": digest.summary,
        "status": digest.status,
        "approved_at": digest.approved_at.isoformat() if digest.approved_at else None,
        "visible_from": digest.visible_from.isoformat() if digest.visible_from else None,
        "visible_until": digest.visible_until.isoformat() if digest.visible_until else None,
        "candidate_id": candidate.id if candidate else None,
        "candidate_type": candidate.candidate_type if candidate else None,
        "safe_payload": digest.safe_payload_json or {},
        "metadata_only": True,
        "document_file_exposed": False,
        "private_path_exposed": False,
        "raw_extraction_text_exposed": False,
        "contact_fields_exposed": False,
        "restricted_fields_exposed": False,
        "api_secret_exposed": False,
        "external_access_created": False,
    }


def validation_status_lists():
    return {
        "source_statuses": INTELLIGENCE_SOURCE_STATUSES,
        "source_categories": INTELLIGENCE_SOURCE_CATEGORIES,
        "source_trust_levels": INTELLIGENCE_SOURCE_TRUST_LEVELS,
        "source_cadences": INTELLIGENCE_SOURCE_CADENCES,
        "ingestion_run_statuses": INTELLIGENCE_INGESTION_RUN_STATUSES,
        "change_event_statuses": INTELLIGENCE_CHANGE_EVENT_STATUSES,
        "alert_statuses": INTELLIGENCE_ALERT_STATUSES,
        "publication_candidate_statuses": INTELLIGENCE_PUBLICATION_CANDIDATE_STATUSES,
    }
