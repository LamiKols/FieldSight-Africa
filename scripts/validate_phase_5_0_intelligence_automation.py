"""Validate Phase 5.0 intelligence automation foundation.

This script uses an in-memory SQLite database and Flask's test client so it
does not touch Replit PostgreSQL data, private document files, payment
providers, or external OCR/AI services.
"""

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SESSION_SECRET", "phase-5-0-validation-secret")
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
    ActorLocation,
    AuditLog,
    Crop,
    DocumentAutomationRun,
    DocumentExtractionRun,
    DocumentFieldReconciliation,
    DocumentPublishControl,
    DocumentType,
    MarketActor,
    PartnerOrganization,
    Region,
    User,
)


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


def confidence_summary(score=88, average=86.0, fields=2, pending=1, mismatches=1, risks=1):
    return {
        "latest_extraction_run_id": None,
        "latest_extraction_status": "completed",
        "document_intelligence_status": "extracted",
        "quality_score": score,
        "average_confidence": average,
        "field_count": fields,
        "accepted_count": max(fields - pending, 0),
        "rejected_count": 0,
        "pending_count": pending,
        "manual_override_count": 0,
        "mismatch_count": mismatches,
        "risk_flag_count": risks,
        "low_confidence_count": 0,
    }


def create_document(admin, organization, suffix, *, with_consent=True, with_version=True, document_status="approved", review_status="approved"):
    region = Region.query.filter_by(code="SW").one()
    crop = Crop.query.filter_by(name="Ginger").one()
    actor = MarketActor(
        partner_organization_id=organization.id,
        created_by_user_id=admin.id,
        actor_type="exporter",
        name=f"Hidden Exporter {suffix}",
        crop_id=crop.id,
        status="active",
    )
    db.session.add(actor)
    db.session.flush()
    db.session.add(ActorLocation(
        market_actor_id=actor.id,
        region_id=region.id,
        location_text="Hidden actor location",
        is_primary=True,
    ))

    document_type = DocumentType.query.filter_by(name="Certificate of Origin").one()
    document = ActorDocument(
        market_actor_id=actor.id,
        partner_organization_id=organization.id,
        document_type_id=document_type.id,
        uploaded_by_user_id=admin.id,
        title=f"Hidden Automation Certificate {suffix}",
        description="Unsafe restricted document description should not render.",
        original_filename=f"unsafe-original-auto-{suffix}.pdf",
        stored_filename=f"unsafe-stored-auto-{suffix}.pdf",
        storage_path=f"/private_uploads/unsafe/auto-{suffix}.pdf",
        mime_type="application/pdf",
        file_size=2048,
        file_hash=f"unsafe-file-hash-auto-{suffix}",
        version_number=1,
        document_reference_number=f"REF-SECRET-{suffix}",
        issuing_body="Hidden Issuing Body",
        linked_crop_id=crop.id,
        document_status=document_status,
        review_status=review_status,
        verification_status="verified",
        redaction_status="completed",
        subscriber_access_level="metadata_only",
        visibility_level="metadata_only",
    )
    db.session.add(document)
    db.session.flush()

    if with_version:
        db.session.add(ActorDocumentVersion(
            actor_document_id=document.id,
            version_number=1,
            storage_backend="local_private",
            storage_path=f"/private_uploads/unsafe/version-{suffix}.pdf",
            original_filename=f"unsafe-version-original-{suffix}.pdf",
            content_type="application/pdf",
            file_size_bytes=2048,
            checksum_sha256=f"unsafe-version-hash-{suffix}",
            uploaded_by_user_id=admin.id,
            document_status="submitted",
        ))

    if with_consent:
        db.session.add(ActorConsentRecord(
            market_actor_id=actor.id,
            partner_organization_id=organization.id,
            consent_status="granted",
            consent_method="written",
            consent_reference=f"CONSENT-AUTO-{suffix}",
            consent_scope_json=[
                "store_actor_documents",
                "use_actor_data_for_verification",
                "use_documents_for_extraction_quality",
            ],
            permitted_document_categories_json=["export_compliance_document"],
            sharing_channels_json=["internal_review", "admin_review"],
            granted_by_name="Hidden Actor Contact",
            granted_by_email="secret-contact@example.com",
            granted_at=utcnow(),
            expires_at=utcnow() + timedelta(days=365),
            captured_by_user_id=admin.id,
            active=True,
        ))

    extraction_run = DocumentExtractionRun(
        actor_document_id=document.id,
        status="completed",
        extractor_type="template",
        document_type_code=document_type.code,
        template_profile_code="certificate_of_origin_v1",
        source_filename=f"unsafe-source-file-{suffix}.pdf",
        extracted_fields_json={"document_reference_number": f"REF-SECRET-{suffix}"},
        confidence_json={"document_reference_number": 0.86, "issuing_body": 0.86},
        field_evidence_json={"document_reference_number": {"source": "unsafe evidence should not render"}},
        provenance_json={"source": "private_version"},
        metadata_mismatches_json=[{"field_name": "issuing_body", "current": "Hidden", "extracted": "Hidden"}],
        risk_flags_json=["metadata_mismatch"],
        expiry_renewal_json={"status": "current"},
        quality_score=88,
        document_intelligence_status="extracted",
        raw_text_excerpt="Unsafe raw extracted text should not render.",
        created_by_user_id=admin.id,
    )
    db.session.add(extraction_run)
    db.session.flush()
    db.session.add(DocumentFieldReconciliation(
        actor_document_id=document.id,
        extraction_run_id=extraction_run.id,
        field_name="document_reference_number",
        field_label="Reference Number",
        current_value=f"REF-SECRET-{suffix}",
        extracted_value=f"REF-SECRET-{suffix}",
        accepted_value=f"REF-SECRET-{suffix}",
        confidence=0.86,
        status="accepted",
        evidence_json={"source": "unsafe evidence should not render"},
        provenance_json={"source_filename": f"unsafe-source-file-{suffix}.pdf"},
    ))
    db.session.add(DocumentFieldReconciliation(
        actor_document_id=document.id,
        extraction_run_id=extraction_run.id,
        field_name="issuing_body",
        field_label="Issuing Body",
        current_value="Hidden Issuing Body",
        extracted_value="Hidden Issuing Body",
        confidence=0.86,
        status="pending",
        evidence_json={"source": "unsafe evidence should not render"},
        provenance_json={"source_filename": f"unsafe-source-file-{suffix}.pdf"},
    ))
    db.session.add(DocumentPublishControl(
        actor_document_id=document.id,
        publish_target="subscriber_portal_metadata",
        status="blocked",
        readiness_checks_json=[{"key": "validation", "status": "fail"}],
        blocking_reasons_json=["Validation keeps this blocked."],
        admin_decision="validation",
        last_evaluated_at=utcnow(),
    ))
    db.session.flush()
    return document, extraction_run


