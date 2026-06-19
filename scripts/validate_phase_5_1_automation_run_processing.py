"""Validate Phase 5.1 deterministic automation run processing."""

import os
import shutil
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

PRIVATE_UPLOAD_ROOT = tempfile.mkdtemp(prefix="fieldsight-phase-5-1-docs-")

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SESSION_SECRET", "phase-5-1-validation-secret")
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
from document_automation import SAFE_FAILURE_MESSAGES, process_automation_run  # noqa: E402
from models import (  # noqa: E402
    ActorConsentRecord,
    ActorDocument,
    ActorDocumentVersion,
    AuditLog,
    Crop,
    DocumentAutomationRun,
    DocumentExtractionRun,
    DocumentPublishControl,
    DocumentType,
    MarketActor,
    PartnerOrganization,
    User,
)
from scripts.process_document_automation_runs import run_batch  # noqa: E402


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


def extraction_content(reference_number, issuing_body="FieldSight Validation Authority"):
    return "\n".join([
        f"document_reference_number: {reference_number}",
        f"issuing_body: {issuing_body}",
        "issued_at: 2026-01-01",
        "expires_at: 2027-12-31",
        "origin_country: Nigeria",
        "crop_or_commodity: Ginger",
    ])


def create_document(admin, organization, suffix, *, file_exists=True, mismatch=False, with_consent=True):
    crop = Crop.query.filter_by(name="Ginger").one()
    actor = MarketActor(
        partner_organization_id=organization.id,
        created_by_user_id=admin.id,
        actor_type="exporter",
        name=f"Hidden Processing Actor {suffix}",
        crop_id=crop.id,
        status="active",
    )
    db.session.add(actor)
    db.session.flush()

    document_type = DocumentType.query.filter_by(name="Certificate of Origin").one()
    reference_number = f"AUTO-{suffix.upper()}-001"
    file_reference = f"AUTO-{suffix.upper()}-MISMATCH" if mismatch else reference_number
    file_path = Path(PRIVATE_UPLOAD_ROOT) / f"private-{suffix}.csv"
    if file_exists:
        file_path.write_text(extraction_content(file_reference), encoding="utf-8")

    document = ActorDocument(
        market_actor_id=actor.id,
        partner_organization_id=organization.id,
        document_type_id=document_type.id,
        uploaded_by_user_id=admin.id,
        title=f"Hidden Processing Document {suffix}",
        description="Unsafe private document description should not render.",
        original_filename=f"unsafe-original-processing-{suffix}.csv",
        stored_filename=f"unsafe-stored-processing-{suffix}.csv",
        storage_path=str(file_path),
        mime_type="text/csv",
        file_size=1024,
        file_hash=f"unsafe-processing-hash-{suffix}",
        version_number=1,
        document_reference_number=reference_number,
        issuing_body="FieldSight Validation Authority",
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
        original_filename=f"unsafe-version-processing-{suffix}.csv",
        content_type="text/csv",
        file_size_bytes=1024,
        checksum_sha256=f"unsafe-version-hash-{suffix}",
        uploaded_by_user_id=admin.id,
        document_status="submitted",
    )
    db.session.add(version)
    db.session.flush()

    if with_consent:
        db.session.add(ActorConsentRecord(
            market_actor_id=actor.id,
            partner_organization_id=organization.id,
            consent_status="granted",
            consent_method="written",
            consent_reference=f"CONSENT-PROCESS-{suffix}",
            consent_scope_json=["store_actor_documents", "use_documents_for_extraction_quality"],
            sharing_channels_json=["internal_review", "admin_review"],
            granted_by_name="Hidden Processing Contact",
            granted_by_email="secret-processing@example.com",
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


def create_run(document, version, admin, status="queued", started_at=None):
    run = DocumentAutomationRun(
        actor_document_id=document.id,
        actor_document_version_id=version.id,
        job_type="document_intelligence",
        trigger_source="phase_5_1_validation",
        status=status,
        eligibility_checks_json=[{
            "key": "validation",
            "label": "Validation",
            "status": "pass",
            "message": "Safe validation eligibility.",
        }],
        confidence_summary_json={"average_confidence": None, "quality_score": None},
        event_log_json=[{
            "event_type": "automation_run_queued",
            "message": "Safe queued event.",
            "metadata": {"auto_published": False},
            "recorded_at": utcnow().isoformat(),
        }],
        requested_by_user_id=admin.id,
        queued_at=utcnow(),
        started_at=started_at,
    )
    db.session.add(run)
    db.session.flush()
    return run


def assert_safe_run(run):
    unsafe_values = [
        "/private-",
        "unsafe-original-processing",
        "unsafe-stored-processing",
        "unsafe-version-processing",
        "unsafe-processing-hash",
        "unsafe-version-hash",
        "Hidden Processing Actor",
        "Hidden Processing Contact",
        "secret-processing@example.com",
        "Unsafe private document description",
    ]
    error_text = run.error_message or ""
    event_text = str(run.event_log_json or [])
    for unsafe in unsafe_values:
        assert_true(unsafe not in error_text, f"Unsafe value leaked into error message: {unsafe}")
        assert_true(unsafe not in event_text, f"Unsafe value leaked into event log: {unsafe}")


def assert_private_content_hidden(page):
    unsafe_values = [
        PRIVATE_UPLOAD_ROOT,
        "private-completed.csv",
        "unsafe-original-processing",
        "unsafe-stored-processing",
        "unsafe-version-processing",
        "unsafe-processing-hash",
        "unsafe-version-hash",
        "Hidden Processing Actor",
        "Hidden Processing Contact",
        "secret-processing@example.com",
        "Unsafe private document description",
        "AUTO-COMPLETED-001",
        "FieldSight Validation Authority",
    ]
    for unsafe in unsafe_values:
        assert_true(unsafe not in page, f"Private content rendered on automation page: {unsafe}")


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

            admin = create_user("Processing Admin", "admin@example.com", role="admin")
            subscriber = create_user("Processing Subscriber", "subscriber@example.com")
            organization = PartnerOrganization(name="Phase 5.1 Partner", slug="phase-5-1-partner", status="active")
            db.session.add(organization)
            db.session.flush()

            completed_doc, completed_version, completed_control = create_document(admin, organization, "completed")
            review_doc, review_version, review_control = create_document(admin, organization, "review", mismatch=True)
            failed_doc, failed_version, failed_control = create_document(admin, organization, "failed", file_exists=False)
            batch_doc, batch_version, _batch_control = create_document(admin, organization, "batch")
            script_doc, script_version, _script_control = create_document(admin, organization, "script")
            stale_doc, stale_version, _stale_control = create_document(admin, organization, "stale")
            consent_blocked_doc, consent_blocked_version, _blocked_control = create_document(
                admin,
                organization,
                "consent-blocked",
                with_consent=False,
            )

            completed_run = create_run(completed_doc, completed_version, admin)
            review_run = create_run(review_doc, review_version, admin)
            failed_run = create_run(failed_doc, failed_version, admin)
            batch_run = create_run(batch_doc, batch_version, admin)
            script_run = create_run(script_doc, script_version, admin, status="cancelled")
            stale_run = create_run(
                stale_doc,
                stale_version,
                admin,
                status="running",
                started_at=utcnow() - timedelta(minutes=90),
            )
            consent_blocked_run = create_run(consent_blocked_doc, consent_blocked_version, admin)
            db.session.commit()

            ids = {
                "completed_run": completed_run.id,
                "review_run": review_run.id,
                "failed_run": failed_run.id,
                "batch_run": batch_run.id,
                "script_run": script_run.id,
                "stale_run": stale_run.id,
                "consent_blocked_run": consent_blocked_run.id,
                "completed_document": completed_doc.id,
                "completed_control": completed_control.id,
                "review_control": review_control.id,
                "failed_control": failed_control.id,
            }

        client = app.test_client()

        for path in [
            f"/admin/intelligence-automation/runs/{ids['completed_run']}/process",
            "/admin/intelligence-automation/process-queued",
        ]:
            response = client.post(path, follow_redirects=False)
            assert_true(response.status_code == 302 and "/login" in response.headers.get("Location", ""), f"{path} did not require login")

        with client:
            login(client, "subscriber@example.com")
            for path in [
                f"/admin/intelligence-automation/runs/{ids['completed_run']}/process",
                "/admin/intelligence-automation/process-queued",
            ]:
                response = client.post(path, follow_redirects=False)
                assert_true(response.status_code in (302, 303), f"{path} was not admin-only")
            logout(client)

            login(client, "admin@example.com")
            response = client.post(
                f"/admin/intelligence-automation/runs/{ids['completed_run']}/process",
                follow_redirects=False,
            )
            assert_true(response.status_code in (302, 303), "Single process route did not redirect")

            with app.app_context():
                completed = db.session.get(DocumentAutomationRun, ids["completed_run"])
                assert_true(completed.status == "completed", "Queued run did not complete")
                assert_true(completed.started_at is not None, "Running transition was not persisted")
                assert_true(completed.completed_at is not None, "Completion time was not persisted")
                assert_true(completed.extraction_run_id is not None, "Processing did not create an extraction run")
                assert_true(completed.confidence_summary_json.get("quality_score") is not None, "Confidence summary was not updated")
                event_types = [event.get("event_type") for event in completed.event_log_json]
                assert_true("automation_run_started" in event_types, "Started event missing")
                assert_true("automation_run_completed" in event_types, "Completed event missing")
                extraction_run = db.session.get(DocumentExtractionRun, completed.extraction_run_id)
                assert_true(extraction_run.source_filename is None, "Automation extraction stored a source filename")
                assert_true(extraction_run.raw_text_excerpt is None, "Automation extraction stored raw text")
                control = db.session.get(DocumentPublishControl, ids["completed_control"])
                assert_true(control.status == "blocked", "Processing changed publish readiness")
                document = db.session.get(ActorDocument, ids["completed_document"])
                assert_true(document.review_status == "approved", "Processing changed document review status")
                assert_true(document.redaction_status == "completed", "Processing changed redaction status")
                started_audit = AuditLog.query.filter_by(
                    action="document_automation_run_started",
                    entity_id=completed.id,
                ).first()
                completed_audit = AuditLog.query.filter_by(
                    action="document_automation_run_completed",
                    entity_id=completed.id,
                ).first()
                assert_true(started_audit is not None and completed_audit is not None, "Processing audit trail missing")
                assert_true(completed_audit.after_values.get("auto_published") is False, "Processing audit implied publishing")
                assert_safe_run(completed)

            response = client.post(
                f"/admin/intelligence-automation/runs/{ids['review_run']}/process",
                follow_redirects=False,
            )
            assert_true(response.status_code in (302, 303), "Needs-review process route did not redirect")
            with app.app_context():
                review_run = db.session.get(DocumentAutomationRun, ids["review_run"])
                assert_true(review_run.status == "needs_review", "Mismatch run did not move to needs review")
                assert_true(review_run.confidence_summary_json.get("mismatch_count") == 1, "Mismatch summary was not persisted")
                assert_true(db.session.get(DocumentPublishControl, ids["review_control"]).status == "blocked", "Needs-review processing changed publish readiness")
                assert_safe_run(review_run)

            response = client.post(
                f"/admin/intelligence-automation/runs/{ids['failed_run']}/process",
                follow_redirects=False,
            )
            assert_true(response.status_code in (302, 303), "Failed process route did not redirect")
            with app.app_context():
                failed = db.session.get(DocumentAutomationRun, ids["failed_run"])
                assert_true(failed.status == "failed", "Missing-file run did not fail")
                assert_true(failed.error_message == SAFE_FAILURE_MESSAGES["missing_file"], "Failed run did not store safe error")
                assert_true(db.session.get(DocumentPublishControl, ids["failed_control"]).status == "blocked", "Failed processing changed publish readiness")
                assert_safe_run(failed)

            response = client.post(
                f"/admin/intelligence-automation/runs/{ids['consent_blocked_run']}/process",
                follow_redirects=False,
            )
            assert_true(response.status_code in (302, 303), "Consent-blocked process route did not redirect")
            with app.app_context():
                blocked = db.session.get(DocumentAutomationRun, ids["consent_blocked_run"])
                assert_true(blocked.status == "needs_review", "Consent-blocked run should require review")
                assert_true(blocked.extraction_run_id is None, "Consent-blocked run created extraction output")
                assert_safe_run(blocked)

            response = client.post(
                "/admin/intelligence-automation/process-queued",
                data={"limit": "10", "stale_minutes": "30", "stale_action": "requeue"},
                follow_redirects=False,
            )
            assert_true(response.status_code in (302, 303), "Batch process route did not redirect")
            with app.app_context():
                batch = db.session.get(DocumentAutomationRun, ids["batch_run"])
                stale = db.session.get(DocumentAutomationRun, ids["stale_run"])
                assert_true(batch.status == "completed", "Batch route did not process queued run")
                assert_true(stale.status == "completed", "Stale running run was not requeued and processed")
                stale_events = [event.get("event_type") for event in stale.event_log_json]
                assert_true("automation_stale_run_requeued" in stale_events, "Stale requeue event missing")
                assert_true("automation_run_completed" in stale_events, "Recovered stale run did not complete")
                assert_safe_run(stale)

            response = client.get("/admin/intelligence-automation")
            assert_true(response.status_code == 200, "Automation dashboard did not render")
            dashboard_page = response.get_data(as_text=True)
            assert_true("Processed 24h" in dashboard_page, "Dashboard processing summary missing")
            assert_true("Stale Running" in dashboard_page, "Dashboard stale count missing")
            assert_true("Process Queued" in dashboard_page, "Dashboard batch control missing")
            assert_private_content_hidden(dashboard_page)

            response = client.get(f"/admin/intelligence-automation/runs/{ids['failed_run']}")
            assert_true(response.status_code == 200, "Failed run detail did not render")
            assert_private_content_hidden(response.get_data(as_text=True))

        with app.app_context():
            script_run = db.session.get(DocumentAutomationRun, ids["script_run"])
            assert_true(script_run.status == "cancelled", "HTTP batch unexpectedly changed script fixture")
            script_run.status = "queued"
            script_run.queued_at = utcnow()
            script_run.cancelled_at = None
            db.session.commit()

        summary = run_batch(limit=5, stale_minutes=30, stale_action="requeue")
        assert_true(summary["auto_published"] is False, "Batch script summary implied publishing")
        assert_true(summary["external_access_created"] is False, "Batch script summary implied access creation")
        with app.app_context():
            script_processed = db.session.get(DocumentAutomationRun, ids["script_run"])
            assert_true(script_processed.status == "completed", "Batch script did not process queued run")
            assert_safe_run(script_processed)

        with app.app_context():
            non_queued_result = process_automation_run(ids["completed_run"])
            assert_true(non_queued_result["processed"] is False, "Processor reprocessed a non-queued run")
            assert_true(non_queued_result["error_code"] == "not_queued", "Non-queued result was not predictable")

        print("Phase 5.1 automation run processing validation passed.")
    finally:
        shutil.rmtree(PRIVATE_UPLOAD_ROOT, ignore_errors=True)


if __name__ == "__main__":
    run_validation()
