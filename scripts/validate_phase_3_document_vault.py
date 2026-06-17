"""Validate Phase 3 partner actor document vault behavior.

This script uses an in-memory SQLite database and Flask's test client so it
does not touch Replit PostgreSQL data or real private document storage.
"""

import io
import os
import shutil
import sys
import tempfile
from pathlib import Path

PRIVATE_UPLOAD_ROOT = tempfile.mkdtemp(prefix="fieldsight-phase-3-docs-")

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SESSION_SECRET", "phase-3-validation-secret")
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
    ActorDocumentVersion,
    AuditLog,
    Commodity,
    Crop,
    DocumentAccessLog,
    DocumentType,
    MarketActor,
    PartnerOrganization,
    PartnerUserProfile,
    User,
)


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def assert_path_inside(path, root, message):
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
    except ValueError as exc:
        raise AssertionError(message) from exc


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


def document_form_data(document_type_id, crop_id, commodity_id, title="CAC Certificate"):
    return {
        "document_type_id": str(document_type_id),
        "title": title,
        "description": "Validation document",
        "document_reference_number": "CAC-VALID-001",
        "issuing_body": "Corporate Affairs Commission",
        "issued_at": "2026-01-15",
        "expires_at": "",
        "linked_crop_id": str(crop_id),
        "linked_commodity_id": str(commodity_id),
        "subscriber_access_level": "full_document",
    }


