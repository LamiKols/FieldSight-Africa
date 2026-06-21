"""Controlled scheduling and operational alerts for document automation."""

from collections import Counter
from datetime import datetime, timedelta

from document_automation import (
    DEFAULT_BATCH_LIMIT,
    DEFAULT_STALE_MINUTES,
    clamp_batch_limit,
    clamp_stale_minutes,
    process_queued_runs,
    recover_stale_runs,
)
from models import (
    AUTOMATION_SCHEDULE_RUN_STATUSES,
    AuditLog,
    AutomationScheduleConfig,
    AutomationScheduledRunLog,
    DocumentAutomationRun,
    db,
)


SCHEDULE_CODE = "document_intelligence"
SCHEDULE_STALE_ACTIONS = {"requeue", "fail"}
SCHEDULE_SAFE_ERROR = "Scheduled automation processing failed safely."


def get_or_create_schedule_config():
    config = AutomationScheduleConfig.query.filter_by(schedule_code=SCHEDULE_CODE).first()
    if config:
        return config
    config = AutomationScheduleConfig(
        schedule_code=SCHEDULE_CODE,
        enabled=False,
        batch_limit=DEFAULT_BATCH_LIMIT,
        stale_run_threshold_minutes=DEFAULT_STALE_MINUTES,
        stale_run_action="requeue",
        processing_frequency_label="manual",
    )
    db.session.add(config)
    db.session.flush()
    return config


def safe_config_snapshot(config):
    return {
        "id": config.id,
        "schedule_code": config.schedule_code,
        "enabled": bool(config.enabled),
        "batch_limit": config.batch_limit,
        "stale_run_threshold_minutes": config.stale_run_threshold_minutes,
        "stale_run_action": config.stale_run_action,
        "processing_frequency_label": config.processing_frequency_label,
        "last_run_at": config.last_run_at.isoformat() if config.last_run_at else None,
        "last_run_status": config.last_run_status,
        "updated_by_user_id": config.updated_by_user_id,
        "auto_published": False,
        "external_access_created": False,
    }


def safe_log_snapshot(run_log):
    return {
        "id": run_log.id,
        "schedule_config_id": run_log.schedule_config_id,
        "trigger_source": run_log.trigger_source,
        "status": run_log.status,
        "queue_count_before": run_log.queue_count_before,
        "stale_runs_handled": run_log.stale_runs_handled,
        "selected_count": run_log.selected_count,
        "processed_count": run_log.processed_count,
        "completed_count": run_log.completed_count,
        "needs_review_count": run_log.needs_review_count,
        "failed_count": run_log.failed_count,
        "skipped_count": run_log.skipped_count,
        "error_code": run_log.error_code,
        "started_at": run_log.started_at.isoformat() if run_log.started_at else None,
        "completed_at": run_log.completed_at.isoformat() if run_log.completed_at else None,
        "auto_published": False,
        "external_access_created": False,
        "private_content_exposed": False,
        "api_secret_exposed": False,
    }


def add_schedule_audit(action, config, actor_user_id=None, run_log=None, before_values=None, after_values=None):
    db.session.add(AuditLog(
        user_id=actor_user_id,
        organization_type="automation_schedule",
        organization_id=config.id,
        action=action,
        entity_type="automation_scheduled_run_log" if run_log else "automation_schedule_config",
        entity_id=run_log.id if run_log else config.id,
        before_values=before_values,
        after_values=after_values,
    ))


def update_schedule_config(
    config,
    *,
    enabled,
    batch_limit,
    stale_run_threshold_minutes,
    stale_run_action,
    processing_frequency_label,
    notes,
    actor_user_id=None,
):
    before_values = safe_config_snapshot(config)
    config.enabled = bool(enabled)
    config.batch_limit = clamp_batch_limit(batch_limit)
    config.stale_run_threshold_minutes = clamp_stale_minutes(stale_run_threshold_minutes)
    config.stale_run_action = stale_run_action if stale_run_action in SCHEDULE_STALE_ACTIONS else "requeue"
    config.processing_frequency_label = (processing_frequency_label or "manual").strip()[:120]
    config.notes = (notes or "").strip()[:2000] or None
    config.updated_by_user_id = actor_user_id
    db.session.flush()
    add_schedule_audit(
        "admin_automation_schedule_updated",
        config,
        actor_user_id=actor_user_id,
        before_values=before_values,
        after_values=safe_config_snapshot(config),
    )
    db.session.commit()
    return config


