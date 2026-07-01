"""Validate partner onboarding demo polish.

This validation is intentionally pragmatic. It checks that the demo-polish
surfaces, seed data, documentation, and safety copy exist without touching
Replit PostgreSQL data, private files, payment providers, or API secrets.
"""

import importlib.util
import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SESSION_SECRET", "partner-onboarding-demo-polish-validation")
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
from models import ActorContact, MarketActor, PartnerUpdateBatch  # noqa: E402
from routes.partner_imports import is_import_batch  # noqa: E402
from scripts.seed_demo_data import (  # noqa: E402
    DEMO_ADMIN_EMAIL,
    DEMO_ERROR_IMPORT_TITLE,
    DEMO_PARTNER_EMAIL,
    DEMO_PASSWORD,
    DEMO_PENDING_IMPORT_TITLE,
    DEMO_SUCCESS_IMPORT_TITLE,
    DEMO_SUBSCRIBER_EMAIL,
    seed_demo_data,
)


DOC_PATH = REPO_ROOT / "docs" / "PARTNER_ONBOARDING_DEMO_POLISH.md"
PARTNER_VALIDATION_PATH = REPO_ROOT / "scripts" / "validate_partner_data_owner_onboarding.py"

REQUIRED_ROUTES = [
    "/partner/onboarding",
    "/partner/imports",
    "/partner/imports/new",
    "/partner/imports/<int:batch_id>",
    "/partner/imports/<int:batch_id>/preview",
    "/partner/imports/<int:batch_id>/submit",
    "/partner/imports/<int:batch_id>/errors.csv",
    "/partner/actor-update-invitations",
    "/admin/partner-imports",
    "/admin/partner-imports/<int:batch_id>",
    "/admin/partner-organizations",
    "/admin/partner-organizations/<int:organization_id>",
    "/admin/partner-organizations/<int:organization_id>/users",
    "/subscriber/product-tour",
]

DEMO_REFERENCES = [
    "Kano Grain Cooperative",
    "Oyo Cassava Aggregators Network",
    "Kaduna Maize Export Cluster",
    "Benue Soybean Producers Association",
    DEMO_PENDING_IMPORT_TITLE,
    DEMO_SUCCESS_IMPORT_TITLE,
    DEMO_ERROR_IMPORT_TITLE,
]

