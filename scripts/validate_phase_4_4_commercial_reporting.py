"""Validate Phase 4.4 commercial reporting and revenue intelligence.

This script uses an in-memory SQLite database and Flask's test client so it
does not touch Replit PostgreSQL data, payment providers, private document
files, or real API secrets.
"""

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SESSION_SECRET", "phase-4-4-validation-secret")
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
    ActorLocation,
    ApiClient,
    ApiKey,
    CommercialFulfilmentAction,
    CommercialRequest,
    Crop,
    DocumentAccessRequest,
    DocumentType,
    License,
    LicensedPack,
    LiveIntelligenceAccess,
    MarketActor,
    PartnerOrganization,
    Region,
    Subscription,
    User,
)


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


def set_created_at(record, days_ago):
    created_at = utcnow() - timedelta(days=days_ago)
    record.created_at = created_at
    if hasattr(record, "updated_at"):
        record.updated_at = created_at


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


def create_subscription(user, plan_code="STARTER", days_ago=1):
    subscription = Subscription(
        user_id=user.id,
        provider="validation",
        provider_subscription_id=f"phase-4-4-sub-{user.id}-{plan_code}",
        plan_code=plan_code,
        status="active",
        current_period_end=utcnow() + timedelta(days=45),
        regions_selected=["SW"],
        crops_selected=["Ginger"],
    )
    set_created_at(subscription, days_ago)
    db.session.add(subscription)
    db.session.flush()
    return subscription


def create_license(user, days_ago=1):
    licensed_pack = LicensedPack.query.filter_by(active=True).order_by(LicensedPack.price_usd).first()
    license_record = License(
        user_id=user.id,
        licensed_pack_id=licensed_pack.id,
        regions_selected=["SW"],
        crops_selected=["Ginger"],
        snapshot_month="2026-06",
        status="active",
    )
    set_created_at(license_record, days_ago)
    db.session.add(license_record)
    db.session.flush()
    return license_record


def create_api_client_with_key(user, days_ago=1):
    api_client = ApiClient(
        name="Phase 4.4 API Client",
        slug=f"phase-4-4-api-client-{user.id}",
        owner_user_id=user.id,
        status="active",
        scopes=["document_metadata:read"],
        notes="Validation client with hidden key material.",
    )
    set_created_at(api_client, days_ago)
    db.session.add(api_client)
    db.session.flush()

    api_key = ApiKey(
        api_client_id=api_client.id,
        name="Hidden Validation Key",
        status="active",
        scopes=["document_metadata:read"],
    )
    api_key.set_secret("phase-4-4-raw-secret")
    db.session.add(api_key)
    db.session.flush()
    return api_client, api_key


def create_live_access(user, days_ago=1):
    live_access = LiveIntelligenceAccess(
        user_id=user.id,
        regions_allowed=1,
        crops_allowed=1,
        regions_selected=["SW"],
        crops_selected=["Ginger"],
        start_date=utcnow() - timedelta(days=1),
        end_date=utcnow() + timedelta(days=90),
        active=True,
        notes="Phase 4.4 validation live access.",
    )
    set_created_at(live_access, days_ago)
    db.session.add(live_access)
    db.session.flush()
    return live_access


def create_commercial_request(
    user,
    request_type,
    product,
    status="pending",
    days_ago=1,
    region_code="SW",
    crop_name="Ginger",
):
    commercial_request = CommercialRequest(
        user_id=user.id,
        request_type=request_type,
        organization_name="Validation Buyer Ltd",
        contact_name="Secret Contact Name",
        contact_email="secret-contact@example.com",
        requested_product=product,
        dataset_code="document_metadata" if request_type == "api_access" else "market_prices",
        region_code=region_code,
        crop_name=crop_name,
        message="Private commercial note should not render.",
        context_json={"private_context": "hidden-context-value"},
        status=status,
    )
    set_created_at(commercial_request, days_ago)
    db.session.add(commercial_request)
    db.session.flush()
    return commercial_request


