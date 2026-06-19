"""Deterministic processing for queued document automation runs."""

from collections import Counter
from datetime import datetime, timedelta

from models import (
    AuditLog,
    DOCUMENT_EXTRACTION_STATUSES,
    DOCUMENT_INTELLIGENCE_STATUSES,
    DocumentAutomationRun,
    DocumentExtractionRun,
    DocumentFieldReconciliation,
    db,
    get_active_actor_consent,
)
from routes.partner import (
    create_reconciliation_rows,
    document_extraction_payload,
    document_version_file_metadata,
    resolve_document_storage_path,
)


DEFAULT_BATCH_LIMIT = 10
MAX_BATCH_LIMIT = 100
DEFAULT_STALE_MINUTES = 30

SAFE_FAILURE_MESSAGES = {
    "missing_document": "The document linked to this automation run is unavailable.",
    "missing_version": "The document version linked to this automation run is unavailable.",
    "missing_file": "The private document file is unavailable for processing.",
    "invalid_file_reference": "The private document file reference could not be resolved safely.",
    "consent_blocked": "Active actor consent does not currently permit internal document intelligence processing.",
    "document_blocked": "The document is not currently eligible for automation processing.",
    "processing_error": "Automation processing failed safely. Review the run and retry when appropriate.",
    "stale_timeout": "Automation processing exceeded the configured running time limit.",
}


class AutomationProcessingError(Exception):
    def __init__(self, code, terminal_status="failed"):
        super().__init__(code)
        self.code = code
        self.terminal_status = terminal_status


