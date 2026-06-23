"""Validate Phase 5.3 intelligence insight generation and review."""

import os
import shutil
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

PRIVATE_UPLOAD_ROOT = tempfile.mkdtemp(prefix="fieldsight-phase-5-3-docs-")

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SESSION_SECRET", "phase-5-3-validation-secret")
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
    Crop,
    DocumentAutomationRun,
    DocumentExtractionRun,
    DocumentFieldReconciliation,
    DocumentPublishControl,
    DocumentType,
    IntelligenceInsight,
    MarketActor,
    PartnerOrganization,
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


def unsafe_values():
    return [
        PRIVATE_UPLOAD_ROOT,
        "unsafe-insight-original",
        "unsafe-insight-stored",
        "unsafe-insight-version",
        "unsafe-insight-hash",
        "Hidden Insight Actor",
        "Hidden Insight Contact",
        "secret-insight@example.com",
        "Unsafe insight document description",
        "INSIGHT-SECRET",
        "Secret Insight Authority",
        "RAW SECRET EXTRACTION TEXT",
        "EXTRACTED SECRET VALUE",
        "CURRENT SECRET VALUE",
    ]


def assert_private_content_hidden(page, surface):
    for unsafe in unsafe_values():
        assert_true(unsafe not in page, f"Private content rendered on {surface}: {unsafe}")


def assert_insight_is_safe(insight):
    text = " ".join([
        insight.title or "",
        insight.summary or "",
        str(insight.safe_summary_json or {}),
        str(insight.key_findings_json or []),
        str(insight.governance_flags_json or []),
        insight.review_notes or "",
    ])
    for unsafe in unsafe_values():
        assert_true(unsafe not in text, f"Unsafe value leaked into insight record: {unsafe}")


