"""Validate Phase 3.2 admin document review and approval behavior.

This script uses an in-memory SQLite database and Flask's test client so it
does not touch Replit PostgreSQL data or real private document storage.
"""

import io
import os
import shutil
import sys
import tempfile
from pathlib import Path

PRIVATE_UPLOAD_ROOT = tempfile.mkdtemp(prefix="fieldsight-phase-3-2-docs-")

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SESSION_SECRET", "phase-3-2-validation-secret")
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
    ActorDocument,
    AuditLog,
    Commodity,
    Crop,
    DocumentAccessLog,
    DocumentExtractionRun,
    DocumentFieldReconciliation,
    DocumentReview,
    DocumentType,
    MarketActor,
    PartnerOrganization,
    PartnerUserProfile,
    User,
)


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


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


def document_form_data(document_type_id, crop_id, commodity_id):
    return {
        "document_type_id": str(document_type_id),
        "title": "Admin Review Certificate of Origin",
        "description": "Phase 3.2 validation document",
        "document_reference_number": "COO-CURRENT-001",
        "issuing_body": "Legacy Issuing Body",
        "issued_at": "2026-01-01",
        "expires_at": "2026-06-01",
        "linked_crop_id": str(crop_id),
        "linked_commodity_id": str(commodity_id),
        "subscriber_access_level": "metadata_only",
    }


def extraction_fixture_content():
    return "\n".join([
        "document_reference_number: COO-EXTRACTED-999",
        "issuing_body: Nigerian Export Promotion Council",
        "issued_at: 2026-02-01",
        "expires_at: 2026-08-01",
        "exporter_name: Admin Review Exporter Ltd",
        "consignee_name: London Buyer Ltd",
        "origin_country: Nigeria",
        "destination_country: United Kingdom",
        "crop_or_commodity: Ginger",
        "quantity: 20 MT",
        "port_of_exit: Lagos",
        "certificate_type: Certificate of Origin",
    ]).encode("utf-8")


