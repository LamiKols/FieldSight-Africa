"""Validate Phase 3.1 document preview, extraction, and reconciliation behavior.

This script uses an in-memory SQLite database and Flask's test client so it
does not touch Replit PostgreSQL data or real private document storage.
"""

import io
import os
import shutil
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

PRIVATE_UPLOAD_ROOT = tempfile.mkdtemp(prefix="fieldsight-phase-3-1-docs-")

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SESSION_SECRET", "phase-3-1-validation-secret")
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
    DocumentAccessLog,
    DocumentExtractionRun,
    DocumentFieldReconciliation,
    DocumentType,
    MarketActor,
    PartnerOrganization,
    PartnerUserProfile,
    User,
    actor_can_share_documents,
    consent_document_category_for_document_type,
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
        "title": "Validation Certificate of Origin",
        "description": "Phase 3.1 validation document",
        "document_reference_number": "COO-CURRENT-001",
        "issuing_body": "Legacy Issuing Body",
        "issued_at": "2026-01-01",
        "expires_at": "2026-06-01",
        "linked_crop_id": str(crop_id),
        "linked_commodity_id": str(commodity_id),
        "subscriber_access_level": "metadata_only",
    }


def upload_document(client, actor_id, document_type_id, crop_id, commodity_id, content):
    data = document_form_data(document_type_id, crop_id, commodity_id)
    data["file"] = (io.BytesIO(content), "certificate-of-origin.csv")
    return client.post(
        f"/partner/actors/{actor_id}/documents/new",
        data=data,
        content_type="multipart/form-data",
        follow_redirects=False,
    )


def extraction_fixture_content():
    return "\n".join([
        "document_reference_number: COO-EXTRACTED-999",
        "issuing_body: Nigerian Export Promotion Council",
        "issued_at: 2026-02-01",
        "expires_at: 2026-08-01",
        "exporter_name: Validation Exporter Ltd",
        "consignee_name: London Buyer Ltd",
        "origin_country: Nigeria",
        "destination_country: United Kingdom",
        "crop_or_commodity: Ginger",
        "quantity: 20 MT",
        "port_of_exit: Lagos",
        "certificate_type: Certificate of Origin",
    ]).encode("utf-8")


