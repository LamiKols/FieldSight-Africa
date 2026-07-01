"""Validate the commercial demo and launch readiness release.

The validation uses an in-memory SQLite database and Flask's test client. It
does not touch Replit PostgreSQL data, private files, payment providers, or API
secrets.
"""

import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SESSION_SECRET", "commercial-demo-launch-readiness-validation")
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
    ActorContact,
    ActorDocument,
    ActorDocumentVersion,
    ApiClient,
    ApiKey,
    CommercialFulfilmentAction,
    CommercialRequest,
    DocumentAccessFulfilmentAction,
    DocumentAccessLog,
    DocumentAccessRequest,
    DocumentEntitlement,
    DocumentPublishControl,
    IntelligenceAlert,
    IntelligenceIngestionRun,
    IntelligencePublicationCandidate,
    IntelligenceSource,
    License,
    LiveIntelligenceAccess,
    MarketActor,
    PartnerOrganization,
    SubscriberIntelligenceDigest,
    Subscription,
)
from scripts.seed_demo_data import (  # noqa: E402
    DEMO_ACTOR_PUBLIC_ID,
    DEMO_ADMIN_EMAIL,
    DEMO_DOCUMENT_TITLE,
    DEMO_PARTNER_SLUG,
    DEMO_PASSWORD,
    DEMO_SUBSCRIBER_EMAIL,
    seed_demo_data,
)


FORBIDDEN_RENDERED_VALUES = [
    DEMO_ADMIN_EMAIL,
    DEMO_SUBSCRIBER_EMAIL,
    DEMO_PASSWORD,
    "storage_path",
    "stored_filename",
    "original_filename",
    "file_hash",
    "key_hash",
    "api_secret",
    "private_uploads",
    "raw_text_excerpt",
    "DEMO-CONSENT-001",
]


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def login(client, email, password=DEMO_PASSWORD):
    response = client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )
    assert_true(response.status_code in (302, 303), f"Login failed for {email}")


def logout(client):
    client.get("/logout", follow_redirects=False)


def assert_no_forbidden_text(text, surface):
    for forbidden in FORBIDDEN_RENDERED_VALUES:
        assert_true(forbidden not in text, f"Forbidden value rendered on {surface}: {forbidden}")


def demo_counts():
    return {
        "sources": IntelligenceSource.query.filter(IntelligenceSource.source_code.like("demo_%")).count(),
        "runs": IntelligenceIngestionRun.query.join(IntelligenceSource).filter(IntelligenceSource.source_code.like("demo_%")).count(),
        "alerts": IntelligenceAlert.query.join(IntelligenceSource).filter(IntelligenceSource.source_code.like("demo_%")).count(),
        "candidates": IntelligencePublicationCandidate.query.count(),
        "digests": SubscriberIntelligenceDigest.query.count(),
        "commercial_requests": CommercialRequest.query.filter(CommercialRequest.requested_product.like("%Demo%")).count(),
        "document_access_requests": DocumentAccessRequest.query.count(),
        "publish_controls": DocumentPublishControl.query.count(),
        "actors": MarketActor.query.filter_by(public_id=DEMO_ACTOR_PUBLIC_ID).count(),
        "documents": ActorDocument.query.filter_by(title=DEMO_DOCUMENT_TITLE).count(),
    }


def assert_seed_safe():
    partner = PartnerOrganization.query.filter_by(slug=DEMO_PARTNER_SLUG).one()
    assert_true(partner.contact_name is None, "Demo partner contact name should not be seeded")
    assert_true(partner.contact_email is None, "Demo partner contact email should not be seeded")
    assert_true(partner.contact_phone is None, "Demo partner contact phone should not be seeded")

    actor = MarketActor.query.filter_by(public_id=DEMO_ACTOR_PUBLIC_ID).one()
    assert_true(actor.name == "Demo Sahel Ginger Exporter", "Demo actor did not seed")
    assert_true(ActorContact.query.filter_by(market_actor_id=actor.id).count() == 0, "Demo seed should not create actor contacts")

    document = ActorDocument.query.filter_by(title=DEMO_DOCUMENT_TITLE).one()
    assert_true(document.original_filename is None, "Demo document original filename should be empty")
    assert_true(document.stored_filename is None, "Demo document stored filename should be empty")
    assert_true(document.storage_path is None, "Demo document storage path should be empty")
    assert_true(document.file_hash is None, "Demo document file hash should be empty")
    assert_true(ActorDocumentVersion.query.count() == 0, "Demo seed should not create document versions or files")

    consent = ActorConsentRecord.query.filter_by(consent_reference="DEMO-CONSENT-001").one()
    assert_true(consent.granted_by_email is None, "Demo consent email should be empty")
    assert_true(consent.granted_by_phone is None, "Demo consent phone should be empty")

    for commercial_request in CommercialRequest.query.filter(CommercialRequest.requested_product.like("%Demo%")).all():
        assert_true(commercial_request.contact_email is None, "Demo commercial request should not seed contact email")
        assert_true((commercial_request.context_json or {}).get("auto_granted") is False, "Demo commercial request should not auto-grant")
        assert_true((commercial_request.context_json or {}).get("payment_flow_changed") is False, "Demo seed should not change payments")

    assert_true(ApiClient.query.count() == 0, "Demo seed should not create API clients")
    assert_true(ApiKey.query.count() == 0, "Demo seed should not create API keys")
    assert_true(Subscription.query.count() == 0, "Demo seed should not create subscriptions")
    assert_true(License.query.count() == 0, "Demo seed should not create licences")
    assert_true(LiveIntelligenceAccess.query.count() == 0, "Demo seed should not create live intelligence access")
    assert_true(DocumentEntitlement.query.count() == 0, "Demo seed should not create document entitlements")
    assert_true(DocumentAccessLog.query.count() == 0, "Demo seed should not create document access logs")
    assert_true(CommercialFulfilmentAction.query.count() == 0, "Demo seed should not create commercial fulfilment")
    assert_true(DocumentAccessFulfilmentAction.query.count() == 0, "Demo seed should not create document fulfilment")