def create_automation_run(document, extraction_run, status, admin, *, days_ago=1, average=86.0):
    created_at = utcnow() - timedelta(days=days_ago)
    run = DocumentAutomationRun(
        actor_document_id=document.id,
        actor_document_version_id=document.versions[0].id if document.versions else None,
        extraction_run_id=extraction_run.id if extraction_run else None,
        job_type="document_intelligence",
        trigger_source="validation_seed",
        status=status,
        eligibility_checks_json=[{"key": "validation", "label": "Validation", "status": "pass", "message": "Seeded safe run."}],
        confidence_summary_json=confidence_summary(average=average),
        event_log_json=[{"event_type": "seeded", "message": "Seeded safe event.", "metadata": {"auto_published": False}, "recorded_at": created_at.isoformat()}],
        requested_by_user_id=admin.id,
        queued_at=created_at,
        created_at=created_at,
        updated_at=created_at,
    )
    if status == "completed":
        run.completed_at = created_at + timedelta(minutes=5)
    if status == "running":
        run.started_at = created_at + timedelta(minutes=1)
    if status == "cancelled":
        run.cancelled_at = created_at + timedelta(minutes=2)
        run.cancelled_by_user_id = admin.id
    db.session.add(run)
    db.session.flush()
    return run


def assert_unsafe_values_hidden(page):
    unsafe_values = [
        "/private_uploads/",
        "unsafe-original-auto",
        "unsafe-stored-auto",
        "unsafe-version-original",
        "unsafe-version-hash",
        "unsafe-file-hash-auto",
        "unsafe-source-file",
        "Unsafe raw extracted text",
        "Unsafe restricted document description",
        "unsafe evidence should not render",
        "Hidden Exporter",
        "Hidden Actor Contact",
        "secret-contact@example.com",
        "REF-SECRET",
        "Hidden Issuing Body",
    ]
    for unsafe in unsafe_values:
        assert_true(unsafe not in page, f"Unsafe value leaked on automation surface: {unsafe}")


