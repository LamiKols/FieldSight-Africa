"""Validate Phase 4.1 API productisation and developer onboarding.

This script uses an in-memory SQLite database and Flask's test client so it
does not touch Replit PostgreSQL data or real API secrets.
"""

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SESSION_SECRET", "phase-4-1-validation-secret")
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
    ActorDocument,
    ApiClient,
    ApiKey,
    ApiUsageEvent,
    AuditLog,
    CommercialRequest,
    DocumentAccessLog,
    DocumentType,
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


def create_api_client_with_key(user, name, slug, raw_secret):
    api_client = ApiClient(
        name=name,
        slug=slug,
        owner_user_id=user.id,
        status="active",
        scopes=["document_metadata:read"],
    )
    db.session.add(api_client)
    db.session.flush()
    api_key = ApiKey(
        api_client_id=api_client.id,
        name=f"{name} Key",
        status="active",
        scopes=["document_metadata:read"],
    )
    api_key.set_secret(raw_secret)
    db.session.add(api_key)
    db.session.flush()
    return api_client, api_key


def create_blocked_document_event(api_client, api_key, owner_user):
    organization = PartnerOrganization(name="Phase 4.1 Partner", slug="phase-4-1-partner", status="active")
    db.session.add(organization)
    db.session.flush()
    actor = MarketActor(
        partner_organization_id=organization.id,
        created_by_user_id=owner_user.id,
        actor_type="exporter",
        name="Hidden Exporter",
        status="active",
    )
    db.session.add(actor)
    db.session.flush()
    document_type = DocumentType.query.filter_by(name="Certificate of Origin").one()
    document = ActorDocument(
        market_actor_id=actor.id,
        partner_organization_id=organization.id,
        document_type_id=document_type.id,
        uploaded_by_user_id=owner_user.id,
        title="Hidden Certificate",
        document_status="approved",
        review_status="approved",
        verification_status="verified",
        storage_path="/private_uploads/hidden/should/not/render.pdf",
        file_hash="hidden-file-hash-should-not-render",
    )
    db.session.add(document)
    db.session.flush()
    db.session.add(DocumentAccessLog(
        actor_document_id=document.id,
        user_id=owner_user.id,
        api_client_id=api_client.id,
        access_type="api_document_metadata_blocked",
        access_channel="api",
        visibility_level="metadata_only",
    ))
    db.session.add(ApiUsageEvent(
        api_client_id=api_client.id,
        api_key_id=api_key.id,
        user_id=owner_user.id,
        endpoint="/api/v1/document-metadata",
        method="GET",
        dataset_type="document_metadata",
        filters_json={"region": "SW", "crop": "Ginger"},
        row_count=0,
        status_code=403,
        units=1,
    ))
    db.session.add(AuditLog(
        action="api_document_metadata_unauthorized",
        entity_type="api_request",
        after_values={"endpoint": "/api/v1/document-metadata", "status_code": 401},
    ))
    db.session.flush()


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

        subscriber = create_user("API Subscriber", "subscriber@example.com")
        other_user = create_user("Other Subscriber", "other@example.com")
        admin = create_user("API Admin", "admin@example.com", role="admin")

        raw_secret = "phase41-secret-token"
        other_secret = "other-secret-token"
        api_client, api_key = create_api_client_with_key(subscriber, "Phase 4.1 API Client", "phase-4-1-api-client", raw_secret)
        create_api_client_with_key(other_user, "Other User API Client", "other-user-api-client", other_secret)
        create_blocked_document_event(api_client, api_key, subscriber)
        db.session.commit()

        subscriber_id = subscriber.id
        raw_hash = api_key.key_hash
        raw_prefix = api_key.key_prefix

    client = app.test_client()

    for path in ["/subscriber/api", "/subscriber/api/docs", "/subscriber/api/request-access"]:
        response = client.get(path, follow_redirects=False)
        assert_true(response.status_code == 302 and "/login" in response.headers.get("Location", ""), f"{path} did not require login")

    with client:
        login(client, "subscriber@example.com")

        response = client.get("/subscriber/api")
        assert_true(response.status_code == 200, "Subscriber API dashboard did not render")
        page = response.get_data(as_text=True)
        assert_true("FieldSight API" in page, "API landing title missing")
        assert_true("Phase 4.1 API Client" in page, "Owned API client missing")
        assert_true(raw_prefix in page, "Key prefix was not shown")
        assert_true(raw_secret not in page, "Raw API secret leaked on subscriber dashboard")
        assert_true(raw_hash not in page, "API key hash leaked on subscriber dashboard")
        assert_true("Other User API Client" not in page, "Subscriber dashboard leaked another user's API client")
        assert_true("/api/v1/document-metadata" in page, "Safe sample request missing")
        assert_true("document_metadata:read" in page, "API scope missing")
        for unsafe in ["hidden-file-hash-should-not-render", "/private_uploads/", "Hidden Exporter"]:
            assert_true(unsafe not in page, f"Unsafe value leaked on subscriber API dashboard: {unsafe}")

        response = client.get("/subscriber/api/docs")
        assert_true(response.status_code == 200, "API docs did not render")
        page = response.get_data(as_text=True)
        assert_true("API Documentation" in page, "API docs title missing")
        assert_true("GET /api/v1/document-metadata" in page, "Endpoint docs missing")
        for safe_field in ["document_id", "actor_public_id", "document_type_code", "metadata_only"]:
            assert_true(safe_field in page, f"Safe field {safe_field} missing from docs")
        for unsafe in ["storage_path", "file_hash", "raw_text_excerpt", "original_filename", "stored_filename", "contact_details"]:
            assert_true(unsafe not in page, f"Unsafe API field appeared in docs: {unsafe}")

        with app.app_context():
            baseline_clients = ApiClient.query.count()
            baseline_keys = ApiKey.query.count()
            baseline_requests = CommercialRequest.query.filter_by(user_id=subscriber_id, request_type="api_access").count()

        response = client.post(
            "/subscriber/api/request-access",
            data={
                "organization_name": "API Buyer Ltd",
                "contact_name": "API Subscriber",
                "contact_email": "subscriber@example.com",
                "message": "We need governed API metadata access for onboarding validation.",
            },
            follow_redirects=False,
        )
        assert_true(response.status_code in (302, 303), "API access request was not accepted")
        with app.app_context():
            assert_true(ApiClient.query.count() == baseline_clients, "API enquiry created an API client")
            assert_true(ApiKey.query.count() == baseline_keys, "API enquiry created an API key")
            assert_true(
                CommercialRequest.query.filter_by(user_id=subscriber_id, request_type="api_access").count() == baseline_requests + 1,
                "API access enquiry was not captured",
            )
            commercial_request = CommercialRequest.query.filter_by(user_id=subscriber_id, request_type="api_access").order_by(CommercialRequest.id.desc()).first()
            assert_true(commercial_request.status == "pending", "API enquiry was not pending")
            assert_true(commercial_request.context_json.get("auto_client_created") is False, "API enquiry did not record non-provisioning")
            assert_true(commercial_request.context_json.get("auto_access_granted") is False, "API enquiry did not record non-granting behavior")
            audit = AuditLog.query.filter_by(action="commercial_api_access_request_created", entity_id=commercial_request.id).first()
            assert_true(audit is not None, "API access enquiry audit log missing")
            assert_true(audit.after_values.get("auto_granted") is False, "API access audit did not record non-granting behavior")

        response = client.get("/admin/api-dashboard", follow_redirects=False)
        assert_true(response.status_code in (302, 303), "Admin API dashboard was not admin-only")
        logout(client)

        login(client, "admin@example.com")
        response = client.get("/admin/api-dashboard")
        assert_true(response.status_code == 200, "Admin API dashboard did not render")
        page = response.get_data(as_text=True)
        assert_true("API Dashboard" in page, "Admin API dashboard title missing")
        assert_true("Phase 4.1 API Client" in page, "Admin API client missing")
        assert_true(raw_prefix in page, "Admin key prefix missing")
        assert_true("api_document_metadata_blocked" in page, "Blocked API event missing")
        assert_true("API Buyer Ltd" in page, "API access enquiry missing")
        assert_true(raw_secret not in page, "Raw API secret leaked on admin dashboard")
        assert_true(raw_hash not in page, "API key hash leaked on admin dashboard")
        for unsafe in ["hidden-file-hash-should-not-render", "/private_uploads/", "Hidden Exporter"]:
            assert_true(unsafe not in page, f"Unsafe value leaked on admin API dashboard: {unsafe}")

    print("Phase 4.1 API productisation validation passed.")


if __name__ == "__main__":
    run_validation()