def create_document_access_request(user, days_ago=1):
    organization = PartnerOrganization(
        name="Phase 4.4 Partner",
        slug="phase-4-4-partner",
        status="active",
    )
    db.session.add(organization)
    db.session.flush()

    region = Region.query.filter_by(code="SW").one()
    crop = Crop.query.filter_by(name="Ginger").one()
    actor = MarketActor(
        partner_organization_id=organization.id,
        created_by_user_id=user.id,
        actor_type="exporter",
        name="Hidden Exporter",
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
        uploaded_by_user_id=user.id,
        title="Safe Reporting Certificate",
        description="Unsafe raw document description should not render.",
        original_filename="unsafe-original-report.pdf",
        stored_filename="unsafe-stored-report.pdf",
        storage_path="/private_uploads/unsafe/report.pdf",
        mime_type="application/pdf",
        file_size=1024,
        file_hash="unsafe-file-hash-should-not-render",
        document_reference_number="REF-SECRET-44",
        issuing_body="Hidden Issuing Body",
        linked_crop_id=crop.id,
        document_status="approved",
        review_status="approved",
        verification_status="verified",
        redaction_status="completed",
        subscriber_access_level="metadata_only",
    )
    db.session.add(document)
    db.session.flush()

    access_request = DocumentAccessRequest(
        actor_document_id=document.id,
        user_id=user.id,
        request_type="redacted_document",
        request_channel="subscriber_portal",
        organization_name="Buyer Due Diligence Ltd",
        purpose="Private due diligence purpose should not render.",
        status="pending",
    )
    set_created_at(access_request, days_ago)
    db.session.add(access_request)
    db.session.flush()
    return access_request


