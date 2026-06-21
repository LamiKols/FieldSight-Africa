"""Validate Phase 5.2 scheduled processing and operational alerts."""

import os
import shutil
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

PRIVATE_UPLOAD_ROOT = tempfile.mkdtemp(prefix="fieldsight-phase-5-2-docs-")

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SESSION_SECRET", "phase-5-2-validation-secret")
os.environ["PRIVATE_UPLOAD_ROOT"] = PRIVATE_UPLOAD_ROOT
os.environ.setdefault("DOCUMENT_STORAGE_BACKEND", "local_private")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app import (  # noqa: E402
    app,
    db,
    seed_datasets,
    seed_document_types,
    seed_licensed_packs,
    seed_payment_plans,
    seed_reference_data,
    seed_reference_options,
)
from models import (  # noqa: E402
    ActorConsentRecord,
    ActorDocument,
    ActorDocumentVersion,
    AuditLog,
    AutomationScheduleConfig,
    AutomationScheduledRunLog,
    Crop,
    DocumentAutomationRun,
    DocumentPublishControl,
    DocumentType,
    MarketActor,
    PartnerOrganization,
    User,
)
from scripts.run_scheduled_document_automation import run_scheduled_cycle  # noqa: E402


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


def create_user(name, email, password="validation-password", role="subscriber"):
    user = User(name=name, email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    return user


def login(client, email, password="validation-password"):
    response = client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )
    assert_true(response.status_code in (302, 303), f"Login failed for {email}")


def logout(client):
    client.get("/logout", follow_redirects=False)


def create_document(admin, organization, suffix, *, create_file=True):
    crop = Crop.query.filter_by(name="Ginger").one()
    actor = MarketActor(
        partner_organization_id=organization.id,
        created_by_user_id=admin.id,
        actor_type="exporter",
        name=f"Hidden Scheduled Actor {suffix}",
        crop_id=crop.id,
        status="active",
    )
    db.session.add(actor)
    db.session.flush()

    document_type = DocumentType.query.filter_by(name="Certificate of Origin").one()
    reference = f"SCHEDULE-{suffix.upper()}-001"
    file_path = Path(PRIVATE_UPLOAD_ROOT) / f"private-schedule-{suffix}.csv"
    if create_file:
        file_path.write_text(
            "\n".join([
                f"document_reference_number: {reference}",
                "issuing_body: FieldSight Schedule Authority",
                "issued_at: 2026-01-01",
                "expires_at: 2027-12-31",
                "origin_country: Nigeria",
            ]),
            encoding="utf-8",
        )

    document = ActorDocument(
        market_actor_id=actor.id,
        partner_organization_id=organization.id,
        document_type_id=document_type.id,
        uploaded_by_user_id=admin.id,
        title=f"Hidden Scheduled Document {suffix}",
        description="Unsafe scheduled document description should not render.",
        original_filename=f"unsafe-schedule-original-{suffix}.csv",
        stored_filename=f"unsafe-schedule-stored-{suffix}.csv",
        storage_path=str(file_path),
        mime_type="text/csv",
        file_size=2048,
        file_hash=f"unsafe-schedule-hash-{suffix}",
        version_number=1,
        document_reference_number=reference,
        issuing_body="FieldSight Schedule Authority",
        linked_crop_id=crop.id,
        document_status="approved",
        review_status="approved",
        verification_status="verified",
        redaction_status="completed",
        subscriber_access_level="metadata_only",
        visibility_level="metadata_only",
        issued_at=datetime(2026, 1, 1).date(),
        expires_at=datetime(2027, 12, 31).date(),
    )
    db.session.add(document)
    db.session.flush()

    version = ActorDocumentVersion(
        actor_document_id=document.id,
        version_number=1,
        storage_backend="local_private",
        storage_path=str(file_path),
        original_filename=f"unsafe-schedule-version-{suffix}.csv",
        content_type="text/csv",
        file_size_bytes=2048,
        checksum_sha256=f"unsafe-schedule-version-hash-{suffix}",
        uploaded_by_user_id=admin.id,
        document_status="submitted",
    )
    db.session.add(version)
    db.session.flush()

    db.session.add(ActorConsentRecord(
        market_actor_id=actor.id,
        partner_organization_id=organization.id,
        consent_status="granted",
        consent_method="written",
        consent_reference=f"CONSENT-SCHEDULE-{suffix}",
        consent_scope_json=["store_actor_documents", "use_documents_for_extraction_quality"],
        sharing_channels_json=["internal_review", "admin_review"],
        granted_by_name="Hidden Scheduled Contact",
        granted_by_email="secret-schedule@example.com",
        granted_at=utcnow(),
        expires_at=utcnow() + timedelta(days=365),
        captured_by_user_id=admin.id,
        active=True,
    ))
    control = DocumentPublishControl(
        actor_document_id=document.id,
        publish_target="subscriber_portal_metadata",
        status="blocked",
        readiness_checks_json=[{"key": "validation", "status": "fail"}],
        blocking_reasons_json=["Validation remains blocked."],
        admin_decision="validation",
        last_evaluated_at=utcnow(),
    )
    db.session.add(control)
    db.session.flush()
    return document, version, control