def assert_route_requires_login(client, path):
    response = client.get(path, follow_redirects=False)
    assert_true(response.status_code == 302 and "/login" in response.headers.get("Location", ""), f"{path} did not require login")


def assert_admin_only_for_subscriber(client, path):
    response = client.get(path, follow_redirects=False)
    assert_true(response.status_code in (302, 303), f"{path} was not admin-only")


def assert_ok_route(client, path, label, required_labels):
    response = client.get(path)
    assert_true(response.status_code == 200, f"{label} did not render")
    text = response.get_data(as_text=True)
    assert_no_forbidden_text(text, label)
    for required_label in required_labels:
        assert_true(required_label in text, f"{label} missing expected text: {required_label}")
    return text


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

        summary = seed_demo_data(commit=True)
        first_counts = demo_counts()
        second_summary = seed_demo_data(commit=True)
        second_counts = demo_counts()
        assert_true(summary["actor_public_id"] == DEMO_ACTOR_PUBLIC_ID, "Demo actor public ID mismatch")
        assert_true(second_summary["actor_public_id"] == DEMO_ACTOR_PUBLIC_ID, "Second seed actor public ID mismatch")
        assert_true(first_counts == second_counts, f"Demo seed was not idempotent: {first_counts} != {second_counts}")
        assert_seed_safe()

    client = app.test_client()
    for path in ["/admin/demo-walkthrough", "/admin/commercial-readiness", "/admin/actors", "/subscriber/product-tour"]:
        assert_route_requires_login(client, path)

    with client:
        login(client, DEMO_SUBSCRIBER_EMAIL)
        for path in ["/admin/demo-walkthrough", "/admin/commercial-readiness", "/admin/actors"]:
            assert_admin_only_for_subscriber(client, path)
        subscriber_text = assert_ok_route(
            client,
            "/subscriber/product-tour",
            "subscriber product tour",
            ["My Access", "Products", "API Docs", "Document Requests", "Intelligence Digests"],
        )
        assert_true("Request Paths" in subscriber_text, "Subscriber product tour missing request paths")
        logout(client)

        login(client, DEMO_ADMIN_EMAIL)
        walkthrough_text = assert_ok_route(
            client,
            "/admin/demo-walkthrough",
            "admin demo walkthrough",
            ["Commercial Demo Walkthrough", "Suggested Demo Path", "Operating Model Links"],
        )
        for label in [
            "Actor Registry",
            "Documents",
            "Document Review",
            "Commercial Requests",
            "Buyer Due Diligence",
            "API Products",
            "Automation",
            "Intelligence Sources",
            "Intelligence Alerts",
            "Publication Candidates",
            "Reports",
        ]:
            assert_true(label in walkthrough_text, f"Walkthrough missing operating model label: {label}")

        assert_ok_route(
            client,
            "/admin/commercial-readiness",
            "commercial readiness",
            [
                "Active intelligence sources",
                "Recent ingestion runs",
                "Open intelligence alerts",
                "Approved digests",
                "Commercial requests",
                "Document access requests",
                "API access requests",
                "Pending document review",
                "Automation queue health",
            ],
        )
        assert_ok_route(
            client,
            "/admin/actors",
            "admin actor registry",
            ["Actor Registry", "Demo Sahel Ginger Exporter", "Demo Sahel Produce Network"],
        )
        assert_ok_route(
            client,
            "/admin/",
            "admin dashboard",
            ["Demo Walkthrough", "Commercial Readiness", "Platform Operating Model"],
        )

    print("Commercial demo and launch readiness validation passed.")


if __name__ == "__main__":
    run_validation()