def create_scheduled_run_log(config, trigger_source, actor_user_id=None):
    run_log = AutomationScheduledRunLog(
        schedule_config_id=config.id,
        trigger_source=(trigger_source or "scheduler_script")[:80],
        status="running",
        requested_by_user_id=actor_user_id,
        started_at=datetime.utcnow(),
        queue_count_before=DocumentAutomationRun.query.filter_by(status="queued").count(),
        safe_summary_json={
            "auto_published": False,
            "external_access_created": False,
            "private_content_exposed": False,
            "api_secret_exposed": False,
        },
    )
    db.session.add(run_log)
    db.session.flush()
    add_schedule_audit(
        "automation_scheduled_run_started",
        config,
        actor_user_id=actor_user_id,
        run_log=run_log,
        before_values=None,
        after_values=safe_log_snapshot(run_log),
    )
    db.session.commit()
    return run_log


def finalize_disabled_schedule(config, run_log, actor_user_id=None):
    run_log.status = "skipped_disabled"
    run_log.completed_at = datetime.utcnow()
    run_log.safe_summary_json = {
        "reason": "schedule_disabled",
        "auto_published": False,
        "external_access_created": False,
        "private_content_exposed": False,
        "api_secret_exposed": False,
    }
    config.last_run_at = run_log.completed_at
    config.last_run_status = run_log.status
    add_schedule_audit(
        "automation_scheduled_run_skipped_disabled",
        config,
        actor_user_id=actor_user_id,
        run_log=run_log,
        before_values=None,
        after_values=safe_log_snapshot(run_log),
    )
    db.session.commit()
    return {
        "run_log": safe_log_snapshot(run_log),
        "schedule_enabled": False,
        "processed": False,
        "status": run_log.status,
    }


def execute_scheduled_processing(trigger_source="scheduler_script", actor_user_id=None):
    config = get_or_create_schedule_config()
    db.session.commit()
    run_log = create_scheduled_run_log(config, trigger_source, actor_user_id=actor_user_id)
    if not config.enabled:
        return finalize_disabled_schedule(config, run_log, actor_user_id=actor_user_id)

    try:
        stale_summary = recover_stale_runs(
            stale_minutes=config.stale_run_threshold_minutes,
            action=config.stale_run_action,
            actor_user_id=actor_user_id,
        )
        processing_summary = process_queued_runs(
            limit=config.batch_limit,
            actor_user_id=actor_user_id,
        )
        run_log = db.session.get(AutomationScheduledRunLog, run_log.id)
        config = db.session.get(AutomationScheduleConfig, config.id)
        run_log.stale_runs_handled = stale_summary["total"]
        run_log.selected_count = processing_summary["selected"]
        run_log.processed_count = processing_summary["processed"]
        run_log.completed_count = processing_summary["completed"]
        run_log.needs_review_count = processing_summary["needs_review"]
        run_log.failed_count = processing_summary["failed"]
        run_log.skipped_count = processing_summary["skipped"]
        run_log.status = (
            "completed_with_attention"
            if run_log.failed_count or run_log.needs_review_count or stale_summary["failed"]
            else "completed"
        )
        if run_log.status not in AUTOMATION_SCHEDULE_RUN_STATUSES:
            run_log.status = "failed"
        run_log.completed_at = datetime.utcnow()
        run_log.error_code = None
        run_log.safe_summary_json = {
            "stale_total": stale_summary["total"],
            "stale_requeued": stale_summary["requeued"],
            "stale_failed": stale_summary["failed"],
            "selected": processing_summary["selected"],
            "processed": processing_summary["processed"],
            "completed": processing_summary["completed"],
            "needs_review": processing_summary["needs_review"],
            "failed": processing_summary["failed"],
            "skipped": processing_summary["skipped"],
            "auto_published": False,
            "external_access_created": False,
            "private_content_exposed": False,
            "api_secret_exposed": False,
        }
        config.last_run_at = run_log.completed_at
        config.last_run_status = run_log.status
        add_schedule_audit(
            "automation_scheduled_run_completed",
            config,
            actor_user_id=actor_user_id,
            run_log=run_log,
            before_values=None,
            after_values=safe_log_snapshot(run_log),
        )
        db.session.commit()
        return {
            "run_log": safe_log_snapshot(run_log),
            "schedule_enabled": True,
            "processed": True,
            "status": run_log.status,
        }
    except Exception:
        db.session.rollback()
        run_log = db.session.get(AutomationScheduledRunLog, run_log.id)
        config = db.session.get(AutomationScheduleConfig, config.id)
        run_log.status = "failed"
        run_log.completed_at = datetime.utcnow()
        run_log.error_code = "scheduled_processing_error"
        run_log.safe_summary_json = {
            "error": SCHEDULE_SAFE_ERROR,
            "auto_published": False,
            "external_access_created": False,
            "private_content_exposed": False,
            "api_secret_exposed": False,
        }
        config.last_run_at = run_log.completed_at
        config.last_run_status = run_log.status
        add_schedule_audit(
            "automation_scheduled_run_failed",
            config,
            actor_user_id=actor_user_id,
            run_log=run_log,
            before_values=None,
            after_values=safe_log_snapshot(run_log),
        )
        db.session.commit()
        return {
            "run_log": safe_log_snapshot(run_log),
            "schedule_enabled": True,
            "processed": False,
            "status": run_log.status,
            "error_code": run_log.error_code,
        }