def upload_document(client, actor_id, document_type_id, crop_id, commodity_id, title, filename, content):
    data = document_form_data(document_type_id, crop_id, commodity_id, title=title)
    data["file"] = (io.BytesIO(content), filename)
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

            org = PartnerOrganization(name="Document Partner", slug="document-partner", status="active")
            other_org = PartnerOrganization(name="Other Document Partner", slug="other-document-partner", status="active")
            db.session.add_all([org, other_org])
            db.session.flush()

            editor = create_user("Data Editor", "editor@example.com")
            reviewer = create_user("Data Reviewer", "reviewer@example.com")
            viewer = create_user("Partner Viewer", "viewer@example.com")
            ordinary = create_user("Ordinary Subscriber", "ordinary@example.com")
            other_editor = create_user("Other Editor", "other-editor@example.com")

            link_partner_user(editor, org, "data_editor")
            link_partner_user(reviewer, org, "data_reviewer")
            link_partner_user(viewer, org, "partner_viewer")
            link_partner_user(other_editor, other_org, "data_editor")

            crop = Crop.query.filter_by(code="ginger").one()
            commodity = Commodity(crop_id=crop.id, code="ginger_validation", name="Validation Ginger", category="Ginger", active=True)
            db.session.add(commodity)
            db.session.flush()

            actor = MarketActor(
                partner_organization_id=org.id,
                created_by_user_id=editor.id,
                updated_by_id=editor.id,
                actor_type="exporter",
                name="Document Vault Exporter",
                crop_id=crop.id,
                commodity_id=commodity.id,
                status="active",
            )
            other_actor = MarketActor(
                partner_organization_id=other_org.id,
                created_by_user_id=other_editor.id,
                updated_by_id=other_editor.id,
                actor_type="exporter",
                name="Other Document Exporter",
                status="active",
            )
            db.session.add_all([actor, other_actor])
            db.session.commit()

            actor_id = actor.id
            other_actor_id = other_actor.id
            crop_id = crop.id
            commodity_id = commodity.id
            document_type_id = DocumentType.query.filter_by(name="CAC Certificate").one().id

        client = app.test_client()
        first_content = b"%PDF-1.4\nphase 3 validation document\n"
        second_content = b"%PDF-1.4\nphase 3 validation document v2\n"

        with client:
            response = client.get(f"/partner/actors/{actor_id}/documents", follow_redirects=False)
            assert_true(response.status_code == 302 and "/login" in response.headers.get("Location", ""), "Document list did not require login")

            login(client, "ordinary@example.com")
            response = client.get(f"/partner/actors/{actor_id}/documents", follow_redirects=False)
            assert_true(response.status_code in (302, 303), "Ordinary subscriber accessed partner document list")
            logout(client)

            login(client, "other-editor@example.com")
            response = client.get(f"/partner/actors/{actor_id}/documents", follow_redirects=False)
            assert_true(response.status_code == 404, "Cross-organization actor document list was accessible")
            logout(client)

            login(client, "editor@example.com")
            response = client.get(f"/partner/actors/{actor_id}/documents")
            assert_true(response.status_code == 200 and "Documents" in response.get_data(as_text=True), "Own actor document list did not render")

            response = upload_document(
                client,
                actor_id,
                document_type_id,
                crop_id,
                commodity_id,
                "Validation CAC Certificate",
                "cac-certificate.pdf",
                first_content,
            )
            assert_true(response.status_code in (302, 303), "Editor upload did not redirect after success")

            with app.app_context():
                document = ActorDocument.query.filter_by(title="Validation CAC Certificate").one()
                document_id = document.id
                original_hash = document.file_hash
                original_storage_path = document.storage_path
                assert_true(document.market_actor_id == actor_id, "Uploaded document is not linked to the actor")
                assert_true(document.partner_organization_id is not None, "Uploaded document is not linked to the partner organization")
                assert_true(document.original_filename == "cac-certificate.pdf", "Original filename was not stored")
                assert_true(document.stored_filename and document.stored_filename != document.original_filename, "Stored filename was not sanitized/randomized")
                assert_true(document.mime_type == "application/pdf", "MIME type was not stored")
                assert_true(document.file_size == len(first_content), "File size was not stored")
                assert_true(len(document.file_hash or "") == 64, "SHA-256 hash was not stored")
                assert_true(document.version_number == 1, "Initial document version number was not set")
                assert_true(document.subscriber_access_level == "hidden", "Sensitive document did not default to hidden access")
                assert_true(document.visibility_level == "hidden", "Sensitive document visibility did not default to hidden")
                assert_path_inside(document.storage_path, PRIVATE_UPLOAD_ROOT, "Document file was not stored under PRIVATE_UPLOAD_ROOT")
                assert_true("static" not in Path(document.storage_path).parts, "Document file was stored under static")

                version = ActorDocumentVersion.query.filter_by(actor_document_id=document.id, version_number=1).one()
                assert_true(version.storage_path == document.storage_path, "Initial document version storage path mismatch")
                assert_true(version.checksum_sha256 == document.file_hash, "Initial document version hash mismatch")
                assert_true(Path(document.storage_path).exists(), "Uploaded private file does not exist")

            response = client.get(f"/partner/documents/{document_id}")
            detail_page = response.get_data(as_text=True)
            assert_true(response.status_code == 200 and "Validation CAC Certificate" in detail_page, "Document detail did not render")
            assert_true(str(PRIVATE_UPLOAD_ROOT) not in detail_page, "Document detail exposed the private upload root")

            response = client.post(
                f"/partner/documents/{document_id}/edit",
                data=document_form_data(document_type_id, crop_id, commodity_id, title="Validation CAC Certificate Updated"),
                follow_redirects=False,
            )
            assert_true(response.status_code in (302, 303), "Metadata edit did not redirect after success")

            with app.app_context():
                document = db.session.get(ActorDocument, document_id)
                assert_true(document.title == "Validation CAC Certificate Updated", "Metadata edit did not persist")
                assert_true(document.file_hash == original_hash, "Metadata edit replaced the file hash")
                assert_true(document.storage_path == original_storage_path, "Metadata edit replaced the storage path")
                assert_true(ActorDocumentVersion.query.filter_by(actor_document_id=document_id).count() == 1, "Metadata edit created a new version")

            response = client.post(
                f"/partner/documents/{document_id}/versions/new",
                data={"file": (io.BytesIO(second_content), "cac-certificate-v2.pdf")},
                content_type="multipart/form-data",
                follow_redirects=False,
            )
            assert_true(response.status_code in (302, 303), "New version upload did not redirect after success")

            with app.app_context():
                document = db.session.get(ActorDocument, document_id)
                current_version = ActorDocumentVersion.query.filter_by(actor_document_id=document_id, version_number=2).one()
                current_version_id = current_version.id
                assert_true(document.version_number == 2, "New version did not increment document version number")
                assert_true(ActorDocumentVersion.query.filter_by(actor_document_id=document_id).count() == 2, "New version row was not created")
                assert_true(document.file_hash != original_hash, "New version did not update current file hash")
                assert_true(document.file_size == len(second_content), "New version did not update current file size")
                assert_true(Path(original_storage_path).exists(), "Previous private version file was removed")

            before_invalid_count = None
            with app.app_context():
                before_invalid_count = ActorDocument.query.count()
            response = upload_document(
                client,
                actor_id,
                document_type_id,
                crop_id,
                commodity_id,
                "Invalid Extension",
                "unsafe.exe",
                b"not allowed",
            )
            assert_true(response.status_code == 200, "Invalid extension did not return the upload form")
            with app.app_context():
                assert_true(ActorDocument.query.count() == before_invalid_count, "Invalid extension created a document")

            oversized_content = b"x" * ((1024 * 1024) + 1)
            response = upload_document(
                client,
                actor_id,
                document_type_id,
                crop_id,
                commodity_id,
                "Oversized Document",
                "oversized.pdf",
                oversized_content,
            )
            assert_true(response.status_code == 200, "Oversized upload did not return the upload form")
            with app.app_context():
                assert_true(ActorDocument.query.count() == before_invalid_count, "Oversized upload created a document")

            logout(client)

            login(client, "viewer@example.com")
            response = client.get(f"/partner/documents/{document_id}")
            assert_true(response.status_code == 200, "Partner viewer could not view document metadata")
            response = client.get(f"/partner/documents/{document_id}/download", follow_redirects=False)
            assert_true(response.status_code in (302, 303), "Partner viewer was not denied document download")
            logout(client)

            login(client, "other-editor@example.com")
            response = client.get(f"/partner/documents/{document_id}", follow_redirects=False)
            assert_true(response.status_code == 404, "Cross-organization document detail was accessible")
            logout(client)

            login(client, "reviewer@example.com")
            response = client.get(f"/partner/documents/{document_id}/download")
            assert_true(response.status_code == 200, "Reviewer could not download document")
            assert_true(response.get_data() == second_content, "Download did not return the current version content")
            assert_true("attachment" in response.headers.get("Content-Disposition", ""), "Download did not use attachment disposition")
            logout(client)

            with app.app_context():
                assert_true(DocumentAccessLog.query.filter_by(actor_document_id=document_id, access_type="metadata_view").count() >= 1, "Metadata view access log was not written")
                download_log = DocumentAccessLog.query.filter_by(
                    actor_document_id=document_id,
                    actor_document_version_id=current_version_id,
                    access_type="download",
                ).first()
                assert_true(download_log is not None, "Download access log was not written")
                assert_true(download_log.access_channel == "partner_portal", "Download access channel was not stored")
                assert_true(download_log.user_id is not None, "Download user ID was not stored")
                assert_true(AuditLog.query.filter_by(action="partner_document_created").first() is not None, "Document create audit log was not written")
                assert_true(AuditLog.query.filter_by(action="partner_document_metadata_updated").first() is not None, "Document metadata audit log was not written")
                assert_true(AuditLog.query.filter_by(action="partner_document_version_uploaded").first() is not None, "Document version audit log was not written")

        print("Phase 3 document vault validation passed.")
    finally:
        shutil.rmtree(PRIVATE_UPLOAD_ROOT, ignore_errors=True)


if __name__ == "__main__":
    run_validation()