def assert_unsafe_values_hidden(page, api_key_hash):
    unsafe_values = [
        "phase-4-4-raw-secret",
        api_key_hash,
        "Secret Contact Name",
        "secret-contact@example.com",
        "Private commercial note should not render.",
        "hidden-context-value",
        "/private_uploads/",
        "unsafe-original-report.pdf",
        "unsafe-stored-report.pdf",
        "unsafe-file-hash-should-not-render",
        "REF-SECRET-44",
        "Hidden Issuing Body",
        "Unsafe raw document description",
        "Hidden Exporter",
        "Hidden actor location",
        "Private due diligence purpose should not render.",
    ]
    for unsafe in unsafe_values:
        assert_true(unsafe not in page, f"Unsafe value leaked in commercial reporting output: {unsafe}")


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

        subscriber = create_user("Reporting Subscriber", "subscriber@example.com")
        other_user = create_user("Other Subscriber", "other@example.com")
        admin = create_user("Reporting Admin", "admin@example.com", role="admin")

        create_subscription(subscriber, days_ago=1)
        create_license(subscriber, days_ago=1)
        create_live_access(subscriber, days_ago=1)
        _api_client, api_key = create_api_client_with_key(subscriber, days_ago=1)

        api_request = create_commercial_request(
            subscriber,
            "api_access",
            "API Metadata Access",
            status="pending",
            days_ago=1,
        )
        create_commercial_request(
            subscriber,
            "live_intelligence",
            "Live Market Intelligence",
            status="contacted",
            days_ago=2,
        )
        upgrade_request = create_commercial_request(
            subscriber,
            "upgrade",
            "National Upgrade",
            status="approved_for_fulfilment",
            days_ago=3,
        )
        old_request = create_commercial_request(
            other_user,
            "api_access",
            "Old Product",
            status="pending",
            days_ago=120,
            region_code="NC",
            crop_name="Sesame",
        )
        create_document_access_request(subscriber, days_ago=1)

        fulfilment = CommercialFulfilmentAction(
            commercial_request_id=upgrade_request.id,
            action_type="upgrade_followup",
            status="recorded",
            notes="Fulfilment note should not render.",
            performed_by_user_id=admin.id,
            metadata_json={"payment_flow_changed": False},
        )
        db.session.add(fulfilment)
        db.session.commit()

        ids = {
            "api_request": api_request.id,
            "old_request": old_request.id,
        }
        api_key_hash = api_key.key_hash

    client = app.test_client()

    for path in [
        "/admin/commercial-reports",
        "/admin/commercial-reports/pipeline.csv",
    ]:
        response = client.get(path, follow_redirects=False)
        assert_true(response.status_code == 302 and "/login" in response.headers.get("Location", ""), f"{path} did not require login")

    with client:
        login(client, "subscriber@example.com")
        for path in [
            "/admin/commercial-reports",
            "/admin/commercial-reports/pipeline.csv",
        ]:
            response = client.get(path, follow_redirects=False)
            assert_true(response.status_code in (302, 303), f"{path} was not admin-only")
        logout(client)

        login(client, "admin@example.com")
        for window in ["7d", "30d", "90d", "all"]:
            response = client.get(f"/admin/commercial-reports?window={window}")
            assert_true(response.status_code == 200, f"Commercial report did not render for window {window}")
            page = response.get_data(as_text=True)
            assert_true("Commercial Reports" in page, "Commercial reporting dashboard title missing")
            assert_true("Request Funnel" in page, "Request funnel metrics missing")
            assert_true("Revenue Readiness" in page, "Revenue readiness metrics missing")
            assert_true("Follow-up Queue" in page, "Follow-up queue missing")
            assert_true("API Enquiries" in page, "API enquiry pipeline metric missing")
            assert_unsafe_values_hidden(page, api_key_hash)

        response = client.get("/admin/commercial-reports?window=30d")
        page_30d = response.get_data(as_text=True)
        assert_true("API Metadata Access" in page_30d, "Recent API product demand missing from 30-day report")
        assert_true("Old Product" not in page_30d, "30-day report included old request outside the window")

        response = client.get("/admin/commercial-reports?window=all")
        page_all = response.get_data(as_text=True)
        assert_true("Old Product" in page_all, "All-time report did not include old request")
        assert_true(f"#{ids['old_request']}" in page_all, "All-time follow-up queue missed old request ID")

        response = client.get("/admin/")
        assert_true(response.status_code == 200, "Admin dashboard did not render")
        admin_dashboard = response.get_data(as_text=True)
        assert_true("Commercial Reports" in admin_dashboard, "Admin dashboard missing commercial reports link")
        assert_true("Follow-up" in admin_dashboard, "Admin dashboard missing follow-up counter")

        response = client.get("/admin/commercial-reports/pipeline.csv?window=30d")
        assert_true(response.status_code == 200, "Commercial pipeline CSV did not render")
        csv_text = response.get_data(as_text=True)
        assert_true("pipeline_summary" in csv_text, "CSV missing pipeline summary rows")
        assert_true("request_funnel" in csv_text, "CSV missing request funnel rows")
        assert_true("revenue_readiness" in csv_text, "CSV missing revenue readiness rows")
        assert_true("follow_up_queue" in csv_text, "CSV missing follow-up queue rows")
        assert_true("API Metadata Access" in csv_text, "CSV missing recent product segment")
        assert_true("Old Product" not in csv_text, "30-day CSV included old request outside the window")
        assert_unsafe_values_hidden(csv_text, api_key_hash)

        response = client.get("/admin/commercial-reports/pipeline.csv?window=all")
        assert_true(response.status_code == 200, "All-time CSV did not render")
        csv_all = response.get_data(as_text=True)
        assert_true("Old Product" in csv_all, "All-time CSV did not include old product segment")
        assert_unsafe_values_hidden(csv_all, api_key_hash)

    print("Phase 4.4 commercial reporting validation passed.")


if __name__ == "__main__":
    run_validation()
