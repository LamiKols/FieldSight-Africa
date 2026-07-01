"""Validate the Partner Data Owner Onboarding release.

This validation uses an in-memory SQLite database and Flask's test client. It
does not touch Replit PostgreSQL data, uploaded files, private paths, payment
providers, or API secrets.
"""

import io
import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SESSION_SECRET", "partner-data-owner-onboarding-validation")
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
    ActorContact,
    MarketActor,
    PartnerOrganization,
    PartnerRecordChange,
    PartnerUpdateBatch,
    PartnerUserProfile,
    User,
)
from routes.partner_imports import IMPORT_ROW_ENTITY_TYPE, import_batch_rows, is_import_batch  # noqa: E402
from scripts.seed_demo_data import (  # noqa: E402
    DEMO_ADMIN_EMAIL,
    DEMO_PARTNER_EMAIL,
    DEMO_PASSWORD,
    seed_demo_data,
)


BAD_PARTNER_LANGUAGE = [
    "one-time dataset sale",
    "download once",
    "static database",
    "upload once and sell",
]

CONTACT_MARKERS = [
    "+2341111111111",
    "field-contact@fieldsight-demo.invalid",
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


def create_user(name, email, role="subscriber"):
    user = User(name=name, email=email, role=role)
    user.set_password(DEMO_PASSWORD)
    db.session.add(user)
    db.session.flush()
    return user


def create_partner_profile(user, organization_name, slug):
    organization = PartnerOrganization(
        name=organization_name,
        slug=slug,
        status="active",
        country="Nigeria",
    )
    db.session.add(organization)
    db.session.flush()
    db.session.add(PartnerUserProfile(
        user_id=user.id,
        partner_organization_id=organization.id,
        partner_role="partner_admin",
        status="active",
    ))
    db.session.flush()
    return organization


def assert_no_bad_language(text, surface):
    lowered = text.lower()
    for phrase in BAD_PARTNER_LANGUAGE:
        assert_true(phrase not in lowered, f"Disallowed partner workflow language rendered on {surface}: {phrase}")


def assert_no_contact_markers(text, surface):
    for marker in CONTACT_MARKERS:
        assert_true(marker not in text, f"Restricted contact marker rendered on {surface}: {marker}")


def assert_ok(client, path, surface, required_text=None):
    response = client.get(path)
    assert_true(response.status_code == 200, f"{surface} did not render: {response.status_code}")
    text = response.get_data(as_text=True)
    assert_no_bad_language(text, surface)
    assert_no_contact_markers(text, surface)
    for value in required_text or []:
        assert_true(value in text, f"{surface} missing expected text: {value}")
    return text


def importer_csv():
    csv_text = "\n".join([
        "COMMODITY CATEGORY,FARMER/AGGREAGATOR,LOCATION,STATE,PHONE,EMAIL,LGA,REGISTRATION STATUS,DATE OF REGISTRATION,NUMBER OF YEARS IN EXPORT TRADE,TRADE DESTINATION,EXPORT CAPACITY,ERTIFICATION,PORT OF EXIT,CONSTRAINT",
        "Ginger,Validation Fresh Aggregator,Validation market zone,Lagos,+2341111111111,field-contact@fieldsight-demo.invalid,Ikeja,registered,2026-06-01,5,Demo buyer market,30 metric tonnes,Validation certification,Demo export corridor,Needs seasonal refresh",
        "Ginger,,Missing actor name zone,Lagos,,,Ikeja,pending,not-a-date,2,Demo market,10 bags,Pending certification,Demo port,Missing actor name",
        "Ginger,Demo Sahel Ginger Exporter,Changed validation zone,Lagos,,,Ikeja,registered,2026-06-02,4,Demo buyer market,Updated volume,Validation update,Demo port,Potential update candidate",
    ])
    return io.BytesIO(csv_text.encode("utf-8"))


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
        seed_demo_data(commit=True)

        other_user = create_user("Other Partner Owner", "other.partner@fieldsight-demo.invalid")
        create_partner_profile(other_user, "Other Demo Partner", "other-demo-partner")
        db.session.commit()

    client = app.test_client()

    for protected_path in ["/partner/onboarding", "/partner/imports", "/partner/imports/new"]:
        response = client.get(protected_path, follow_redirects=False)
        assert_true(response.status_code in (302, 303), f"{protected_path} did not require login")

    with client:
        login(client, DEMO_PARTNER_EMAIL)

        dashboard_text = assert_ok(
            client,
            "/partner/",
            "partner dashboard",
            [
                "Add Single Actor",
                "Bulk Upload Spreadsheet",
                "View Import Batches",
                "Fix Corrections",
                "Submit Data For Review",
                "View Approved Actors",
                "Continuous Data Updates",
                "Subscription Access",
            ],
        )
        assert_true("Live Actor Registry" in dashboard_text, "Partner dashboard does not describe the live registry")

        assert_ok(
            client,
            "/partner/onboarding",
            "partner onboarding",
            ["Partner Data Owner Onboarding", "Single Actor Entry", "Bulk Upload", "Actor Self-Updates"],
        )
        assert_ok(
            client,
            "/partner/actors/new",
            "single actor form",
            ["Data Freshness Date", "Last Verified Date", "Source of Update", "Update Cycle", "Partner Notes"],
        )
        assert_ok(
            client,
            "/partner/imports",
            "partner imports",
            ["Live Actor Registry Imports", "Bulk Upload Spreadsheet"],
        )
        assert_ok(
            client,
            "/partner/imports/new",
            "partner import form",
            ["FARMER/AGGREAGATOR", "ERTIFICATION", "Preview Import"],
        )

        response = client.post(
            "/partner/imports/new",
            data={
                "title": "Validation Monthly Registry Import",
                "reporting_month": "2026-07",
                "update_cycle": "monthly",
                "data_freshness_date": "2026-07-01",
                "last_verified_date": "2026-07-01",
                "update_source": "validation_bulk_upload",
                "partner_notes": "Validation import",
                "import_file": (importer_csv(), "validation-import.csv"),
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        assert_true(response.status_code in (302, 303), "Import upload did not redirect to preview")

        with app.app_context():
            batch = PartnerUpdateBatch.query.filter_by(title="Validation Monthly Registry Import").one()
            batch_id = batch.id
            rows = import_batch_rows(batch)
            actions = {(row.after_values or {}).get("action") for row in rows}
            assert_true("create" in actions, "Import did not create a create row")
            assert_true("invalid" in actions, "Import did not create an invalid correction row")
            assert_true("update_candidate" in actions or "duplicate_warning" in actions, "Import did not detect update/duplicate candidate")
            assert_true(is_import_batch(batch), "Batch was not marked as an import batch")
            created_actor = MarketActor.query.filter_by(name="Validation Fresh Aggregator").one()
            contacts = ActorContact.query.filter_by(market_actor_id=created_actor.id).all()
            assert_true(len(contacts) == 1, "Created import actor did not get a restricted contact record")
            assert_true(contacts[0].restricted is True and contacts[0].visibility_level == "hidden", "Imported contact was not restricted")
            for change in PartnerRecordChange.query.filter_by(entity_type=IMPORT_ROW_ENTITY_TYPE).all():
                text = str(change.after_values)
                for marker in CONTACT_MARKERS:
                    assert_true(marker not in text, "Contact value leaked into row metadata")

        preview_text = assert_ok(
            client,
            f"/partner/imports/{batch_id}/preview",
            "import preview",
            ["Total Rows", "Valid Rows", "Rejected Rows", "Validation Fresh Aggregator", "Actor name is required"],
        )
        assert_true("Create" in preview_text, "Preview did not show proposed create action")

        error_response = client.get(f"/partner/imports/{batch_id}/errors.csv")
        assert_true(error_response.status_code == 200, "Error CSV route did not render")
        error_text = error_response.get_data(as_text=True)
        assert_true("Actor name is required" in error_text, "Error CSV missing correction message")
        assert_no_contact_markers(error_text, "error CSV")

        submit_response = client.post(f"/partner/imports/{batch_id}/submit", follow_redirects=False)
        assert_true(submit_response.status_code in (302, 303), "Import submit did not redirect")

        logout(client)
        login(client, "other.partner@fieldsight-demo.invalid")
        other_response = client.get(f"/partner/imports/{batch_id}", follow_redirects=False)
        assert_true(other_response.status_code == 404, "Another partner could see this import batch")

        logout(client)
        login(client, DEMO_ADMIN_EMAIL)
        assert_ok(
            client,
            "/admin/partner-imports",
            "admin partner imports",
            ["Partner Registry Imports", "Validation Monthly Registry Import", "Rejected", "Created Actors"],
        )
        assert_ok(
            client,
            f"/admin/partner-imports/{batch_id}",
            "admin partner import detail",
            ["Freshness Summary", "Import Rows", "Validation Fresh Aggregator"],
        )
        assert_ok(
            client,
            "/admin/partner-organizations",
            "admin partner organizations",
            ["Partner Organizations", "Demo Sahel Produce Network"],
        )

        with app.app_context():
            organization = PartnerOrganization.query.filter_by(slug="demo-sahel-produce-network").one()
            organization_id = organization.id
        assert_ok(
            client,
            f"/admin/partner-organizations/{organization_id}",
            "admin partner organization detail",
            ["Recent Actor Records", "Import Batches"],
        )
        assert_ok(
            client,
            f"/admin/partner-organizations/{organization_id}/users",
            "admin partner organization users",
            ["Data Owner Users", "Demo Partner Owner"],
        )
        assert_ok(
            client,
            "/subscriber/product-tour",
            "subscriber product tour contact safety",
            ["Product Tour"],
        )

    print("Partner data owner onboarding validation passed.")


if __name__ == "__main__":
    run_validation()
