"""Validate Phase 3.3 redaction and publish-readiness controls.

This script uses an in-memory SQLite database and Flask's test client so it
does not touch Replit PostgreSQL data or real private document storage.
"""

import compileall
import io
import os
import shutil
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

PRIVATE_UPLOAD_ROOT = tempfile.mkdtemp(prefix="fieldsight-phase-3-3-docs-")

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SESSION_SECRET", "phase-3-3-validation-secret")
os.environ["PRIVATE_UPLOAD_ROOT"] = PRIVATE_UPLOAD_ROOT
os.environ.setdefault("DOCUMENT_STORAGE_BACKEND", "local_private")
os.environ["MAX_DOCUMENT_UPLOAD_MB"] = "1"

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
    AuditLog,
    Commodity,
    Crop,
    DocumentExtractionRun,
    DocumentFieldReconciliation,
    DocumentPublishControl,
    DocumentType,
    MarketActor,
    PartnerOrganization,
    PartnerUserProfile,
    User,
    consent_document_category_for_document_type,
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


def link_partner_user(user, organization, role):
    profile = PartnerUserProfile(
        user_id=user.id,
        partner_organization_id=organization.id,
        partner_role=role,
        status="active",
    )
    db.session.add(profile)
    db.session.flush()
    return profile


def login(client, email, password="validation-password"):
    response = client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )
    assert_true(response.status_code in (302, 303), f"Login failed for {email}")


def logout(client):
    client.get("/logout", follow_redirects=False)


def create_active_consent(actor, organization, user, document_category):
    now = utcnow()
    consent = ActorConsentRecord(
        market_actor_id=actor.id,
        partner_organization_id=organization.id,
        consent_status="granted",
        consent_method="written",
        consent_reference="CONSENT-PHASE-3-3",
        consent_scope_json=[
            "store_actor_documents",
            "share_document_metadata_with_subscribers",
            "share_redacted_documents_with_subscribers",
            "share_full_documents_with_approved_users",
            "include_in_paid_data_packs",
            "include_in_live_intelligence",
            "include_in_api_responses",
            "use_documents_for_extraction_quality",
        ],
        permitted_data_categories_json=["identity_profile", "certification_metadata"],
        permitted_document_categories_json=[document_category],
        sharing_channels_json=[
            "internal_review",
            "partner_portal",
            "admin_review",
            "licensed_data_pack",
            "live_intelligence",
            "subscriber_portal",
            "api",
            "approved_buyer_due_diligence",
        ],
        granted_by_name="Phase 3.3 Actor",
        granted_at=now,
        expires_at=now + timedelta(days=365),
        captured_by_user_id=user.id,
        active=True,
    )
    db.session.add(consent)
    db.session.flush()
    return consent


def create_refused_consent(actor, organization, user):
    consent = ActorConsentRecord(
        market_actor_id=actor.id,
        partner_organization_id=organization.id,
        consent_status="refused",
        consent_method="written",
        consent_reference="CONSENT-PHASE-3-3-REFUSED",
        granted_by_name="Phase 3.3 Actor",
        captured_by_user_id=user.id,
        active=True,
    )
    db.session.add(consent)
    db.session.flush()
    return consent


def future_date(days=365):
    return (utcnow().date() + timedelta(days=days)).isoformat()


def document_form_data(document_type_id, crop_id, commodity_id, expires_at):
    return {
        "document_type_id": str(document_type_id),
        "title": "Phase 3.3 Certificate of Origin",
        "description": "Phase 3.3 redaction and publish-control validation document",
        "document_reference_number": "COO-READY-001",
        "issuing_body": "Nigerian Export Promotion Council",
        "issued_at": utcnow().date().isoformat(),
        "expires_at": expires_at,
        "linked_crop_id": str(crop_id),
        "linked_commodity_id": str(commodity_id),
        "subscriber_access_level": "metadata_only",
    }


def extraction_fixture_content(expires_at):
    return "\n".join([
        "document_reference_number: COO-READY-001",
        "issuing_body: Nigerian Export Promotion Council",
        f"issued_at: {utcnow().date().isoformat()}",
        f"expires_at: {expires_at}",
        "exporter_name: Phase 3.3 Exporter Ltd",
        "consignee_name: London Buyer Ltd",
        "origin_country: Nigeria",
        "destination_country: United Kingdom",
        "crop_or_commodity: Ginger",
        "quantity: 20 MT",
        "port_of_exit: Lagos",
        "certificate_type: Certificate of Origin",
    ]).encode("utf-8")


