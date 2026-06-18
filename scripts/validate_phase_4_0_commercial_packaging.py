"""Validate Phase 4.0 commercial product packaging.

This script uses an in-memory SQLite database and Flask's test client so it
does not touch Replit PostgreSQL data or payment/provider configuration.
"""

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SESSION_SECRET", "phase-4-0-validation-secret")
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
    ApiClient,
    AuditLog,
    CommercialRequest,
    License,
    LicensedPack,
    LiveIntelligenceAccess,
    Subscription,
    User,
)


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


def future_datetime(days=45):
    return utcnow() + timedelta(days=days)


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


def create_subscription(user):
    subscription = Subscription(
        user_id=user.id,
        provider="validation",
        provider_subscription_id=f"phase-4-sub-{user.id}",
        plan_code="STARTER",
        status="active",
        current_period_end=future_datetime(),
        regions_selected=["SW"],
        crops_selected=["Ginger"],
    )
    db.session.add(subscription)
    db.session.flush()
    return subscription


def create_license(user):
    pack = LicensedPack.query.filter_by(code="CORE_REGIONAL").one()
    license_record = License(
        user_id=user.id,
        licensed_pack_id=pack.id,
        regions_selected=["SW"],
        crops_selected=["Ginger"],
        snapshot_month=utcnow().strftime("%Y-%m"),
        status="active",
    )
    db.session.add(license_record)
    db.session.flush()
    return license_record


def create_live_access(user):
    access = LiveIntelligenceAccess(
        user_id=user.id,
        regions_allowed=1,
        crops_allowed=1,
        regions_selected=["SW"],
        crops_selected=["Ginger"],
        start_date=utcnow() - timedelta(days=1),
        end_date=future_datetime(),
        active=True,
        notes="Phase 4.0 validation live access.",
    )
    db.session.add(access)
    db.session.flush()
    return access


def create_api_client(user, name="Phase 4 API Client"):
    api_client = ApiClient(
        name=name,
        slug=name.lower().replace(" ", "-"),
        owner_user_id=user.id,
        status="active",
        scopes=["document_metadata:read"],
    )
    db.session.add(api_client)
    db.session.flush()
    return api_client


def commercial_request_payload(request_type, product):
    return {
        "request_type": request_type,
        "organization_name": "Validation Buyer Ltd",
        "contact_name": "Validation Subscriber",
        "contact_email": "subscriber@example.com",
        "requested_product": product,
        "dataset_code": "market_changes" if request_type == "upgrade" else "",
        "region_code": "NE" if request_type == "upgrade" else "",
        "crop_name": "Maize" if request_type == "upgrade" else "",
        "message": f"Please review {product} for Phase 4.0 validation.",
        "regions": ["SW", "NE"],
    }


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

        subscriber = create_user("Validation Subscriber", "subscriber@example.com")
        other_user = create_user("Other Subscriber", "other@example.com")
        admin = create_user("Validation Admin", "admin@example.com", role="admin")

        create_subscription(subscriber)
        create_license(subscriber)
        create_live_access(subscriber)
        create_api_client(subscriber)
        create_api_client(other_user, name="Other User API Client")
        db.session.add(CommercialRequest(
            user_id=other_user.id,
            request_type="upgrade",
            organization_name="Other Organization",
            contact_name="Other Subscriber",
            contact_email="other@example.com",
            requested_product="Other Private Request",
            message="This should not render on another subscriber's My Access page.",
            status="pending",
        ))
        db.session.commit()

    client = app.test_client()

    response = client.get("/subscriber/my-access", follow_redirects=False)
    assert_true(response.status_code == 302 and "/login" in response.headers.get("Location", ""), "My Access did not require login")

    with client:
        login(client, "subscriber@example.com")

        response = client.get("/subscriber/my-access")
        assert_true(response.status_code == 200, "My Access did not render for subscriber")
        page = response.get_data(as_text=True)
        assert_true("My Access" in page, "My Access title missing")
        assert_true("API And Document Metadata" in page, "API/document metadata section missing")
        assert_true("Phase 4 API Client" in page, "Subscriber API client missing")
        assert_true("Other User API Client" not in page, "My Access leaked another user's API client")
        assert_true("other@example.com" not in page, "My Access leaked another subscriber")
        assert_true("Request Upgrade" in page, "Upgrade CTA missing")
        assert_true("Request Restricted Access" in page, "Restricted document access CTA missing")

        response = client.get("/subscriber/products")
        assert_true(response.status_code == 200, "Product catalogue did not render")
        page = response.get_data(as_text=True)
        for label in ["Core Regional", "Expanded Regional", "National", "Live Market Intelligence"]:
            assert_true(label in page, f"{label} product tier missing")
        assert_true("They do not grant access automatically" in page, "Non-granting CTA explanation missing")

        with app.app_context():
            baseline = {
                "commercial_requests": CommercialRequest.query.count(),
                "subscriptions": Subscription.query.count(),
                "licenses": License.query.count(),
                "live_access": LiveIntelligenceAccess.query.count(),
                "api_clients": ApiClient.query.count(),
            }

        for request_type, product, audit_action in [
            ("upgrade", "Dataset Region Crop Upgrade", "commercial_upgrade_request_created"),
            ("api_access", "API Metadata", "commercial_api_access_request_created"),
            ("live_intelligence", "Live Market Intelligence", "commercial_live_intelligence_request_created"),
        ]:
            response = client.post(
                "/subscriber/commercial-request/new",
                data=commercial_request_payload(request_type, product),
                follow_redirects=False,
            )
            assert_true(response.status_code in (302, 303), f"{request_type} request was not accepted")
            with app.app_context():
                latest = CommercialRequest.query.order_by(CommercialRequest.created_at.desc(), CommercialRequest.id.desc()).first()
                assert_true(latest.request_type == request_type, f"{request_type} request type was not stored")
                assert_true(latest.status == "pending", f"{request_type} request was not pending")
                audit = AuditLog.query.filter_by(action=audit_action, entity_id=latest.id).first()
                assert_true(audit is not None, f"{audit_action} audit log missing")
                assert_true(audit.after_values.get("auto_granted") is False, f"{audit_action} audit did not record non-granting behavior")

        with app.app_context():
            assert_true(CommercialRequest.query.count() == baseline["commercial_requests"] + 3, "Commercial requests were not captured durably")
            assert_true(Subscription.query.count() == baseline["subscriptions"], "Commercial CTAs created a subscription")
            assert_true(License.query.count() == baseline["licenses"], "Commercial CTAs created a licence")
            assert_true(LiveIntelligenceAccess.query.count() == baseline["live_access"], "Commercial CTAs created live access")
            assert_true(ApiClient.query.count() == baseline["api_clients"], "Commercial CTAs created an API client")

        response = client.get("/admin/commercial-dashboard", follow_redirects=False)
        assert_true(response.status_code in (302, 303), "Admin commercial dashboard was not admin-only")
        logout(client)

        login(client, "admin@example.com")
        response = client.get("/admin/commercial-dashboard")
        assert_true(response.status_code == 200, "Admin commercial dashboard did not render")
        page = response.get_data(as_text=True)
        assert_true("Commercial Dashboard" in page, "Admin commercial dashboard title missing")
        assert_true("Commercial Requests" in page, "Commercial requests section missing")
        assert_true("API Clients And Access Requests" in page, "API/access request section missing")
        assert_true("commercial_upgrade_request_created" in page, "Recent commercial audit event missing")

    print("Phase 4.0 commercial packaging validation passed.")


if __name__ == "__main__":
    run_validation()