def create_active_consent(actor, organization, user, document_category):
    now = datetime.now(UTC).replace(tzinfo=None)
    consent = ActorConsentRecord(
        market_actor_id=actor.id,
        partner_organization_id=organization.id,
        consent_status="granted",
        consent_method="written",
        consent_reference="CONSENT-PHASE-3-1",
        consent_scope_json=[
            "store_actor_documents",
            "use_documents_for_extraction_quality",
            "share_document_metadata_with_subscribers",
        ],
        permitted_data_categories_json=["identity_profile", "certification_metadata"],
        permitted_document_categories_json=[document_category],
        sharing_channels_json=["internal_review", "partner_portal", "subscriber_portal"],
        granted_by_name="Validation Actor",
        granted_at=now,
        expires_at=now + timedelta(days=365),
        captured_by_user_id=user.id,
        active=True,
    )
    db.session.add(consent)
    db.session.flush()
    return consent


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

            org = PartnerOrganization(name="Preview Partner", slug="preview-partner", status="active")
            other_org = PartnerOrganization(name="Other Preview Partner", slug="other-preview-partner", status="active")
            db.session.add_all([org, other_org])
            db.session.flush()

            editor = create_user("Data Editor", "editor@example.com")
            viewer = create_user("Partner Viewer", "viewer@example.com")
            ordinary = create_user("Ordinary Subscriber", "ordinary@example.com")
            other_editor = create_user("Other Editor", "other-editor@example.com")

            link_partner_user(editor, org, "data_editor")
            link_partner_user(viewer, org, "partner_viewer")
            link_partner_user(other_editor, other_org, "data_editor")

            crop = Crop.query.filter_by(code="ginger").one()
            commodity = Commodity(crop_id=crop.id, code="phase_3_1_ginger", name="Phase 3.1 Ginger", category="Ginger", active=True)
            db.session.add(commodity)
            db.session.flush()

            actor = MarketActor(
                partner_organization_id=org.id,
                created_by_user_id=editor.id,
                updated_by_id=editor.id,
                actor_type="exporter",
                name="Phase 3.1 Exporter",
                crop_id=crop.id,
                commodity_id=commodity.id,
                status="active",
            )
            other_actor = MarketActor(
                partner_organization_id=other_org.id,
                created_by_user_id=other_editor.id,
                updated_by_id=other_editor.id,
                actor_type="exporter",
                name="Other Phase 3.1 Exporter",
                status="active",
            )
            db.session.add_all([actor, other_actor])
            db.session.flush()

            document_type = DocumentType.query.filter_by(name="Certificate of Origin").one()
            document_category = consent_document_category_for_document_type(document_type)
            create_active_consent(actor, org, editor, document_category)
            db.session.commit()

            actor_id = actor.id
            crop_id = crop.id
            commodity_id = commodity.id
            document_type_id = document_type.id

        client = app.test_client()

        with client:
            login(client, "editor@example.com")
            response = upload_document(
                client,
                actor_id,
                document_type_id,
                crop_id,
                commodity_id,
                extraction_fixture_content(),
            )
            assert_true(response.status_code in (302, 303), "Editor upload did not redirect after success")

            with app.app_context():
                document = ActorDocument.query.filter_by(title="Validation Certificate of Origin").one()
                document_id = document.id
                assert_true(document.document_reference_number == "COO-CURRENT-001", "Initial reference number was not stored")
                assert_true(actor_can_share_documents(document.market_actor, "subscriber_portal", document_category), "Consent helper did not allow subscriber document sharing")
                assert_true(str(PRIVATE_UPLOAD_ROOT) in document.storage_path, "Document was not stored under the validation private root")

            response = client.get(f"/partner/documents/{document_id}/preview")
            preview_body = response.get_data(as_text=True)
            assert_true(response.status_code == 200, "Partner editor could not preview own document")
            assert_true("inline" in response.headers.get("Content-Disposition", ""), "Preview did not use inline content disposition")
            assert_true(str(PRIVATE_UPLOAD_ROOT) not in preview_body, "Preview response exposed the private upload root")
            assert_true(response.headers.get("X-FieldSight-External-Shareable") == "true", "Preview did not evaluate consent shareability")

            detail_response = client.get(f"/partner/documents/{document_id}")
            detail_body = detail_response.get_data(as_text=True)
            assert_true(detail_response.status_code == 200 and "Document Preview" in detail_body, "Document detail did not include preview panel")
            assert_true("Document Intelligence" in detail_body, "Document detail did not include intelligence panel")
            logout(client)

            login(client, "ordinary@example.com")
            response = client.get(f"/partner/documents/{document_id}/preview", follow_redirects=False)
            assert_true(response.status_code in (302, 303), "Ordinary subscriber was not denied preview")
            logout(client)

            login(client, "other-editor@example.com")
            response = client.get(f"/partner/documents/{document_id}/preview", follow_redirects=False)
            assert_true(response.status_code == 404, "Cross-organization partner could preview the document")
            logout(client)

            login(client, "viewer@example.com")
            response = client.post(f"/partner/documents/{document_id}/extract", follow_redirects=False)
            assert_true(response.status_code in (302, 303), "Partner viewer was not denied extraction")
            response = client.get(f"/partner/documents/{document_id}/reconcile", follow_redirects=False)
            assert_true(response.status_code in (302, 303), "Partner viewer was not denied reconciliation")
            logout(client)

            login(client, "editor@example.com")
            response = client.post(f"/partner/documents/{document_id}/extract", follow_redirects=False)
            assert_true(response.status_code in (302, 303), "Editor extraction did not redirect after success")

            with app.app_context():
                document = db.session.get(ActorDocument, document_id)
                extraction_run = DocumentExtractionRun.query.filter_by(actor_document_id=document_id).one()
                assert_true(extraction_run.status == "needs_review", "Extraction run did not require review for mismatched metadata")
                assert_true(extraction_run.template_profile_code == "certificate_of_origin_v1", "Certificate of Origin template profile was not used")
                assert_true(extraction_run.quality_score is not None, "Extraction quality score was not stored")
                assert_true("metadata_mismatch" in (extraction_run.risk_flags_json or []), "Metadata mismatch risk flag was not stored")
                assert_true(extraction_run.field_evidence_json.get("document_reference_number"), "Field evidence placeholder was not stored")
                assert_true(extraction_run.provenance_json.get("document_reference_number"), "Field provenance placeholder was not stored")
                assert_true(extraction_run.expiry_renewal_json.get("status") in {"current", "renewal_due_soon", "expired"}, "Expiry readiness was not stored")
                assert_true(DocumentFieldReconciliation.query.filter_by(extraction_run_id=extraction_run.id).count() >= 12, "Reconciliation rows were not created for certificate fields")
                assert_true(document.document_reference_number == "COO-CURRENT-001", "Extraction auto-updated document metadata")
                reference_row = DocumentFieldReconciliation.query.filter_by(
                    extraction_run_id=extraction_run.id,
                    field_name="document_reference_number",
                ).one()
                reference_row_id = reference_row.id
                assert_true(reference_row.extracted_value == "COO-EXTRACTED-999", "Reference number was not extracted")

            response = client.get(f"/partner/documents/{document_id}/reconcile")
            assert_true(response.status_code == 200 and "Reconcile Extracted Fields" in response.get_data(as_text=True), "Reconciliation page did not render")

            response = client.post(
                f"/partner/documents/{document_id}/reconcile",
                data={
                    f"action_{reference_row_id}": "accepted",
                    f"notes_{reference_row_id}": "Validated against uploaded certificate.",
                },
                follow_redirects=False,
            )
            assert_true(response.status_code in (302, 303), "Reconciliation save did not redirect")

            with app.app_context():
                document = db.session.get(ActorDocument, document_id)
                reference_row = db.session.get(DocumentFieldReconciliation, reference_row_id)
                assert_true(document.document_reference_number == "COO-EXTRACTED-999", "Accepted reconciliation did not update mapped metadata")
                assert_true(reference_row.status == "accepted", "Reference reconciliation row was not marked accepted")
                assert_true(reference_row.decision_history_json, "Reconciliation decision history was not stored")
                assert_true(DocumentAccessLog.query.filter_by(actor_document_id=document_id, access_type="preview").first() is not None, "Preview access log was not written")
                assert_true(AuditLog.query.filter_by(action="partner_document_extraction_created").first() is not None, "Extraction audit log was not written")
                assert_true(AuditLog.query.filter_by(action="partner_document_reconciliation_updated").first() is not None, "Reconciliation audit log was not written")

        print("Phase 3.1 document preview/extraction validation passed.")
    finally:
        shutil.rmtree(PRIVATE_UPLOAD_ROOT, ignore_errors=True)


if __name__ == "__main__":
    run_validation()