def upload_document(client, actor_id, document_type_id, crop_id, commodity_id, expires_at):
    data = document_form_data(document_type_id, crop_id, commodity_id, expires_at)
    data["file"] = (io.BytesIO(extraction_fixture_content(expires_at)), "phase-3-3-certificate.csv")
    return client.post(
        f"/partner/actors/{actor_id}/documents/new",
        data=data,
        content_type="multipart/form-data",
        follow_redirects=False,
    )


def accept_all_reconciliation_rows(document_id, reviewer_id):
    run = DocumentExtractionRun.query.filter_by(actor_document_id=document_id).one()
    rows = DocumentFieldReconciliation.query.filter_by(extraction_run_id=run.id).all()
    now = utcnow()
    for row in rows:
        row.status = "accepted"
        row.accepted_value = row.extracted_value or row.current_value
        row.reviewed_by_user_id = reviewer_id
        row.reviewed_at = now
        row.decision_history_json = [{
            "action": "accepted",
            "accepted_value": row.accepted_value,
            "notes": "Phase 3.3 validation reconciliation.",
            "reviewed_by_user_id": reviewer_id,
            "reviewed_at": now.isoformat(),
        }]
    run.status = "completed"
    run.document_intelligence_status = "reconciled"
    run.risk_flags_json = []
    run.metadata_mismatches_json = []
    run.expiry_renewal_json = {"status": "current", "expires_at": None, "days_until_expiry": 365}
    db.session.flush()
    return run