def create_run(document, version, admin, status="queued", *, started_at=None, completed_at=None):
    run = DocumentAutomationRun(
        actor_document_id=document.id,
        actor_document_version_id=version.id,
        job_type="document_intelligence",
        trigger_source="phase_5_2_validation",
        status=status,
        eligibility_checks_json=[{
            "key": "validation",
            "label": "Validation",
            "status": "pass",
            "message": "Safe schedule validation fixture.",
        }],
        confidence_summary_json={"average_confidence": None, "quality_score": None},
        event_log_json=[{
            "event_type": "automation_run_queued",
            "message": "Safe schedule fixture event.",
            "metadata": {"auto_published": False},
            "recorded_at": utcnow().isoformat(),
        }],
        requested_by_user_id=admin.id,
        queued_at=utcnow(),
        started_at=started_at,
        completed_at=completed_at,
        error_message="Safe controlled failure." if status == "failed" else None,
    )
    db.session.add(run)
    db.session.flush()
    return run


def assert_log_is_safe(run_log):
    text = " ".join([
        str(run_log.safe_summary_json or {}),
        run_log.error_code or "",
        run_log.trigger_source or "",
    ])
    unsafe_values = [
        PRIVATE_UPLOAD_ROOT,
        "private-schedule",
        "unsafe-schedule-original",
        "unsafe-schedule-stored",
        "unsafe-schedule-version",
        "unsafe-schedule-hash",
        "Hidden Scheduled Actor",
        "Hidden Scheduled Contact",
        "secret-schedule@example.com",
        "Unsafe scheduled document description",
        "SCHEDULE-",
        "FieldSight Schedule Authority",
    ]
    for unsafe in unsafe_values:
        assert_true(unsafe not in text, f"Unsafe value leaked into scheduled run log: {unsafe}")


def assert_private_content_hidden(page):
    unsafe_values = [
        PRIVATE_UPLOAD_ROOT,
        "private-schedule",
        "unsafe-schedule-original",
        "unsafe-schedule-stored",
        "unsafe-schedule-version",
        "unsafe-schedule-hash",
        "Hidden Scheduled Actor",
        "Hidden Scheduled Contact",
        "secret-schedule@example.com",
        "Unsafe scheduled document description",
        "SCHEDULE-",
        "FieldSight Schedule Authority",
    ]
    for unsafe in unsafe_values:
        assert_true(unsafe not in page, f"Private content rendered on schedule surface: {unsafe}")