def upload_document(client, actor_id, document_type_id, crop_id, commodity_id):
    data = document_form_data(document_type_id, crop_id, commodity_id)
    data["file"] = (io.BytesIO(extraction_fixture_content()), "admin-review-certificate.csv")
    return client.post(
        f"/partner/actors/{actor_id}/documents/new",
        data=data,
        content_type="multipart/form-data",
        follow_redirects=False,
    )


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

            org = PartnerOrganization(name="Admin Review Partner", slug="admin-review-partner", status="active")
            db.session.add(org)
            db.session.flush()

            admin = create_user("Admin Reviewer", "admin@example.com", role="admin")
            partner_editor = create_user("Partner Editor", "partner@example.com")
            ordinary = create_user("Ordinary Subscriber", "ordinary@example.com")
            link_partner_user(partner_editor, org, "data_editor")

            crop = Crop.query.filter_by(code="ginger").one()
            commodity = Commodity(crop_id=crop.id, code="phase_3_2_ginger", name="Phase 3.2 Ginger", category="Ginger", active=True)
            db.session.add(commodity)
            db.session.flush()

            actor = MarketActor(
                partner_organization_id=org.id,
                created_by_user_id=partner_editor.id,
                updated_by_id=partner_editor.id,
                actor_type="exporter",
                name="Admin Review Exporter",
                crop_id=crop.id,
                commodity_id=commodity.id,
                status="active",
            )
            db.session.add(actor)
            db.session.commit()

            actor_id = actor.id
            crop_id = crop.id
            commodity_id = commodity.id
            document_type_id = DocumentType.query.filter_by(name="Certificate of Origin").one().id

        client = app.test_client()

        with client:
            login(client, "partner@example.com")
            response = upload_document(client, actor_id, document_type_id, crop_id, commodity_id)
            assert_true(response.status_code in (302, 303), "Partner document upload did not redirect")

            with app.app_context():
                document = ActorDocument.query.filter_by(title="Admin Review Certificate of Origin").one()
                document_id = document.id
                assert_true(document.subscriber_access_level == "hidden", "Document without active consent was not forced hidden")
                assert_true(str(PRIVATE_UPLOAD_ROOT) in document.storage_path, "Document was not stored under validation private root")

            response = client.post(f"/partner/documents/{document_id}/extract", follow_redirects=False)
            assert_true(response.status_code in (302, 303), "Partner extraction did not redirect")
            logout(client)

            login(client, "ordinary@example.com")
            response = client.get("/admin/documents/review-queue", follow_redirects=False)
            assert_true(response.status_code in (302, 303) and "/login" in response.headers.get("Location", ""), "Ordinary subscriber accessed admin review queue")
            logout(client)

            login(client, "partner@example.com")
            response = client.get("/admin/documents/review-queue", follow_redirects=False)
            assert_true(response.status_code in (302, 303) and "/login" in response.headers.get("Location", ""), "Partner user accessed admin review queue")
            logout(client)

            login(client, "admin@example.com")
            response = client.get("/admin/documents/review-queue")
            queue_body = response.get_data(as_text=True)
            assert_true(response.status_code == 200, "Admin could not access document review queue")
            assert_true("Admin Review Certificate of Origin" in queue_body, "Queue did not show submitted partner document")
            assert_true("Admin Review Exporter" in queue_body, "Queue did not show actor name")

            response = client.get(f"/admin/documents/{document_id}/review")
            detail_body = response.get_data(as_text=True)
            assert_true(response.status_code == 200, "Admin could not open document review detail")
            assert_true("Admin Review Exporter" in detail_body, "Review detail did not show actor")
            assert_true("Admin Review Partner" in detail_body, "Review detail did not show partner organization")
            assert_true("No active actor consent is recorded" in detail_body, "Review detail did not show missing consent warning")
            assert_true("Extraction And Risk" in detail_body, "Review detail did not show extraction context")
            assert_true("Metadata Mismatch" in detail_body, "Review detail did not show risk flags")
            assert_true("Reconciliation Summary" in detail_body, "Review detail did not show reconciliation rows")
            assert_true("Sensitive Type" in detail_body, "Review detail did not show sensitive document flag")
            assert_true(str(PRIVATE_UPLOAD_ROOT) not in detail_body, "Review detail exposed private upload root")

            response = client.get(f"/admin/documents/{document_id}/preview")
            assert_true(response.status_code == 200, "Admin preview route did not return file content")
            assert_true("inline" in response.headers.get("Content-Disposition", ""), "Admin preview did not use inline disposition")
            assert_true("no-store" in response.headers.get("Cache-Control", ""), "Admin preview did not use no-store cache control")
            assert_true(str(PRIVATE_UPLOAD_ROOT) not in response.get_data(as_text=True), "Admin preview exposed private upload root")

            response = client.post(
                f"/admin/documents/{document_id}/review/decision",
                data={"action": "approve", "review_notes": "Approved for internal verification."},
                follow_redirects=False,
            )
            assert_true(response.status_code in (302, 303), "Approve decision did not redirect")
            with app.app_context():
                document = db.session.get(ActorDocument, document_id)
                assert_true(document.review_status == "approved", "Approve did not set review status")
                assert_true(document.document_status == "approved", "Approve did not set document status")
                assert_true(document.subscriber_access_level == "hidden", "Approve changed subscriber access")
                assert_true(document.visibility_level == "hidden", "Approve changed external visibility")
                assert_true(AuditLog.query.filter_by(action="admin_document_review_approved").first() is not None, "Approve audit log was not written")
                assert_true(DocumentReview.query.filter_by(actor_document_id=document_id, status="approved").first() is not None, "Approve review history was not written")

            response = client.post(
                f"/admin/documents/{document_id}/review/decision",
                data={"action": "request_correction", "correction_reason": "Please upload a clearer certificate scan."},
                follow_redirects=False,
            )
            assert_true(response.status_code in (302, 303), "Request correction decision did not redirect")
            with app.app_context():
                document = db.session.get(ActorDocument, document_id)
                assert_true(document.review_status == "needs_correction", "Correction request did not set review status")
                assert_true("clearer certificate" in (document.review_comments or ""), "Correction reason was not stored")
                assert_true(AuditLog.query.filter_by(action="admin_document_correction_requested").first() is not None, "Correction audit log was not written")

            response = client.post(
                f"/admin/documents/{document_id}/review/decision",
                data={"action": "reject", "rejection_reason": "Certificate number is not acceptable."},
                follow_redirects=False,
            )
            assert_true(response.status_code in (302, 303), "Reject decision did not redirect")
            with app.app_context():
                document = db.session.get(ActorDocument, document_id)
                assert_true(document.review_status == "rejected", "Reject did not set review status")
                assert_true(document.verification_status == "rejected", "Reject did not set verification status")
                assert_true("not acceptable" in (document.review_comments or ""), "Rejection reason was not stored")
                assert_true(AuditLog.query.filter_by(action="admin_document_review_rejected").first() is not None, "Reject audit log was not written")

            response = client.post(
                f"/admin/documents/{document_id}/review/decision",
                data={"action": "require_redaction", "review_notes": "Contains personal identifiers."},
                follow_redirects=False,
            )
            assert_true(response.status_code in (302, 303), "Require redaction decision did not redirect")
            with app.app_context():
                document = db.session.get(ActorDocument, document_id)
                assert_true(document.review_status == "redaction_required", "Redaction action did not set review status")
                assert_true(document.redaction_status == "redaction_required", "Redaction action did not set redaction status")
                assert_true(AuditLog.query.filter_by(action="admin_document_redaction_required").first() is not None, "Redaction audit log was not written")

            response = client.post(
                f"/admin/documents/{document_id}/review/decision",
                data={"action": "mark_verified", "review_notes": "Verified after admin review."},
                follow_redirects=False,
            )
            assert_true(response.status_code in (302, 303), "Mark verified decision did not redirect")
            response = client.post(
                f"/admin/documents/{document_id}/review/decision",
                data={"action": "mark_unverified", "review_notes": "Returned to unverified for follow-up."},
                follow_redirects=False,
            )
            assert_true(response.status_code in (302, 303), "Mark unverified decision did not redirect")

            with app.app_context():
                document = db.session.get(ActorDocument, document_id)
                assert_true(document.verification_status == "unverified", "Mark unverified did not set verification status")
                assert_true(AuditLog.query.filter_by(action="admin_document_verification_updated").count() >= 2, "Verification audit logs were not written")
                assert_true(DocumentAccessLog.query.filter_by(actor_document_id=document_id, access_type="admin_preview").first() is not None, "Admin preview access log was not written")
                assert_true(DocumentAccessLog.query.filter_by(actor_document_id=document_id, access_type="admin_review_detail").first() is not None, "Admin review detail access log was not written")
                assert_true(DocumentExtractionRun.query.filter_by(actor_document_id=document_id).first() is not None, "Extraction run missing after admin validation")
                assert_true(DocumentFieldReconciliation.query.filter_by(actor_document_id=document_id).count() > 0, "Reconciliation rows missing after admin validation")

        print("Phase 3.2 admin document review validation passed.")
    finally:
        shutil.rmtree(PRIVATE_UPLOAD_ROOT, ignore_errors=True)


if __name__ == "__main__":
    run_validation()
