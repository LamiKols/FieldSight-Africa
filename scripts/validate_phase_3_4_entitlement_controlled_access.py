"""Validate Phase 3.4 entitlement-controlled metadata access.

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

PRIVATE_UPLOAD_ROOT = tempfile.mkdtemp(prefix="fieldsight-phase-3-4-docs-")

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SESSION_SECRET", "phase-3-4-validation-secret")
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
    ActorLocation,
    ApiClient,
    ApiKey,
    ApiUsageEvent,
    AuditLog,
    Commodity,
    Crop,
    DocumentAccessLog,
    DocumentAccessRequest,
    DocumentExtractionRun,
    DocumentFieldReconciliation,
    DocumentPublishControl,
    DocumentType,
    MarketActor,
    PartnerOrganization,
    PartnerUserProfile,
    Region,
    Subscription,
    User,
    consent_document_category_for_document_type,
)


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


def future_datetime(days=30):
    return utcnow() + timedelta(days=days)


def future_date(days=365):
    return (utcnow().date() + timedelta(days=days)).isoformat()


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


def document_form_data(document_type_id, crop_id, commodity_id, expires_at):
    return {
        "document_type_id": str(document_type_id),
        "title": "Phase 3.4 Certificate of Origin",
        "description": "Internal partner description should never be subscriber/API output",
        "document_reference_number": "COO-PHASE-34-001",
        "issuing_body": "Nigerian Export Promotion Council",
        "issued_at": utcnow().date().isoformat(),
        "expires_at": expires_at,
        "linked_crop_id": str(crop_id),
        "linked_commodity_id": str(commodity_id),
        "subscriber_access_level": "metadata_only",
    }


def extraction_fixture_content(expires_at):
    return "\n".join([
        "document_reference_number: COO-PHASE-34-001",
        "issuing_body: Nigerian Export Promotion Council",
        f"issued_at: {utcnow().date().isoformat()}",
        f"expires_at: {expires_at}",
        "exporter_name: Hidden Exporter Ltd",
        "consignee_name: Hidden Buyer Ltd",
        "origin_country: Nigeria",
        "destination_country: United Kingdom",
        "crop_or_commodity: Ginger",
        "quantity: 20 MT",
        "port_of_exit: Lagos",
        "certificate_type: Certificate of Origin",
    ]).encode("utf-8")


def upload_document(client, actor_id, document_type_id, crop_id, commodity_id, expires_at):
    data = document_form_data(document_type_id, crop_id, commodity_id, expires_at)
    data["file"] = (io.BytesIO(extraction_fixture_content(expires_at)), "phase-3-4-certificate.csv")
    return client.post(
        f"/partner/actors/{actor_id}/documents/new",
        data=data,
        content_type="multipart/form-data",
        follow_redirects=False,
    )


def create_active_consent(actor, organization, user, document_category):
    now = utcnow()
    consent = ActorConsentRecord(
        market_actor_id=actor.id,
        partner_organization_id=organization.id,
        consent_status="granted",
        consent_method="written",
        consent_reference="CONSENT-PHASE-3-4",
        consent_scope_json=[
            "store_actor_documents",
            "share_document_metadata_with_subscribers",
            "share_redacted_documents_with_subscribers",
            "share_full_documents_with_approved_users",
            "include_in_paid_data_packs",
            "include_in_live_intelligence",
            "include_in_api_responses",
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
        granted_by_name="Validation Actor",
        granted_at=now,
        expires_at=now + timedelta(days=365),
        captured_by_user_id=user.id,
        active=True,
    )
    db.session.add(consent)
    db.session.flush()
    return consent


def accept_reconciliation_rows(document_id, reviewer_id):
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
            "notes": "Phase 3.4 validation reconciliation.",
            "reviewed_by_user_id": reviewer_id,
            "reviewed_at": now.isoformat(),
        }]
    run.status = "completed"
    run.document_intelligence_status = "reconciled"
    run.risk_flags_json = []
    run.metadata_mismatches_json = []
    run.expiry_renewal_json = {"status": "current", "expires_at": None, "days_until_expiry": 365}
    db.session.flush()


def make_publish_control(document_id, target, status="ready"):
    control = DocumentPublishControl(
        actor_document_id=document_id,
        publish_target=target,
        status=status,
        readiness_checks_json=[{"key": "validation", "status": "pass"}],
        blocking_reasons_json=[],
        admin_decision="validation_seed",
        decided_at=utcnow(),
        last_evaluated_at=utcnow(),
    )
    db.session.add(control)
    db.session.flush()
    return control


def approve_for_external_metadata(document):
    document.document_status = "approved"
    document.review_status = "approved"
    document.verification_status = "verified"
    document.redaction_status = "completed"
    document.review_comments = "Approved for Phase 3.4 validation."
    for target in [
        "subscriber_portal_metadata",
        "api_metadata",
        "redacted_document_candidate",
        "full_document_restricted_candidate",
    ]:
        make_publish_control(document.id, target)
    db.session.flush()


def create_subscription(user):
    subscription = Subscription(
        user_id=user.id,
        provider="validation",
        provider_subscription_id=f"sub-{user.id}",
        plan_code="STARTER",
        status="active",
        current_period_end=future_datetime(),
        regions_selected=["SW"],
        crops_selected=["Ginger"],
    )
    db.session.add(subscription)
    db.session.flush()
    return subscription


def create_api_key(owner_user):
    api_client = ApiClient(
        name="Phase 3.4 API Client",
        slug="phase-3-4-api-client",
        owner_user_id=owner_user.id,
        status="active",
        scopes=["document_metadata:read"],
    )
    db.session.add(api_client)
    db.session.flush()
    api_key = ApiKey(
        api_client_id=api_client.id,
        name="Validation Key",
        status="active",
        scopes=["document_metadata:read"],
    )
    raw_secret = "ph34-api-secret-token"
    api_key.set_secret(raw_secret)
    db.session.add(api_key)
    db.session.flush()
    return raw_secret


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

            org = PartnerOrganization(name="Phase 3.4 Partner", slug="phase-3-4-partner", status="active")
            db.session.add(org)
            db.session.flush()

            admin = create_user("Admin", "admin@example.com", role="admin")
            partner_editor = create_user("Partner Editor", "partner@example.com")
            subscriber = create_user("Subscriber", "subscriber@example.com")
            free_user = create_user("Free User", "free@example.com")
            link_partner_user(partner_editor, org, "data_editor")
            create_subscription(subscriber)
            api_secret = create_api_key(subscriber)

            crop = Crop.query.filter_by(code="ginger").one()
            commodity = Commodity(crop_id=crop.id, code="phase_3_4_ginger", name="Phase 3.4 Ginger", category="Ginger", active=True)
            db.session.add(commodity)
            region = Region.query.filter_by(code="SW").one()
            db.session.flush()

            actor = MarketActor(
                partner_organization_id=org.id,
                created_by_user_id=partner_editor.id,
                updated_by_id=partner_editor.id,
                actor_type="exporter",
                name="Phase 3.4 Exporter",
                crop_id=crop.id,
                commodity_id=commodity.id,
                status="active",
            )
            db.session.add(actor)
            db.session.flush()
            db.session.add(ActorLocation(
                market_actor_id=actor.id,
                region_id=region.id,
                location="Lagos",
                location_text="Lagos export office",
                is_primary=True,
            ))

            document_type = DocumentType.query.filter_by(name="Certificate of Origin").one()
            document_category = consent_document_category_for_document_type(document_type)
            create_active_consent(actor, org, partner_editor, document_category)
            db.session.commit()

            actor_id = actor.id
            subscriber_id = subscriber.id
            crop_id = crop.id
            commodity_id = commodity.id
            document_type_id = document_type.id
            partner_editor_id = partner_editor.id
            expires_at = future_date()

        client = app.test_client()

        response = client.get("/subscriber/document-metadata", follow_redirects=False)
        assert_true(response.status_code == 302 and "/login" in response.headers.get("Location", ""), "Subscriber metadata route did not require login")

        with client:
            login(client, "partner@example.com")
            response = upload_document(client, actor_id, document_type_id, crop_id, commodity_id, expires_at)
            assert_true(response.status_code in (302, 303), "Partner upload did not redirect")
            with app.app_context():
                document = ActorDocument.query.filter_by(title="Phase 3.4 Certificate of Origin").one()
                document_id = document.id
                assert_true(str(PRIVATE_UPLOAD_ROOT) in document.storage_path, "Document was not stored in validation private root")
            response = client.post(f"/partner/documents/{document_id}/extract", follow_redirects=False)
            assert_true(response.status_code in (302, 303), "Partner extraction did not redirect")
            logout(client)

            with app.app_context():
                document = db.session.get(ActorDocument, document_id)
                accept_reconciliation_rows(document_id, partner_editor_id)
                approve_for_external_metadata(document)
                blocked_document = ActorDocument(
                    market_actor_id=document.market_actor_id,
                    partner_organization_id=document.partner_organization_id,
                    document_type_id=document.document_type_id,
                    uploaded_by_user_id=partner_editor_id,
                    title="Blocked Phase 3.4 Document",
                    document_status="approved",
                    review_status="approved",
                    verification_status="verified",
                    redaction_status="completed",
                    subscriber_access_level="metadata_only",
                    visibility_level="metadata_only",
                    document_reference_number="BLOCKED-001",
                    issuing_body="Blocked Issuer",
                    linked_crop_id=crop_id,
                    linked_commodity_id=commodity_id,
                    expires_at=document.expires_at,
                    version_number=1,
                )
                db.session.add(blocked_document)
                db.session.flush()
                blocked_document_id = blocked_document.id
                db.session.commit()

            login(client, "subscriber@example.com")
            response = client.get("/subscriber/document-metadata")
            body = response.get_data(as_text=True)
            assert_true(response.status_code == 200, "Subscriber metadata list did not render")
            assert_true("Certificate of Origin" in body, "Allowed metadata was not visible")
            assert_true("COO-PHASE-34-001" in body, "Allowed reference number was not visible")
            assert_true(str(PRIVATE_UPLOAD_ROOT) not in body, "Subscriber metadata exposed private upload root")
            assert_true("phase-3-4-certificate.csv" not in body, "Subscriber metadata exposed original filename")
            assert_true("Phase 3.4 Exporter" not in body, "Subscriber metadata exposed actor name")
            assert_true("Internal partner description" not in body, "Subscriber metadata exposed internal description")

            response = client.get(f"/subscriber/document-metadata/{document_id}")
            detail_body = response.get_data(as_text=True)
            assert_true(response.status_code == 200, "Subscriber metadata detail did not render")
            assert_true("Nigerian Export Promotion Council" in detail_body, "Subscriber metadata detail missed issuing body")
            assert_true(str(PRIVATE_UPLOAD_ROOT) not in detail_body, "Subscriber metadata detail exposed private root")
            assert_true("phase-3-4-certificate.csv" not in detail_body, "Subscriber metadata detail exposed filename")

            response = client.post(
                "/subscriber/document-access-requests/new",
                data={
                    "document_id": str(document_id),
                    "request_type": "redacted_document",
                    "organization_name": "Subscriber Buyer Ltd",
                    "purpose": "Due diligence review request",
                },
                follow_redirects=False,
            )
            assert_true(response.status_code in (302, 303), "Access request creation did not redirect")
            with app.app_context():
                request_row = DocumentAccessRequest.query.filter_by(actor_document_id=document_id, user_id=subscriber_id).one()
                assert_true(request_row.status == "pending", "Access request was not pending")
                assert_true(AuditLog.query.filter_by(action="subscriber_document_access_requested").first() is not None, "Access request audit log missing")
                assert_true(DocumentAccessLog.query.filter_by(actor_document_id=document_id, access_type="subscriber_document_access_request_created").first() is not None, "Access request access log missing")
            logout(client)

            login(client, "free@example.com")
            response = client.get(f"/subscriber/document-metadata/{document_id}", follow_redirects=False)
            assert_true(response.status_code in (302, 303), "Free user was not redirected from blocked metadata detail")
            logout(client)

            response = client.get("/api/v1/document-metadata")
            assert_true(response.status_code == 401, "API route did not reject missing key")
            response = client.get(
                "/api/v1/document-metadata",
                headers={"Authorization": f"Bearer {api_secret}"},
            )
            assert_true(response.status_code == 200, "API metadata list did not return success")
            api_body = response.get_json()
            api_text = response.get_data(as_text=True)
            assert_true(api_body["count"] == 1, "API metadata list returned unexpected row count")
            assert_true(api_body["data"][0]["reference_number"] == "COO-PHASE-34-001", "API metadata missed reference number")
            assert_true("storage_path" not in api_text and "original_filename" not in api_text, "API metadata exposed file fields")
            assert_true(str(PRIVATE_UPLOAD_ROOT) not in api_text, "API metadata exposed private root")
            assert_true("Phase 3.4 Exporter" not in api_text, "API metadata exposed actor name")
            assert_true("Hidden Buyer" not in api_text, "API metadata exposed extracted PII")

            response = client.get(
                f"/api/v1/document-metadata?document_id={blocked_document_id}",
                headers={"X-API-Key": api_secret},
            )
            assert_true(response.status_code == 403, "API did not block metadata without publish controls")
            with app.app_context():
                assert_true(ApiUsageEvent.query.filter_by(endpoint="/api/v1/document-metadata", status_code=200).first() is not None, "API usage success event missing")
                assert_true(ApiUsageEvent.query.filter_by(endpoint="/api/v1/document-metadata", status_code=403).first() is not None, "API usage blocked event missing")
                assert_true(DocumentAccessLog.query.filter_by(actor_document_id=document_id, access_type="api_document_metadata_allowed").first() is not None, "API allowed access log missing")
                assert_true(DocumentAccessLog.query.filter_by(actor_document_id=blocked_document_id, access_type="api_document_metadata_blocked").first() is not None, "API blocked access log missing")
                assert_true(AuditLog.query.filter_by(action="api_document_metadata_unauthorized").first() is not None, "Unauthorized API audit log missing")

            login(client, "admin@example.com")
            response = client.get("/admin/document-access-requests")
            admin_body = response.get_data(as_text=True)
            assert_true(response.status_code == 200 and "Due diligence review request" in admin_body, "Admin access request queue did not show request")
            logout(client)

            with app.app_context():
                document = db.session.get(ActorDocument, document_id)
                document.review_status = "needs_correction"
                document.document_status = "needs_correction"
                document.review_comments = "Please correct the issuing body."
                db.session.commit()

            login(client, "partner@example.com")
            response = client.get("/partner/documents/corrections")
            correction_body = response.get_data(as_text=True)
            assert_true(response.status_code == 200 and "Please correct the issuing body." in correction_body, "Partner correction queue did not show admin comments")
            response = client.post(
                f"/partner/documents/{document_id}/correction",
                data={
                    "document_type_id": str(document_type_id),
                    "title": "Phase 3.4 Corrected Certificate",
                    "description": "Corrected internal description",
                    "document_reference_number": "COO-PHASE-34-002",
                    "issuing_body": "Corrected Issuing Body",
                    "issued_at": utcnow().date().isoformat(),
                    "expires_at": expires_at,
                    "linked_crop_id": str(crop_id),
                    "linked_commodity_id": str(commodity_id),
                    "subscriber_access_level": "metadata_only",
                    "correction_notes": "Corrected the issuing body.",
                    "file": (io.BytesIO(extraction_fixture_content(expires_at)), "corrected-phase-3-4.csv"),
                },
                content_type="multipart/form-data",
                follow_redirects=False,
            )
            assert_true(response.status_code in (302, 303), "Partner correction submission did not redirect")
            with app.app_context():
                document = db.session.get(ActorDocument, document_id)
                assert_true(document.review_status == "pending", "Correction did not reset review status")
                assert_true(document.document_status == "submitted", "Correction did not resubmit document")
                assert_true(document.version_number == 2, "Correction upload did not create a new version")
                assert_true(AuditLog.query.filter_by(action="partner_document_correction_submitted").first() is not None, "Correction audit log missing")

        print("Phase 3.4 entitlement-controlled access validation passed.")
    finally:
        shutil.rmtree(PRIVATE_UPLOAD_ROOT, ignore_errors=True)


if __name__ == "__main__":
    run_validation()