def run_validation():
    with app.app_context():
        db.drop_all()
        db.create_all()
        seed_payment_plans()
        seed_datasets()
        seed_licensed_packs()
        seed_reference_data()
        seed_document_types()
        seed_reference_options()

        admin = create_user("Automation Admin", "admin@example.com", role="admin")
        subscriber = create_user("Automation Subscriber", "subscriber@example.com")
        organization = PartnerOrganization(name="Phase 5 Partner", slug="phase-5-partner", status="active")
        db.session.add(organization)
        db.session.flush()

        manual_document, manual_extraction = create_document(admin, organization, "manual")
        retry_document, retry_extraction = create_document(admin, organization, "retry")
        cancel_document, cancel_extraction = create_document(admin, organization, "cancel")
        completed_document, completed_extraction = create_document(admin, organization, "completed")
        old_document, old_extraction = create_document(admin, organization, "old")
        blocked_document, _blocked_extraction = create_document(admin, organization, "blocked", with_consent=False)

        failed_run = create_automation_run(retry_document, retry_extraction, "failed", admin)
        queued_run = create_automation_run(cancel_document, cancel_extraction, "queued", admin)
        completed_run = create_automation_run(completed_document, completed_extraction, "completed", admin)
        old_run = create_automation_run(old_document, old_extraction, "completed", admin, days_ago=120, average=42.0)
        db.session.commit()

        ids = {
            "manual_document": manual_document.id,
            "blocked_document": blocked_document.id,
            "failed_run": failed_run.id,
            "queued_run": queued_run.id,
            "completed_run": completed_run.id,
            "old_run": old_run.id,
            "old_document": old_document.id,
            "document_type_id": manual_document.document_type_id,
            "partner_id": organization.id,
            "actor_public_id": retry_document.market_actor.public_id,
        }

    client = app.test_client()

    for path in [
        "/admin/intelligence-automation",
        "/admin/intelligence-automation/runs",
        f"/admin/intelligence-automation/runs/{ids['failed_run']}",
    ]:
        response = client.get(path, follow_redirects=False)
        assert_true(response.status_code == 302 and "/login" in response.headers.get("Location", ""), f"{path} did not require login")

    with client:
        login(client, "subscriber@example.com")
        for path in [
            "/admin/intelligence-automation",
            "/admin/intelligence-automation/runs",
            f"/admin/intelligence-automation/runs/{ids['failed_run']}",
        ]:
            response = client.get(path, follow_redirects=False)
            assert_true(response.status_code in (302, 303), f"{path} was not admin-only")
        logout(client)

        login(client, "admin@example.com")
        response = client.get("/admin/intelligence-automation")
        assert_true(response.status_code == 200, "Automation dashboard did not render")
        page = response.get_data(as_text=True)
        assert_true("Intelligence Automation" in page, "Automation dashboard title missing")
        assert_true("Status Mix" in page, "Automation dashboard status summary missing")
        assert_unsafe_values_hidden(page)

        response = client.get("/admin/intelligence-automation/runs")
        assert_true(response.status_code == 200, "Automation run list did not render")
        page = response.get_data(as_text=True)
        assert_true("Automation Runs" in page, "Automation run list title missing")
        assert_true(f"#{ids['failed_run']}" in page, "Run list missed failed run")
        assert_true(f"Document #{ids['old_document']}" not in page, "Default 30-day run list included old run")
        assert_unsafe_values_hidden(page)

        response = client.get("/admin/intelligence-automation/runs?date_window=all")
        assert_true(f"Document #{ids['old_document']}" in response.get_data(as_text=True), "All-time run list missed old run")

        filter_paths = [
            f"/admin/intelligence-automation/runs?status=failed&date_window=all",
            f"/admin/intelligence-automation/runs?document_type_id={ids['document_type_id']}&date_window=all",
            f"/admin/intelligence-automation/runs?partner_organization_id={ids['partner_id']}&date_window=all",
            f"/admin/intelligence-automation/runs?actor={ids['actor_public_id']}&date_window=all",
            "/admin/intelligence-automation/runs?confidence_min=80&date_window=all",
            "/admin/intelligence-automation/runs?confidence_max=50&date_window=all",
        ]
        for path in filter_paths:
            response = client.get(path)
            assert_true(response.status_code == 200, f"Automation filter failed for {path}")
            assert_unsafe_values_hidden(response.get_data(as_text=True))

        response = client.get(f"/admin/intelligence-automation/runs/{ids['failed_run']}")
        assert_true(response.status_code == 200, "Automation run detail did not render")
        page = response.get_data(as_text=True)
        assert_true("Confidence Summary" in page, "Run detail missing confidence summary")
        assert_true("Automated Extraction" in page, "Run detail missing automated extraction separation")
        assert_true("Human Review" in page, "Run detail missing human review separation")
        assert_true("Publish Target Separation" in page, "Run detail missing publish-readiness separation")
        assert_unsafe_values_hidden(page)

        response = client.post(f"/admin/intelligence-automation/runs/{ids['failed_run']}/retry", follow_redirects=False)
        assert_true(response.status_code in (302, 303), "Retry workflow did not redirect")
        with app.app_context():
            retry_child = DocumentAutomationRun.query.filter_by(retry_of_run_id=ids["failed_run"]).one()
            assert_true(retry_child.status == "queued", "Retry did not create a queued automation run")
            retry_audit = AuditLog.query.filter_by(
                action="admin_document_automation_retry_requested",
                entity_id=ids["failed_run"],
            ).first()
            assert_true(retry_audit is not None, "Retry audit log missing")

        response = client.post(f"/admin/intelligence-automation/runs/{ids['queued_run']}/cancel", follow_redirects=False)
        assert_true(response.status_code in (302, 303), "Cancel workflow did not redirect")
        with app.app_context():
            cancelled = db.session.get(DocumentAutomationRun, ids["queued_run"])
            assert_true(cancelled.status == "cancelled", "Queued automation run was not cancelled")
            cancel_audit = AuditLog.query.filter_by(
                action="admin_document_automation_run_cancelled",
                entity_id=ids["queued_run"],
            ).first()
            assert_true(cancel_audit is not None, "Cancel audit log missing")

        response = client.post(f"/admin/intelligence-automation/runs/{ids['completed_run']}/cancel", follow_redirects=False)
        assert_true(response.status_code in (302, 303), "Blocked cancel did not redirect")
        with app.app_context():
            completed = db.session.get(DocumentAutomationRun, ids["completed_run"])
            assert_true(completed.status == "completed", "Completed run status changed during blocked cancel")
            cancel_block = AuditLog.query.filter_by(
                action="admin_document_automation_cancel_blocked",
                entity_id=ids["completed_run"],
            ).first()
            assert_true(cancel_block is not None, "Blocked cancel audit log missing")

        response = client.post(f"/admin/documents/{ids['manual_document']}/automation/run", follow_redirects=False)
        assert_true(response.status_code in (302, 303), "Manual run trigger did not redirect")
        with app.app_context():
            manual_run = DocumentAutomationRun.query.filter_by(
                actor_document_id=ids["manual_document"],
                trigger_source="admin_manual",
            ).one()
            assert_true(manual_run.status == "queued", "Manual run trigger did not create a queued run")
            manual_audit = AuditLog.query.filter_by(
                action="admin_document_automation_run_queued",
                entity_id=manual_run.id,
            ).first()
            assert_true(manual_audit is not None, "Manual run audit missing")

        response = client.post(f"/admin/documents/{ids['blocked_document']}/automation/run", follow_redirects=False)
        assert_true(response.status_code in (302, 303), "Blocked manual trigger did not redirect")
        with app.app_context():
            blocked_runs = DocumentAutomationRun.query.filter_by(actor_document_id=ids["blocked_document"]).count()
            assert_true(blocked_runs == 0, "Ineligible document created an automation run")
            blocked_audit = AuditLog.query.filter_by(
                action="admin_document_automation_run_blocked",
                entity_id=ids["blocked_document"],
            ).first()
            assert_true(blocked_audit is not None, "Blocked manual run audit missing")

        response = client.get("/admin/")
        assert_true(response.status_code == 200, "Admin dashboard did not render")
        admin_dashboard = response.get_data(as_text=True)
        assert_true("Automation" in admin_dashboard, "Admin dashboard missing automation link/counter")

    print("Phase 5.0 intelligence automation validation passed.")


if __name__ == "__main__":
    run_validation()