def create_document_bundle(admin, organization, suffix, *, risky=False, consent=True):
    crop = Crop.query.filter_by(name="Ginger").one()
    actor = MarketActor(
        partner_organization_id=organization.id,
        created_by_user_id=admin.id,
        actor_type="exporter",
        name=f"Hidden Insight Actor {suffix}",
        crop_id=crop.id,
        status="active",
    )
    db.session.add(actor)
    db.session.flush()

    document_type = DocumentType.query.filter_by(name="Certificate of Origin").one()
    file_path = Path(PRIVATE_UPLOAD_ROOT) / f"unsafe-insight-version-{suffix}.csv"
    file_path.write_text("RAW SECRET EXTRACTION TEXT\nEXTRACTED SECRET VALUE", encoding="utf-8")

    document = ActorDocument(
        market_actor_id=actor.id,
        partner_organization_id=organization.id,
        document_type_id=document_type.id,
        uploaded_by_user_id=admin.id,
        title=f"Unsafe insight document title {suffix}",
        description="Unsafe insight document description should not render.",
        original_filename=f"unsafe-insight-original-{suffix}.csv",
        stored_filename=f"unsafe-insight-stored-{suffix}.csv",
        storage_path=str(file_path),
        mime_type="text/csv",
        file_size=2048,
        file_hash=f"unsafe-insight-hash-{suffix}",
        version_number=1,
        document_reference_number=f"INSIGHT-SECRET-{suffix}",
        issuing_body="Secret Insight Authority",
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
        original_filename=f"unsafe-insight-version-{suffix}.csv",
        content_type="text/csv",
        file_size_bytes=2048,
        checksum_sha256=f"unsafe-insight-version-hash-{suffix}",
        uploaded_by_user_id=admin.id,
        document_status="submitted",
    )
    db.session.add(version)
    db.session.flush()

    if consent:
        db.session.add(ActorConsentRecord(
            market_actor_id=actor.id,
            partner_organization_id=organization.id,
            consent_status="granted",
            consent_method="written",
            consent_reference=f"CONSENT-INSIGHT-{suffix}",
            consent_scope_json=["store_actor_documents", "use_documents_for_extraction_quality"],
            sharing_channels_json=["internal_review", "admin_review"],
            granted_by_name="Hidden Insight Contact",
            granted_by_email="secret-insight@example.com",
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

    mismatches = []
    risk_flags = []
    if risky:
        mismatches = [{
            "field_name": "document_reference_number",
            "current_value": "CURRENT SECRET VALUE",
            "extracted_value": "EXTRACTED SECRET VALUE",
        }]
        risk_flags = ["metadata_mismatch", "renewal_due_soon"]

    extraction_run = DocumentExtractionRun(
        actor_document_id=document.id,
        actor_document_version_id=version.id,
        status="completed",
        extractor_type="automation_template",
        document_type_code=document_type.code,
        template_profile_code="certificate_of_origin_v1",
        source_filename="unsafe-insight-original.csv",
        extracted_fields_json={
            "document_reference_number": "EXTRACTED SECRET VALUE",
            "issuing_body": "Secret Insight Authority",
        },
        confidence_json={"document_reference_number": 0.92, "issuing_body": 0.88},
        field_evidence_json={"document_reference_number": {"excerpt": "RAW SECRET EXTRACTION TEXT"}},
        provenance_json={"source": "unsafe-insight-version.csv"},
        metadata_mismatches_json=mismatches,
        risk_flags_json=risk_flags,
        expiry_renewal_json={"status": "current"},
        quality_score=92 if not risky else 62,
        document_intelligence_status="extracted" if not risky else "needs_reconciliation",
        raw_text_excerpt="RAW SECRET EXTRACTION TEXT",
        created_by_user_id=admin.id,
    )
    db.session.add(extraction_run)
    db.session.flush()

    row_status = "accepted" if not risky else "pending"
    db.session.add(DocumentFieldReconciliation(
        actor_document_id=document.id,
        extraction_run_id=extraction_run.id,
        field_name="document_reference_number",
        field_label="Document reference number",
        current_value="CURRENT SECRET VALUE",
        extracted_value="EXTRACTED SECRET VALUE",
        accepted_value=None,
        confidence=0.92,
        status=row_status,
        evidence_json={"excerpt": "RAW SECRET EXTRACTION TEXT"},
        provenance_json={"source": "unsafe-insight-version.csv"},
        risk_flags_json=risk_flags,
    ))
    db.session.flush()

    automation_run = DocumentAutomationRun(
        actor_document_id=document.id,
        actor_document_version_id=version.id,
        extraction_run_id=extraction_run.id,
        job_type="document_intelligence",
        trigger_source="phase_5_3_validation",
        status="needs_review" if risky else "completed",
        eligibility_checks_json=[{
            "key": "validation",
            "label": "Validation",
            "status": "pass",
            "message": "Safe insight validation fixture.",
        }],
        confidence_summary_json={
            "latest_extraction_run_id": extraction_run.id,
            "latest_extraction_status": extraction_run.status,
            "document_intelligence_status": extraction_run.document_intelligence_status,
            "quality_score": extraction_run.quality_score,
            "average_confidence": 90 if not risky else 63,
            "field_count": 1,
            "accepted_count": 1 if not risky else 0,
            "pending_count": 0 if not risky else 1,
            "rejected_count": 0,
            "manual_override_count": 0,
            "mismatch_count": len(mismatches),
            "risk_flag_count": len(risk_flags),
            "unsafe_extra": "RAW SECRET EXTRACTION TEXT",
        },
        event_log_json=[{
            "event_type": "automation_run_completed",
            "message": "Safe validation event.",
            "metadata": {"auto_published": False},
            "recorded_at": utcnow().isoformat(),
        }],
        requested_by_user_id=admin.id,
        queued_at=utcnow(),
        started_at=utcnow(),
        completed_at=utcnow(),
    )
    db.session.add(automation_run)
    db.session.flush()
    return {
        "document": document,
        "version": version,
        "control": control,
        "extraction_run": extraction_run,
        "automation_run": automation_run,
    }


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

            admin = create_user("Insight Admin", "admin@example.com", role="admin")
            subscriber = create_user("Insight Subscriber", "subscriber@example.com")
            organization = PartnerOrganization(name="Phase 5.3 Partner", slug="phase-5-3-partner", status="active")
            db.session.add(organization)
            db.session.flush()

            safe_bundle = create_document_bundle(admin, organization, "safe")
            risky_bundle = create_document_bundle(admin, organization, "risky", risky=True)
            blocked_bundle = create_document_bundle(admin, organization, "blocked", consent=False)
            db.session.commit()

            ids = {
                "safe_run": safe_bundle["automation_run"].id,
                "safe_control": safe_bundle["control"].id,
                "risky_run": risky_bundle["automation_run"].id,
                "risky_control": risky_bundle["control"].id,
                "blocked_run": blocked_bundle["automation_run"].id,
            }

        client = app.test_client()
        protected_get_routes = [
            "/admin/intelligence-insights",
            f"/admin/intelligence-automation/runs/{ids['safe_run']}",
        ]
        for path in protected_get_routes:
            response = client.get(path, follow_redirects=False)
            assert_true(response.status_code == 302 and "/login" in response.headers.get("Location", ""), f"{path} did not require login")

        protected_post_routes = [
            f"/admin/intelligence-automation/runs/{ids['safe_run']}/generate-insight",
        ]
        for path in protected_post_routes:
            response = client.post(path, follow_redirects=False)
            assert_true(response.status_code == 302 and "/login" in response.headers.get("Location", ""), f"{path} did not require login")

        with client:
            login(client, "subscriber@example.com")
            response = client.get("/admin/intelligence-insights", follow_redirects=False)
            assert_true(response.status_code in (302, 303), "Insight queue was not admin-only")
            response = client.post(f"/admin/intelligence-automation/runs/{ids['safe_run']}/generate-insight", follow_redirects=False)
            assert_true(response.status_code in (302, 303), "Insight generation action was not admin-only")
            logout(client)

            login(client, "admin@example.com")
            response = client.post(
                f"/admin/intelligence-automation/runs/{ids['safe_run']}/generate-insight",
                follow_redirects=False,
            )
            assert_true(response.status_code in (302, 303), "Insight generation did not redirect")
            with app.app_context():
                safe_insight = IntelligenceInsight.query.filter_by(automation_run_id=ids["safe_run"]).one()
                assert_true(safe_insight.status == "generated", "Generated insight did not persist")
                assert_true(safe_insight.publishing_candidate_status == "candidate_pending_review", "Safe insight did not start as candidate pending review")
                assert_insight_is_safe(safe_insight)
                generation_audit = AuditLog.query.filter_by(action="intelligence_insight_generated", entity_id=safe_insight.id).first()
                assert_true(generation_audit is not None, "Insight generation audit missing")
                safe_insight_id = safe_insight.id

            response = client.post(
                f"/admin/intelligence-automation/runs/{ids['risky_run']}/generate-insight",
                follow_redirects=False,
            )
            assert_true(response.status_code in (302, 303), "Risk insight generation did not redirect")
            with app.app_context():
                risky_insight = IntelligenceInsight.query.filter_by(automation_run_id=ids["risky_run"]).one()
                assert_true(risky_insight.publishing_candidate_status == "blocked", "Risky insight was not blocked as a candidate")
                assert_true(risky_insight.safe_summary_json["mismatch_fields"] == ["document_reference_number"], "Risky insight did not preserve safe mismatch field names")
                assert_insight_is_safe(risky_insight)
                risky_insight_id = risky_insight.id

            response = client.post(
                f"/admin/intelligence-automation/runs/{ids['blocked_run']}/generate-insight",
                follow_redirects=False,
            )
            assert_true(response.status_code in (302, 303), "Consent-blocked insight generation did not redirect")
            with app.app_context():
                blocked_count = IntelligenceInsight.query.filter_by(automation_run_id=ids["blocked_run"]).count()
                assert_true(blocked_count == 0, "Insight generation bypassed active consent")

            response = client.get("/admin/intelligence-insights")
            assert_true(response.status_code == 200, "Insight queue did not render")
            queue_page = response.get_data(as_text=True)
            assert_true("Intelligence Insights" in queue_page, "Insight queue heading missing")
            assert_private_content_hidden(queue_page, "insight queue")

            response = client.get(f"/admin/intelligence-insights/{safe_insight_id}")
            assert_true(response.status_code == 200, "Insight detail did not render")
            detail_page = response.get_data(as_text=True)
            assert_true("Governance Flags" in detail_page, "Insight detail missing governance flags")
            assert_private_content_hidden(detail_page, "insight detail")

            response = client.post(
                f"/admin/intelligence-insights/{safe_insight_id}/review",
                data={
                    "review_action": "edit",
                    "title": "Reviewed internal insight",
                    "summary": "Reviewed safe internal summary.",
                    "review_notes": "Safe admin edit note.",
                    "publishing_candidate_status": "candidate_pending_review",
                },
                follow_redirects=False,
            )
            assert_true(response.status_code in (302, 303), "Insight edit did not redirect")
            with app.app_context():
                safe_insight = db.session.get(IntelligenceInsight, safe_insight_id)
                assert_true(safe_insight.status == "in_review", "Insight edit did not move to in_review")
                assert_true(safe_insight.title == "Reviewed internal insight", "Insight title edit did not persist")
                assert_true(AuditLog.query.filter_by(action="intelligence_insight_updated", entity_id=safe_insight_id).first() is not None, "Insight edit audit missing")
                assert_insight_is_safe(safe_insight)

            response = client.post(
                f"/admin/intelligence-insights/{safe_insight_id}/review",
                data={
                    "review_action": "approve",
                    "title": "Reviewed internal insight",
                    "summary": "Approved safe internal summary.",
                    "review_notes": "Approved for internal candidate tracking only.",
                    "publishing_candidate_status": "approved_candidate",
                },
                follow_redirects=False,
            )
            assert_true(response.status_code in (302, 303), "Insight approve did not redirect")
            with app.app_context():
                safe_insight = db.session.get(IntelligenceInsight, safe_insight_id)
                assert_true(safe_insight.status == "approved", "Insight approve did not persist")
                assert_true(safe_insight.publishing_candidate_status == "approved_candidate", "Approved safe insight did not retain approved candidate status")
                assert_true(AuditLog.query.filter_by(action="intelligence_insight_approved", entity_id=safe_insight_id).first() is not None, "Insight approve audit missing")
                assert_insight_is_safe(safe_insight)

            response = client.post(
                f"/admin/intelligence-insights/{risky_insight_id}/review",
                data={
                    "review_action": "reject",
                    "title": "Rejected internal insight",
                    "summary": "Rejected due to safe summarized risk flags.",
                    "review_notes": "Rejected for internal review.",
                    "publishing_candidate_status": "approved_candidate",
                },
                follow_redirects=False,
            )
            assert_true(response.status_code in (302, 303), "Insight reject did not redirect")
            with app.app_context():
                risky_insight = db.session.get(IntelligenceInsight, risky_insight_id)
                assert_true(risky_insight.status == "rejected", "Insight reject did not persist")
                assert_true(risky_insight.publishing_candidate_status == "blocked", "Rejected insight was not blocked")
                assert_true(AuditLog.query.filter_by(action="intelligence_insight_rejected", entity_id=risky_insight_id).first() is not None, "Insight reject audit missing")
                assert_insight_is_safe(risky_insight)

            response = client.post(
                f"/admin/intelligence-insights/{risky_insight_id}/review",
                data={
                    "review_action": "archive",
                    "title": "Archived internal insight",
                    "summary": "Archived safe internal summary.",
                    "review_notes": "Archived after rejection.",
                    "publishing_candidate_status": "blocked",
                },
                follow_redirects=False,
            )
            assert_true(response.status_code in (302, 303), "Insight archive did not redirect")
            with app.app_context():
                risky_insight = db.session.get(IntelligenceInsight, risky_insight_id)
                assert_true(risky_insight.status == "archived", "Insight archive did not persist")
                assert_true(risky_insight.archived_at is not None, "Insight archived_at missing")
                assert_true(AuditLog.query.filter_by(action="intelligence_insight_archived", entity_id=risky_insight_id).first() is not None, "Insight archive audit missing")

            response = client.get(f"/admin/intelligence-automation/runs/{ids['safe_run']}")
            assert_true(response.status_code == 200, "Automation run detail did not render")
            run_page = response.get_data(as_text=True)
            assert_true("Generated Insights" in run_page, "Automation run detail missing generated insight section")
            assert_true(f"/admin/intelligence-insights/{safe_insight_id}" in run_page, "Automation run detail missing insight link")
            assert_private_content_hidden(run_page, "automation run detail")

            response = client.get(f"/admin/intelligence-insights/{safe_insight_id}")
            assert_private_content_hidden(response.get_data(as_text=True), "approved insight detail")
            response = client.post(
                f"/admin/intelligence-insights/{safe_insight_id}/review",
                data={"review_action": "unsupported"},
                follow_redirects=False,
            )
            assert_true(response.status_code in (302, 303), "Unsupported review action did not redirect safely")

        with app.app_context():
            for insight in IntelligenceInsight.query.all():
                assert_insight_is_safe(insight)
            assert_true(db.session.get(DocumentPublishControl, ids["safe_control"]).status == "blocked", "Insight approval changed publish readiness")
            assert_true(db.session.get(DocumentPublishControl, ids["risky_control"]).status == "blocked", "Risk insight changed publish readiness")
            assert_true(DocumentPublishControl.query.filter(DocumentPublishControl.status != "blocked").count() == 0, "Insight workflow auto-published a document target")

        print("Phase 5.3 intelligence insight generation and review validation passed.")
    finally:
        shutil.rmtree(PRIVATE_UPLOAD_ROOT, ignore_errors=True)


if __name__ == "__main__":
    run_validation()