FORBIDDEN_TRUSTED_SURFACE_MARKERS = [
    "storage_path",
    "stored_filename",
    "original_filename",
    "file_hash",
    "key_hash",
    "api_secret",
    "private_uploads",
    "raw_text_excerpt",
    "ActorContact",
    "contact_phone",
    "contact_email",
    "kano-grain-demo@fieldsight-demo.invalid",
    "oyo-cassava-demo@fieldsight-demo.invalid",
    "actor-contact@fieldsight-demo.invalid",
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


def assert_ok(client, path, surface, expected=None):
    response = client.get(path)
    assert_true(response.status_code == 200, f"{surface} returned {response.status_code}")
    text = response.get_data(as_text=True)
    for value in expected or []:
        assert_true(value in text, f"{surface} missing expected text: {value}")
    for marker in FORBIDDEN_TRUSTED_SURFACE_MARKERS:
        assert_true(marker not in text, f"Restricted marker rendered on {surface}: {marker}")
    return text


def assert_documentation():
    assert_true(DOC_PATH.exists(), "Demo polish documentation is missing")
    text = DOC_PATH.read_text(encoding="utf-8")
    for phrase in [
        "Demo Personas",
        "Step-By-Step Walkthrough",
        "Important Routes And Screens",
        "Demo Data Included",
        "Validation Commands",
        "Known SQLite Warning",
    ]:
        assert_true(phrase in text, f"Documentation missing section: {phrase}")
    for reference in DEMO_REFERENCES:
        assert_true(reference in text, f"Documentation missing demo reference: {reference}")


def assert_routes_exist():
    routes = {rule.rule for rule in app.url_map.iter_rules()}
    for route in REQUIRED_ROUTES:
        assert_true(route in routes, f"Expected route missing: {route}")


def assert_partner_validation_callable():
    assert_true(PARTNER_VALIDATION_PATH.exists(), "Partner onboarding validation script is missing")
    spec = importlib.util.spec_from_file_location("partner_validation", PARTNER_VALIDATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert_true(callable(getattr(module, "run_validation", None)), "Partner onboarding validation is not callable")


def assert_seed_scenarios():
    titles = {
        batch.title for batch in PartnerUpdateBatch.query.all()
        if is_import_batch(batch)
    }
    for title in [DEMO_PENDING_IMPORT_TITLE, DEMO_SUCCESS_IMPORT_TITLE, DEMO_ERROR_IMPORT_TITLE]:
        assert_true(title in titles, f"Demo import scenario missing: {title}")

    assert_true(
        MarketActor.query.filter_by(name="Kaduna Maize Export Cluster").first() is not None,
        "Actor update invitation demo actor missing",
    )
    statuses = {actor.status for actor in MarketActor.query.all()}
    for status in ["active", "pending_review", "needs_correction"]:
        assert_true(status in statuses, f"Expected seeded actor status missing: {status}")

    restricted_contacts = ActorContact.query.filter_by(restricted=True, visibility_level="hidden").count()
    assert_true(restricted_contacts >= 1, "Demo import should create restricted contacts only")


def run_validation():
    assert_documentation()
    assert_routes_exist()
    assert_partner_validation_callable()

    with app.app_context():
        db.drop_all()
        db.create_all()
        seed_payment_plans()
        seed_datasets()
        seed_licensed_packs()
        seed_reference_data()
        seed_document_types()
        seed_reference_options()
        seed_demo_data(commit=True)
        assert_seed_scenarios()

    client = app.test_client()
    with client:
        login(client, DEMO_ADMIN_EMAIL)
        admin_imports = assert_ok(
            client,
            "/admin/partner-imports",
            "admin partner imports",
            ["Partner Registry Imports", DEMO_PENDING_IMPORT_TITLE, DEMO_SUCCESS_IMPORT_TITLE, DEMO_ERROR_IMPORT_TITLE],
        )
        assert_true("No partner imports are awaiting review" not in admin_imports, "Admin import queue rendered empty state despite demo seed")
        assert_ok(
            client,
            "/admin/partner-organizations",
            "admin partner organizations",
            ["Partner Organizations", "Kano Grain Cooperative", "Oyo Cassava Aggregators Network"],
        )

        logout(client)
        login(client, DEMO_PARTNER_EMAIL)
        partner_imports = assert_ok(
            client,
            "/partner/imports",
            "partner imports",
            ["Live Actor Registry Imports", "Demo Flow", DEMO_PENDING_IMPORT_TITLE],
        )
        assert_true("No partner registry imports yet" not in partner_imports, "Partner import list rendered empty state despite demo seed")
        assert_ok(
            client,
            "/partner/imports/new",
            "partner import form",
            ["Error CSV downloads", "Kano Grain Cooperative", "Preview Import"],
        )
        assert_ok(
            client,
            "/partner/actor-update-invitations",
            "actor update invitations",
            ["Demo Invitation Queue", "Kaduna Maize Export Cluster", "No personal contact details"],
        )

        with app.app_context():
            success_batch = PartnerUpdateBatch.query.filter_by(title=DEMO_SUCCESS_IMPORT_TITLE).one()
            error_batch = PartnerUpdateBatch.query.filter_by(title=DEMO_ERROR_IMPORT_TITLE).one()
        assert_ok(
            client,
            f"/partner/imports/{success_batch.id}/preview",
            "successful import preview",
            ["No validation errors were found", "awaiting admin review"],
        )
        assert_ok(
            client,
            f"/partner/imports/{error_batch.id}/preview",
            "error import preview",
            ["Error CSV is available", "Rejected Rows"],
        )

        logout(client)
        login(client, DEMO_SUBSCRIBER_EMAIL)
        assert_ok(
            client,
            "/subscriber/product-tour",
            "subscriber product tour",
            ["Trusted Data Story", "confidence-scored agricultural intelligence", "restricted contact fields"],
        )
        assert_ok(
            client,
            "/subscriber/document-metadata",
            "subscriber document metadata",
            ["Verified Document Metadata", "Document files, private paths, filenames, contact details, and downloads are not exposed"],
        )

    print("Partner onboarding demo polish validation passed.")


if __name__ == "__main__":
    run_validation()