def run_validation():
    try:
        with app.app_context():
            db.drop_all()
            db.create_all()
            seed_payment_plans()
            seed_datasets()
            seed_licensed_packs()
            seed_reference_data()
            seed_document_types()
            seed_reference_options()

            admin = create_user("Schedule Admin", "admin@example.com", role="admin")
            subscriber = create_user("Schedule Subscriber", "subscriber@example.com")
            organization = PartnerOrganization(name="Phase 5.2 Partner", slug="phase-5-2-partner", status="active")
            db.session.add(organization)
            db.session.flush()

            queued_runs = []
            control_ids = []
            for suffix in ["queue-a", "queue-b", "queue-c"]:
                document, version, control = create_document(admin, organization, suffix)
                queued_runs.append(create_run(document, version, admin))
                control_ids.append(control.id)

            failure_document, failure_version, _failure_control = create_document(admin, organization, "repeat-failure")
            first_failure = create_run(
                failure_document,
                failure_version,
                admin,
                status="failed",
                completed_at=utcnow() - timedelta(hours=2),
            )
            second_failure = create_run(
                failure_document,
                failure_version,
                admin,
                status="failed",
                completed_at=utcnow() - timedelta(hours=1),
            )

            review_document, review_version, _review_control = create_document(admin, organization, "needs-review")
            needs_review_run = create_run(review_document, review_version, admin, status="needs_review")

            stale_document, stale_version, _stale_control = create_document(admin, organization, "stale")
            stale_run = create_run(
                stale_document,
                stale_version,
                admin,
                status="running",
                started_at=utcnow() - timedelta(minutes=90),
            )
            db.session.commit()

            ids = {
                "admin": admin.id,
                "queued_runs": [run.id for run in queued_runs],
                "control_ids": control_ids,
                "first_failure": first_failure.id,
                "second_failure": second_failure.id,
                "needs_review": needs_review_run.id,
                "stale": stale_run.id,
            }

        client = app.test_client()
        route_paths = [
            "/admin/intelligence-automation/schedule",
            "/admin/intelligence-automation/schedule/update",
            "/admin/intelligence-automation/schedule/run-now",
        ]
        response = client.get(route_paths[0], follow_redirects=False)
        assert_true(response.status_code == 302 and "/login" in response.headers.get("Location", ""), "Schedule page did not require login")
        for path in route_paths[1:]:
            response = client.post(path, follow_redirects=False)
            assert_true(response.status_code == 302 and "/login" in response.headers.get("Location", ""), f"{path} did not require login")

        with client:
            login(client, "subscriber@example.com")
            response = client.get(route_paths[0], follow_redirects=False)
            assert_true(response.status_code in (302, 303), "Schedule page was not admin-only")
            for path in route_paths[1:]:
                response = client.post(path, follow_redirects=False)
                assert_true(response.status_code in (302, 303), f"{path} was not admin-only")
            logout(client)

            login(client, "admin@example.com")
            response = client.post(
                "/admin/intelligence-automation/schedule/update",
                data={
                    "enabled": "false",
                    "batch_limit": "1",
                    "stale_run_threshold_minutes": "30",
                    "stale_run_action": "fail",
                    "processing_frequency_label": "Every 15 minutes",
                    "notes": "Controlled operations schedule.",
                },
                follow_redirects=False,
            )
            assert_true(response.status_code in (302, 303), "Schedule update did not redirect")
            with app.app_context():
                config = AutomationScheduleConfig.query.filter_by(schedule_code="document_intelligence").one()
                assert_true(config.enabled is False, "Disabled schedule setting did not persist")
                assert_true(config.batch_limit == 1, "Batch limit did not persist")
                assert_true(config.stale_run_threshold_minutes == 30, "Stale threshold did not persist")
                assert_true(config.stale_run_action == "fail", "Stale action did not persist")
                assert_true(config.processing_frequency_label == "Every 15 minutes", "Frequency label did not persist")
                update_audit = AuditLog.query.filter_by(action="admin_automation_schedule_updated").first()
                assert_true(update_audit is not None, "Schedule update audit missing")

            response = client.get("/admin/intelligence-automation/schedule")
            assert_true(response.status_code == 200, "Schedule page did not render")
            schedule_page = response.get_data(as_text=True)
            for label in ["Failed Runs", "Stale Running", "Needs Review", "Repeated Failures", "Queue Backlog"]:
                assert_true(label in schedule_page, f"Alert summary missing: {label}")
            assert_true("Documents have failed automation processing more than once" in schedule_page, "Repeated-failure alert was not active")
            assert_true("Queued jobs exceed the configured batch limit" in schedule_page, "Backlog alert was not active")
            assert_private_content_hidden(schedule_page)

            with app.app_context():
                queued_before = DocumentAutomationRun.query.filter_by(status="queued").count()
            response = client.post("/admin/intelligence-automation/schedule/run-now", follow_redirects=False)
            assert_true(response.status_code in (302, 303), "Disabled run-now did not redirect")
            with app.app_context():
                queued_after = DocumentAutomationRun.query.filter_by(status="queued").count()
                assert_true(queued_after == queued_before, "Disabled schedule processed queued runs")
                disabled_log = AutomationScheduledRunLog.query.order_by(AutomationScheduledRunLog.id.desc()).first()
                assert_true(disabled_log.status == "skipped_disabled", "Disabled schedule did not create skipped log")
                assert_true(disabled_log.processed_count == 0, "Disabled schedule log reported processing")
                assert_log_is_safe(disabled_log)

            response = client.post(
                "/admin/intelligence-automation/schedule/update",
                data={
                    "enabled": "true",
                    "batch_limit": "2",
                    "stale_run_threshold_minutes": "30",
                    "stale_run_action": "fail",
                    "processing_frequency_label": "Every 15 minutes",
                    "notes": "Controlled operations schedule.",
                },
                follow_redirects=False,
            )
            assert_true(response.status_code in (302, 303), "Enabled schedule update did not redirect")

            response = client.post("/admin/intelligence-automation/schedule/run-now", follow_redirects=False)
            assert_true(response.status_code in (302, 303), "Enabled run-now did not redirect")
            with app.app_context():
                config = AutomationScheduleConfig.query.filter_by(schedule_code="document_intelligence").one()
                assert_true(config.enabled is True, "Enabled schedule setting did not persist")
                run_now_log = AutomationScheduledRunLog.query.filter_by(trigger_source="admin_run_now").order_by(AutomationScheduledRunLog.id.desc()).first()
                assert_true(run_now_log is not None, "Run-now log missing")
                assert_true(run_now_log.processed_count == 2, "Enabled schedule did not respect batch limit")
                assert_true(run_now_log.stale_runs_handled == 1, "Enabled schedule did not handle stale run")
                assert_true(run_now_log.status == "completed_with_attention", "Stale failure did not produce attention status")
                assert_log_is_safe(run_now_log)
                stale = db.session.get(DocumentAutomationRun, ids["stale"])
                assert_true(stale.status == "failed", "Configured stale fail action did not persist")
                assert_true(DocumentAutomationRun.query.filter_by(status="queued").count() == 1, "Enabled schedule processed the wrong queue size")
                for control_id in ids["control_ids"]:
                    assert_true(db.session.get(DocumentPublishControl, control_id).status == "blocked", "Scheduled processing changed publish readiness")

            response = client.get("/admin/intelligence-automation")
            assert_true(response.status_code == 200, "Automation dashboard did not render")
            dashboard_page = response.get_data(as_text=True)
            assert_true("Operational Alerts" in dashboard_page, "Dashboard operational alerts missing")
            assert_true("Schedule details" in dashboard_page, "Dashboard schedule link missing")
            assert_private_content_hidden(dashboard_page)

        script_result = run_scheduled_cycle()
        assert_true(script_result["schedule_enabled"] is True, "Scheduler script did not use enabled config")
        assert_true(script_result["processed"] is True, "Scheduler script did not process queue")
        with app.app_context():
            script_log = AutomationScheduledRunLog.query.filter_by(trigger_source="scheduler_script").order_by(AutomationScheduledRunLog.id.desc()).first()
            assert_true(script_log is not None, "Scheduler script log missing")
            assert_true(script_log.processed_count == 1, "Scheduler script did not process remaining queued run")
            assert_true(DocumentAutomationRun.query.filter_by(status="queued").count() == 0, "Scheduler script left expected queued run")
            assert_log_is_safe(script_log)
            for run_log in AutomationScheduledRunLog.query.all():
                assert_log_is_safe(run_log)
            for control_id in ids["control_ids"]:
                assert_true(db.session.get(DocumentPublishControl, control_id).status == "blocked", "Scheduler script changed publish readiness")

        print("Phase 5.2 scheduled processing and alerts validation passed.")
    finally:
        shutil.rmtree(PRIVATE_UPLOAD_ROOT, ignore_errors=True)


if __name__ == "__main__":
    run_validation()