def clamp_batch_limit(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = DEFAULT_BATCH_LIMIT
    return max(1, min(parsed, MAX_BATCH_LIMIT))


def clamp_stale_minutes(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = DEFAULT_STALE_MINUTES
    return max(1, min(parsed, 1440))


def safe_run_snapshot(automation_run):
    return {
        "automation_run_id": automation_run.id,
        "actor_document_id": automation_run.actor_document_id,
        "actor_document_version_id": automation_run.actor_document_version_id,
        "extraction_run_id": automation_run.extraction_run_id,
        "retry_of_run_id": automation_run.retry_of_run_id,
        "status": automation_run.status,
        "job_type": automation_run.job_type,
        "trigger_source": automation_run.trigger_source,
        "confidence_summary": automation_run.confidence_summary_json or {},
        "file_exposed": False,
        "storage_path_exposed": False,
        "source_filename_exposed": False,
        "raw_extraction_text_exposed": False,
        "restricted_fields_exposed": False,
        "api_secret_exposed": False,
        "auto_published": False,
        "external_access_created": False,
    }


def append_safe_event(automation_run, event_type, message, metadata=None):
    events = list(automation_run.event_log_json or [])
    events.append({
        "event_type": event_type,
        "message": message,
        "metadata": metadata or {},
        "recorded_at": datetime.utcnow().isoformat(),
    })
    automation_run.event_log_json = events


def add_processing_audit(automation_run, action, actor_user_id=None, before_values=None, after_values=None):
    document = automation_run.actor_document
    db.session.add(AuditLog(
        user_id=actor_user_id,
        organization_type="partner_organization",
        organization_id=document.partner_organization_id if document else None,
        action=action,
        entity_type="document_automation_run",
        entity_id=automation_run.id,
        before_values=before_values,
        after_values=after_values,
    ))


def confidence_values(extraction_run, reconciliation_rows):
    values = []
    if extraction_run and isinstance(extraction_run.confidence_json, dict):
        values.extend(
            float(value)
            for value in extraction_run.confidence_json.values()
            if isinstance(value, (int, float))
        )
    values.extend(
        float(row.confidence)
        for row in reconciliation_rows
        if isinstance(row.confidence, (int, float))
    )
    return values


def confidence_percent(value):
    if value is None:
        return None
    if value <= 1:
        return round(value * 100, 1)
    return round(value, 1)


def build_confidence_summary(document, extraction_run=None):
    if extraction_run is None:
        extraction_run = (
            DocumentExtractionRun.query.filter_by(actor_document_id=document.id)
            .order_by(DocumentExtractionRun.created_at.desc(), DocumentExtractionRun.id.desc())
            .first()
        )
    reconciliation_rows = []
    if extraction_run:
        reconciliation_rows = (
            DocumentFieldReconciliation.query.filter_by(extraction_run_id=extraction_run.id)
            .order_by(DocumentFieldReconciliation.id)
            .all()
        )
    values = confidence_values(extraction_run, reconciliation_rows)
    average_confidence = (sum(values) / len(values)) if values else None
    statuses = Counter(row.status or "unknown" for row in reconciliation_rows)
    mismatches = extraction_run.metadata_mismatches_json if extraction_run and extraction_run.metadata_mismatches_json else []
    risk_flags = extraction_run.risk_flags_json if extraction_run and extraction_run.risk_flags_json else []
    return {
        "latest_extraction_run_id": extraction_run.id if extraction_run else None,
        "latest_extraction_status": extraction_run.status if extraction_run else "missing",
        "document_intelligence_status": extraction_run.document_intelligence_status if extraction_run else "not_started",
        "quality_score": extraction_run.quality_score if extraction_run else None,
        "average_confidence": confidence_percent(average_confidence),
        "field_count": len(reconciliation_rows),
        "accepted_count": statuses.get("accepted", 0),
        "rejected_count": statuses.get("rejected", 0),
        "pending_count": statuses.get("pending", 0),
        "manual_override_count": statuses.get("manually_overridden", 0),
        "mismatch_count": len(mismatches),
        "risk_flag_count": len(risk_flags),
        "low_confidence_count": len([value for value in values if value < 0.6]),
    }


def consent_allows_processing(document):
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


def validate_processing_run(automation_run):
    document = automation_run.actor_document
    if not document:
        raise AutomationProcessingError("missing_document")
    if document.archived_at or document.document_status in {"archived", "rejected"} or document.review_status == "rejected":
        raise AutomationProcessingError("document_blocked", terminal_status="needs_review")
    if not consent_allows_processing(document):
        raise AutomationProcessingError("consent_blocked", terminal_status="needs_review")
    version = automation_run.actor_document_version
    if not version:
        raise AutomationProcessingError("missing_version")
    return document, version


def create_automation_extraction_run(automation_run, document, version, file_path, actor_user_id=None):
    payload = document_extraction_payload(document, version, file_path)
    if payload["status"] not in DOCUMENT_EXTRACTION_STATUSES:
        payload["status"] = "needs_review"
    if payload["document_intelligence_status"] not in DOCUMENT_INTELLIGENCE_STATUSES:
        payload["document_intelligence_status"] = "needs_reconciliation"

    extraction_run = DocumentExtractionRun(
        actor_document_id=document.id,
        actor_document_version_id=version.id,
        status=payload["status"],
        extractor_type="automation_template",
        document_type_code=document.document_type.code if document.document_type else None,
        template_profile_code=payload["template_profile_code"],
        source_filename=None,
        extracted_fields_json=payload["extracted_fields"],
        confidence_json=payload["confidence_json"],
        field_evidence_json=payload["evidence"],
        provenance_json=payload["provenance"],
        metadata_mismatches_json=payload["mismatches"],
        risk_flags_json=payload["risk_flags"],
        expiry_renewal_json=payload["expiry_renewal"],
        quality_score=payload["quality_score"],
        document_intelligence_status=payload["document_intelligence_status"],
        raw_text_excerpt=None,
        created_by_user_id=actor_user_id or automation_run.requested_by_user_id,
    )
    db.session.add(extraction_run)
    db.session.flush()
    create_reconciliation_rows(document, extraction_run, payload)
    db.session.flush()
    return extraction_run, payload


def finalize_processing_error(run_id, code, terminal_status="failed", actor_user_id=None):
    db.session.rollback()
    automation_run = db.session.get(DocumentAutomationRun, run_id)
    if not automation_run:
        return {"run_id": run_id, "processed": False, "status": "missing", "error_code": "missing_run"}
    before_values = safe_run_snapshot(automation_run)
    automation_run.status = terminal_status
    automation_run.completed_at = datetime.utcnow()
    automation_run.error_message = SAFE_FAILURE_MESSAGES.get(code, SAFE_FAILURE_MESSAGES["processing_error"])
    append_safe_event(
        automation_run,
        "automation_run_needs_review" if terminal_status == "needs_review" else "automation_run_failed",
        automation_run.error_message,
        {
            "error_code": code,
            "terminal_status": terminal_status,
            "auto_published": False,
            "external_access_created": False,
        },
    )
    add_processing_audit(
        automation_run,
        "document_automation_run_needs_review" if terminal_status == "needs_review" else "document_automation_run_failed",
        actor_user_id=actor_user_id,
        before_values=before_values,
        after_values=safe_run_snapshot(automation_run),
    )
    db.session.commit()
    return {
        "run_id": automation_run.id,
        "processed": True,
        "status": automation_run.status,
        "error_code": code,
    }


def process_automation_run(run_id, actor_user_id=None):
    automation_run = db.session.get(DocumentAutomationRun, run_id)
    if not automation_run:
        return {"run_id": run_id, "processed": False, "status": "missing", "error_code": "missing_run"}
    if automation_run.status != "queued":
        return {"run_id": run_id, "processed": False, "status": automation_run.status, "error_code": "not_queued"}

    before_values = safe_run_snapshot(automation_run)
    automation_run.status = "running"
    automation_run.started_at = datetime.utcnow()
    automation_run.completed_at = None
    automation_run.error_message = None
    append_safe_event(
        automation_run,
        "automation_run_started",
        "Deterministic internal document intelligence processing started.",
        {"auto_published": False, "external_access_created": False},
    )
    add_processing_audit(
        automation_run,
        "document_automation_run_started",
        actor_user_id=actor_user_id,
        before_values=before_values,
        after_values=safe_run_snapshot(automation_run),
    )
    db.session.commit()

    try:
        automation_run = db.session.get(DocumentAutomationRun, run_id)
        if automation_run.status != "running":
            return {"run_id": run_id, "processed": False, "status": automation_run.status, "error_code": "status_changed"}
        document, version = validate_processing_run(automation_run)
        storage_path, _download_name, _mime_type, _extension = document_version_file_metadata(document, version=version)
        if not storage_path:
            raise AutomationProcessingError("missing_file")
        try:
            file_path = resolve_document_storage_path(storage_path)
        except Exception as exc:
            raise AutomationProcessingError("invalid_file_reference") from exc
        if not file_path.exists() or not file_path.is_file():
            raise AutomationProcessingError("missing_file")

        extraction_run, payload = create_automation_extraction_run(
            automation_run,
            document,
            version,
            file_path,
            actor_user_id=actor_user_id,
        )
        automation_run.extraction_run_id = extraction_run.id
        automation_run.confidence_summary_json = build_confidence_summary(document, extraction_run=extraction_run)
        automation_run.status = "needs_review" if payload["status"] == "needs_review" else "completed"
        automation_run.completed_at = datetime.utcnow()
        automation_run.error_message = None
        append_safe_event(
            automation_run,
            "automation_run_needs_review" if automation_run.status == "needs_review" else "automation_run_completed",
            "Deterministic processing completed and requires human review." if automation_run.status == "needs_review" else "Deterministic processing completed successfully.",
            {
                "extraction_run_id": extraction_run.id,
                "quality_score": extraction_run.quality_score,
                "mismatch_count": len(payload["mismatches"]),
                "risk_flag_count": len(payload["risk_flags"]),
                "auto_published": False,
                "external_access_created": False,
            },
        )
        add_processing_audit(
            automation_run,
            "document_automation_run_needs_review" if automation_run.status == "needs_review" else "document_automation_run_completed",
            actor_user_id=actor_user_id,
            before_values=before_values,
            after_values=safe_run_snapshot(automation_run),
        )
        db.session.commit()
        return {
            "run_id": automation_run.id,
            "processed": True,
            "status": automation_run.status,
            "extraction_run_id": extraction_run.id,
            "error_code": None,
        }
    except AutomationProcessingError as exc:
        return finalize_processing_error(
            run_id,
            exc.code,
            terminal_status=exc.terminal_status,
            actor_user_id=actor_user_id,
        )
    except Exception:
        return finalize_processing_error(
            run_id,
            "processing_error",
            terminal_status="failed",
            actor_user_id=actor_user_id,
        )


def recover_stale_runs(stale_minutes=DEFAULT_STALE_MINUTES, action="requeue", actor_user_id=None):
    stale_minutes = clamp_stale_minutes(stale_minutes)
    if action not in {"requeue", "fail"}:
        action = "requeue"
    cutoff = datetime.utcnow() - timedelta(minutes=stale_minutes)
    running_runs = DocumentAutomationRun.query.filter_by(status="running").all()
    stale_runs = [
        run for run in running_runs
        if (run.started_at or run.updated_at or run.created_at) <= cutoff
    ]
    summary = {"total": len(stale_runs), "requeued": 0, "failed": 0, "run_ids": []}
    for automation_run in stale_runs:
        before_values = safe_run_snapshot(automation_run)
        summary["run_ids"].append(automation_run.id)
        if action == "fail":
            automation_run.status = "failed"
            automation_run.completed_at = datetime.utcnow()
            automation_run.error_message = SAFE_FAILURE_MESSAGES["stale_timeout"]
            summary["failed"] += 1
            event_type = "automation_stale_run_failed"
            audit_action = "document_automation_stale_run_failed"
            message = SAFE_FAILURE_MESSAGES["stale_timeout"]
        else:
            automation_run.status = "queued"
            automation_run.started_at = None
            automation_run.completed_at = None
            automation_run.error_message = None
            summary["requeued"] += 1
            event_type = "automation_stale_run_requeued"
            audit_action = "document_automation_stale_run_requeued"
            message = "Stale running automation was safely returned to the queue."
        append_safe_event(
            automation_run,
            event_type,
            message,
            {
                "stale_minutes": stale_minutes,
                "auto_published": False,
                "external_access_created": False,
            },
        )
        add_processing_audit(
            automation_run,
            audit_action,
            actor_user_id=actor_user_id,
            before_values=before_values,
            after_values=safe_run_snapshot(automation_run),
        )
    db.session.commit()
    return summary


def process_queued_runs(limit=DEFAULT_BATCH_LIMIT, actor_user_id=None):
    limit = clamp_batch_limit(limit)
    run_ids = [
        run.id
        for run in (
            DocumentAutomationRun.query.filter_by(status="queued")
            .order_by(DocumentAutomationRun.queued_at, DocumentAutomationRun.id)
            .limit(limit)
            .all()
        )
    ]
    results = [process_automation_run(run_id, actor_user_id=actor_user_id) for run_id in run_ids]
    counts = Counter(result["status"] for result in results)
    return {
        "requested_limit": limit,
        "selected": len(run_ids),
        "processed": len([result for result in results if result["processed"]]),
        "completed": counts.get("completed", 0),
        "needs_review": counts.get("needs_review", 0),
        "failed": counts.get("failed", 0),
        "cancelled": counts.get("cancelled", 0),
        "skipped": len([result for result in results if not result["processed"]]),
        "run_ids": run_ids,
        "results": results,
    }