def latest_control(document_id, target):
    return DocumentPublishControl.query.filter_by(
        actor_document_id=document_id,
        publish_target=target,
    ).one()


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

            org = PartnerOrganization(name="Publish Controls Partner", slug="publish-controls-partner", status="active")
            db.session.add(org)
            db.session.flush()

            admin = create_user("Admin Publisher", "admin@example.com", role="admin")
            partner_editor = create_user("Partner Editor", "partner@example.com")
            ordinary = create_user("Ordinary Subscriber", "ordinary@example.com")
            link_partner_user(partner_editor, org, "data_editor")

            crop = Crop.query.filter_by(code="ginger").one()
            commodity = Commodity(crop_id=crop.id, code="phase_3_3_ginger", name="Phase 3.3 Ginger", category="Ginger", active=True)
            db.session.add(commodity)
            db.session.flush()

            actor = MarketActor(
                partner_organization_id=org.id,
                created_by_user_id=partner_editor.id,
                updated_by_id=partner_editor.id,
                actor_type="exporter",
                name="Phase 3.3 Exporter",
                crop_id=crop.id,
                commodity_id=commodity.id,
                status="active",
            )
            db.session.add(actor)
            db.session.flush()

            document_type = DocumentType.query.filter_by(name="Certificate of Origin").one()
            document_category = consent_document_category_for_document_type(document_type)
            create_active_consent(actor, org, partner_editor, document_category)
            db.session.commit()

            actor_id = actor.id
            crop_id = crop.id
            commodity_id = commodity.id
            document_type_id = document_type.id
            partner_editor_id = partner_editor.id
            expires_at = future_date()

        client = app.test_client()

        with client:
            login(client, "partner@example.com")
            response = upload_document(client, actor_id, document_type_id, crop_id, commodity_id, expires_at)
            assert_true(response.status_code in (302, 303), "Partner document upload did not redirect")

            with app.app_context():
                document = ActorDocument.query.filter_by(title="Phase 3.3 Certificate of Origin").one()
                document_id = document.id
                assert_true(document.subscriber_access_level == "metadata_only", "Active consent did not preserve metadata-level upload")
                assert_true(str(PRIVATE_UPLOAD_ROOT) in document.storage_path, "Document was not stored under validation private root")

            response = client.post(f"/partner/documents/{document_id}/extract", follow_redirects=False)
            assert_true(response.status_code in (302, 303), "Partner extraction did not redirect")
            logout(client)

            login(client, "ordinary@example.com")
            response = client.get(f"/admin/documents/{document_id}/redaction", follow_redirects=False)
            assert_true(response.status_code in (302, 303) and "/login" in response.headers.get("Location", ""), "Ordinary subscriber accessed redaction controls")
            response = client.get(f"/admin/documents/{document_id}/publish-controls", follow_redirects=False)
            assert_true(response.status_code in (302, 303) and "/login" in response.headers.get("Location", ""), "Ordinary subscriber accessed publish controls")
            response = client.get(f"/api/documents/{document_id}", follow_redirects=False)
            assert_true(response.status_code == 404, "Unexpected API document route exists")
            response = client.get(f"/documents/{document_id}/download", follow_redirects=False)
            assert_true(response.status_code == 404, "Unexpected public document download route exists")
            logout(client)

            login(client, "partner@example.com")
            response = client.get(f"/admin/documents/{document_id}/publish-controls", follow_redirects=False)
            assert_true(response.status_code in (302, 303) and "/login" in response.headers.get("Location", ""), "Partner user accessed admin publish controls")
            logout(client)

            login(client, "admin@example.com")
            response = client.get(f"/admin/documents/{document_id}/redaction")
            assert_true(response.status_code == 200, "Admin could not access redaction controls")
            assert_true("Redaction Controls" in response.get_data(as_text=True), "Redaction page did not render")

            response = client.get(f"/admin/documents/{document_id}/publish-controls")
            publish_body = response.get_data(as_text=True)
            assert_true(response.status_code == 200, "Admin could not access publish controls")
            assert_true("Verified Metadata" in publish_body, "Publish controls did not show verified metadata target")
            assert_true("API Metadata" in publish_body, "Publish controls did not show API metadata target")
            assert_true(str(PRIVATE_UPLOAD_ROOT) not in publish_body, "Publish controls exposed private upload root")

            response = client.post(
                f"/admin/documents/{document_id}/publish-controls/decision",
                data={
                    "publish_target": "subscriber_portal_metadata",
                    "decision": "mark_ready",
                    "decision_notes": "Trying before admin approval should stay blocked.",
                },
                follow_redirects=False,
            )
            assert_true(response.status_code in (302, 303), "Blocked publish decision did not redirect")
            with app.app_context():
                control = latest_control(document_id, "subscriber_portal_metadata")
                assert_true(control.status == "blocked", "Publish control did not block before approval")
                assert_true(control.blocking_reasons_json, "Blocked publish control did not store reasons")
                assert_true(AuditLog.query.filter_by(action="admin_document_publish_readiness_decision").first() is not None, "Publish decision audit log missing")

            response = client.post(
                f"/admin/documents/{document_id}/redaction",
                data={"redaction_status": "required", "redaction_notes": "PII check required before candidates."},
                follow_redirects=False,
            )
            assert_true(response.status_code in (302, 303), "Redaction required update did not redirect")
            with app.app_context():
                document = db.session.get(ActorDocument, document_id)
                assert_true(document.redaction_status == "required", "Redaction status did not update to required")
                assert_true(AuditLog.query.filter_by(action="admin_document_redaction_updated").first() is not None, "Redaction audit log was not written")

            with app.app_context():
                accept_all_reconciliation_rows(document_id, partner_editor_id)
                db.session.commit()

            response = client.post(
                f"/admin/documents/{document_id}/review/decision",
                data={
                    "action": "approve",
                    "verification_status": "verified",
                    "review_notes": "Approved and verified for Phase 3.3 readiness validation.",
                },
                follow_redirects=False,
            )
            assert_true(response.status_code in (302, 303), "Admin approval did not redirect")

            response = client.post(
                f"/admin/documents/{document_id}/redaction",
                data={"redaction_status": "completed", "redaction_notes": "Redaction completed for controlled readiness validation."},
                follow_redirects=False,
            )
            assert_true(response.status_code in (302, 303), "Redaction completed update did not redirect")

            response = client.post(f"/admin/documents/{document_id}/publish-controls/evaluate", follow_redirects=False)
            assert_true(response.status_code in (302, 303), "Evaluate all publish targets did not redirect")
            with app.app_context():
                ready_control = latest_control(document_id, "subscriber_portal_metadata")
                redacted_candidate = latest_control(document_id, "redacted_document_candidate")
                assert_true(ready_control.status == "ready", "Subscriber metadata target was not ready after all gates passed")
                assert_true(redacted_candidate.status == "ready", "Redacted document candidate was not ready after redaction/file gates passed")
                assert_true(DocumentPublishControl.query.filter_by(actor_document_id=document_id).count() == 7, "All publish targets were not persisted")
                assert_true(AuditLog.query.filter_by(action="admin_document_publish_readiness_evaluated").first() is not None, "Evaluate-all audit log was not written")

            response = client.post(
                f"/admin/documents/{document_id}/publish-controls/decision",
                data={
                    "publish_target": "subscriber_portal_metadata",
                    "decision": "mark_ready",
                    "decision_notes": "All checks passed.",
                },
                follow_redirects=False,
            )
            assert_true(response.status_code in (302, 303), "Ready publish decision did not redirect")
            with app.app_context():
                control = latest_control(document_id, "subscriber_portal_metadata")
                assert_true(control.status == "ready", "Publish target was not marked ready")
                assert_true(not control.blocking_reasons_json, "Ready publish target retained blocking reasons")

            with app.app_context():
                extraction_run = DocumentExtractionRun.query.filter_by(actor_document_id=document_id).one()
                extraction_run.risk_flags_json = ["metadata_mismatch"]
                db.session.commit()

            response = client.post(
                f"/admin/documents/{document_id}/publish-controls/decision",
                data={
                    "publish_target": "api_metadata",
                    "decision": "mark_ready",
                    "decision_notes": "High-risk flags should block readiness.",
                },
                follow_redirects=False,
            )
            assert_true(response.status_code in (302, 303), "High-risk block decision did not redirect")
            with app.app_context():
                control = latest_control(document_id, "api_metadata")
                assert_true(control.status == "blocked", "High-risk target was not blocked")
                assert_true(any("high-risk" in reason for reason in control.blocking_reasons_json), "High-risk blocker was not stored")

            response = client.post(
                f"/admin/documents/{document_id}/publish-controls/decision",
                data={
                    "publish_target": "api_metadata",
                    "decision": "waive_high_risk_flags",
                    "decision_notes": "Admin waiver recorded for validation only.",
                },
                follow_redirects=False,
            )
            assert_true(response.status_code in (302, 303), "High-risk waiver decision did not redirect")
            with app.app_context():
                control = latest_control(document_id, "api_metadata")
                assert_true(control.status == "waived", "High-risk-only blocker was not waivable")

            with app.app_context():
                document = db.session.get(ActorDocument, document_id)
                create_refused_consent(document.market_actor, document.partner_organization, db.session.get(User, partner_editor_id))
                db.session.commit()

            response = client.post(
                f"/admin/documents/{document_id}/publish-controls/decision",
                data={
                    "publish_target": "licensed_data_pack_metadata",
                    "decision": "mark_ready",
                    "decision_notes": "Later refused consent should block readiness.",
                },
                follow_redirects=False,
            )
            assert_true(response.status_code in (302, 303), "Consent-blocked publish decision did not redirect")
            with app.app_context():
                control = latest_control(document_id, "licensed_data_pack_metadata")
                assert_true(control.status == "blocked", "Later refused consent did not block publish readiness")
                assert_true(any("consent" in reason.lower() for reason in control.blocking_reasons_json), "Consent blocker was not stored")

        assert_true(compileall.compile_file(str(REPO_ROOT / "app.py"), quiet=1), "app.py did not compile")
        assert_true(compileall.compile_file(str(REPO_ROOT / "models.py"), quiet=1), "models.py did not compile")
        assert_true(compileall.compile_dir(str(REPO_ROOT / "routes"), quiet=1), "routes package did not compile")
        assert_true(compileall.compile_dir(str(REPO_ROOT / "scripts"), quiet=1), "scripts package did not compile")

        print("Phase 3.3 redaction and publish controls validation passed.")
    finally:
        shutil.rmtree(PRIVATE_UPLOAD_ROOT, ignore_errors=True)


if __name__ == "__main__":
    run_validation()