def repeated_failure_summary():
    counter = Counter(
        run.actor_document_id
        for run in DocumentAutomationRun.query.filter_by(status="failed").all()
    )
    items = [
        {"document_id": document_id, "failure_count": count}
        for document_id, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
        if count >= 2
    ]
    return items


def operational_monitoring_summary(config=None):
    config = config or get_or_create_schedule_config()
    now = datetime.utcnow()
    stale_cutoff = now - timedelta(minutes=config.stale_run_threshold_minutes)
    running_runs = DocumentAutomationRun.query.filter_by(status="running").all()
    stale_runs = [
        run for run in running_runs
        if (run.started_at or run.updated_at or run.created_at) <= stale_cutoff
    ]
    repeated_failures = repeated_failure_summary()
    queued_count = DocumentAutomationRun.query.filter_by(status="queued").count()
    failed_count = DocumentAutomationRun.query.filter_by(status="failed").count()
    needs_review_count = DocumentAutomationRun.query.filter_by(status="needs_review").count()
    completed_24h = DocumentAutomationRun.query.filter(
        DocumentAutomationRun.status == "completed",
        DocumentAutomationRun.completed_at >= now - timedelta(hours=24),
    ).count()
    failed_24h = DocumentAutomationRun.query.filter(
        DocumentAutomationRun.status == "failed",
        DocumentAutomationRun.completed_at >= now - timedelta(hours=24),
    ).count()
    backlog_active = queued_count > config.batch_limit
    alerts = [
        {
            "code": "failed_runs",
            "label": "Failed Runs",
            "count": failed_count,
            "active": failed_count > 0,
            "severity": "critical" if failed_count else "clear",
            "message": "Failed automation runs require admin review." if failed_count else "No failed automation runs.",
        },
        {
            "code": "stale_running",
            "label": "Stale Running",
            "count": len(stale_runs),
            "active": bool(stale_runs),
            "severity": "critical" if stale_runs else "clear",
            "message": "Running jobs exceed the configured stale threshold." if stale_runs else "No stale running jobs.",
        },
        {
            "code": "needs_review",
            "label": "Needs Review",
            "count": needs_review_count,
            "active": needs_review_count > 0,
            "severity": "warning" if needs_review_count else "clear",
            "message": "Automation outcomes are waiting for human review." if needs_review_count else "No automation outcomes are waiting for review.",
        },
        {
            "code": "repeated_failures",
            "label": "Repeated Failures",
            "count": len(repeated_failures),
            "active": bool(repeated_failures),
            "severity": "critical" if repeated_failures else "clear",
            "message": "Documents have failed automation processing more than once." if repeated_failures else "No repeated document failures.",
        },
        {
            "code": "queue_backlog",
            "label": "Queue Backlog",
            "count": queued_count,
            "active": backlog_active,
            "severity": "warning" if backlog_active else "clear",
            "message": "Queued jobs exceed the configured batch limit." if backlog_active else "Queue is within the configured batch limit.",
        },
    ]
    recent_logs = (
        AutomationScheduledRunLog.query
        .order_by(AutomationScheduledRunLog.started_at.desc(), AutomationScheduledRunLog.id.desc())
        .limit(12)
        .all()
    )
    return {
        "metrics": {
            "queued_count": queued_count,
            "running_count": len(running_runs),
            "completed_24h": completed_24h,
            "failed_24h": failed_24h,
            "stale_running_count": len(stale_runs),
            "needs_review_count": needs_review_count,
            "repeated_failure_document_count": len(repeated_failures),
            "backlog_active": backlog_active,
        },
        "alerts": alerts,
        "repeated_failures": repeated_failures,
        "recent_logs": recent_logs,
    }
