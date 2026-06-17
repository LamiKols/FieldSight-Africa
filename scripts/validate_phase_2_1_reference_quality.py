"""Validate Phase 2.1 reference options and actor quality scoring.

This script uses an in-memory SQLite database and Flask's test client so it
does not touch Replit PostgreSQL data.
"""

import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SESSION_SECRET", "phase-2-1-validation-secret")
os.environ.setdefault("PRIVATE_UPLOAD_ROOT", "private_uploads")
os.environ.setdefault("DOCUMENT_STORAGE_BACKEND", "local_private")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app import (  # noqa: E402
    REFERENCE_OPTIONS,
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
    ActorCertification,
    ActorContact,
    ActorConstraint,
    ActorExportProfile,
    ActorLocation,
    CertificationType,
    Commodity,
    Crop,
    LGA,
    MarketActor,
    PartnerOrganization,
    PartnerRecordChange,
    PartnerUserProfile,
    Port,
    ReferenceOption,
    Region,
    State,
    TradeDestination,
    User,
    calculate_actor_quality_score,
)


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def create_user(name, email, role="subscriber", password="validation-password"):
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


def actor_form_data(crop_id, state_id=None, lga_id=None, commodity_id=None, destination_id=None, port_id=None, certification_type_id=None, name="Dropdown Quality Exporter"):
    return {
        "name": name,
        "actor_type": "exporter",
        "crop_id": str(crop_id),
        "commodity_id": str(commodity_id or ""),
        "commodity_category": "Ginger",
        "registration_status": "registered",
        "date_of_registration": "2026-06-01",
        "status": "active",
        "source_reference_type": "partner_field_report",
        "source_reference": "validation-source-1",
        "region_id": "",
        "state_id": str(state_id or ""),
        "state_name": "Lagos",
        "lga_id": str(lga_id or ""),
        "lga_name": "Ikeja",
        "location_text": "Ikeja aggregation hub",
        "contact_role": "export_manager",
        "contact_name": "Restricted Contact",
        "contact_phone": "+2348000000000",
        "contact_email": "restricted@example.com",
        "contact_restricted": "true",
        "years_in_export_trade": "5",
        "trade_destination_id": str(destination_id or ""),
        "trade_destination_name": "United Kingdom",
        "export_capacity": "20",
        "export_capacity_unit": "mt_month",
        "port_id": str(port_id or ""),
        "port_of_exit": "Apapa Port",
        "certification_type_id": str(certification_type_id or ""),
        "certification_name": "NEPC Registration",
        "certificate_number": "CERT-001",
        "reference_number": "REF-001",
        "issuing_body": "NEPC",
        "certification_verification_status": "verified",
        "certification_status": "active",
        "constraint_category": "logistics",
        "constraint_text": "Limited refrigerated transport access",
        "constraint_severity": "medium",
        "constraint_status": "active",
        "batch_id": "",
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
        seed_reference_options()

        expected_options = sum(len(options) for options in REFERENCE_OPTIONS.values())
        assert_true(ReferenceOption.query.count() == expected_options, "Reference option seed is not idempotent")

        custom_option = ReferenceOption(
            category="contact_role",
            code="validation_contact",
            label="Validation Contact",
            active=True,
        )
        db.session.add(custom_option)

        admin = create_user("Admin User", "admin@example.com", role="admin")
        ordinary = create_user("Ordinary User", "ordinary@example.com")
        partner_user = create_user("Partner User", "partner@example.com")
        org = PartnerOrganization(name="Validation Partner", slug="validation-partner", status="active")
        db.session.add(org)
        db.session.flush()
        db.session.add(PartnerUserProfile(
            user_id=partner_user.id,
            partner_organization_id=org.id,
            partner_role="partner_admin",
            status="active",
        ))

        region = Region.query.filter_by(code="SW").one()
        state = State(region_id=region.id, code="LA", name="Lagos", active=True)
        db.session.add(state)
        db.session.flush()
        lga = LGA(state_id=state.id, name="Ikeja", active=True)
        crop = Crop.query.filter_by(code="ginger").one()
        commodity = Commodity(crop_id=crop.id, code="ginger_split", name="Split Ginger", category="Ginger", active=True)
        destination = TradeDestination(code="uk", name="United Kingdom", country="United Kingdom", active=True)
        port = Port(code="apapa", name="Apapa Port", country="Nigeria", active=True)
        certification_type = CertificationType(code="nepc", name="NEPC Registration", active=True)
        db.session.add_all([lga, commodity, destination, port, certification_type])

        sparse_actor = MarketActor(
            partner_organization_id=org.id,
            created_by_user_id=partner_user.id,
            updated_by_id=partner_user.id,
            actor_type="exporter",
            name="Sparse Actor",
            status="active",
        )
        db.session.add(sparse_actor)
        db.session.commit()

        assert_true(ReferenceOption.query.filter_by(category="contact_role", code="validation_contact").first() is not None, "ReferenceOption model could not create a custom row")

    client = app.test_client()

    with client:
        login(client, "ordinary@example.com")
        response = client.get("/admin/reference-options", follow_redirects=False)
        assert_true(response.status_code in (302, 303), "Ordinary user accessed admin reference options")
        logout(client)

        login(client, "admin@example.com")
        response = client.get("/admin/reference-options")
        assert_true(response.status_code == 200 and "Reference Options" in response.get_data(as_text=True), "Admin reference options list did not render")
        response = client.get("/admin/reference-options/new")
        assert_true(response.status_code == 200 and "New Reference Option" in response.get_data(as_text=True), "Admin new reference option form did not render")
        response = client.post(
            "/admin/reference-options/new",
            data={
                "category": "constraint_status",
                "code": "validation_status",
                "label": "Validation Status",
                "description": "Created by validation",
                "sort_order": "99",
                "active": "true",
                "metadata_json": "{\"source\":\"validation\"}",
            },
            follow_redirects=False,
        )
        assert_true(response.status_code in (302, 303), "Admin could not create reference option")
        with app.app_context():
            option = ReferenceOption.query.filter_by(category="constraint_status", code="validation_status").one()
            option_id = option.id

        response = client.get(f"/admin/reference-options/{option_id}/edit")
        assert_true(response.status_code == 200 and "Edit Reference Option" in response.get_data(as_text=True), "Admin edit reference option form did not render")
        response = client.post(
            f"/admin/reference-options/{option_id}/edit",
            data={
                "label": "Validation Status Updated",
                "description": "Updated by validation",
                "sort_order": "100",
                "active": "true",
                "is_default": "true",
                "metadata_json": "{\"source\":\"validation\",\"updated\":true}",
            },
            follow_redirects=False,
        )
        assert_true(response.status_code in (302, 303), "Admin could not edit reference option")
        with app.app_context():
            option = db.session.get(ReferenceOption, option_id)
            assert_true(option.label == "Validation Status Updated", "Reference option edit did not persist")
            assert_true(option.is_default is True, "Reference option default flag did not persist")
        logout(client)

        login(client, "partner@example.com")
        response = client.get("/partner/actors/new")
        assert_true(response.status_code == 200 and "Source Reference Type" in response.get_data(as_text=True), "Partner actor form did not render reference dropdowns")
        with app.app_context():
            crop_id = Crop.query.filter_by(code="ginger").one().id
            state_id = State.query.filter_by(name="Lagos").one().id
            lga_id = LGA.query.filter_by(name="Ikeja").one().id
            commodity_id = Commodity.query.filter_by(code="ginger_split").one().id
            destination_id = TradeDestination.query.filter_by(code="uk").one().id
            port_id = Port.query.filter_by(code="apapa").one().id
            certification_type_id = CertificationType.query.filter_by(code="nepc").one().id

        response = client.post(
            "/partner/actors/new",
            data=actor_form_data(crop_id, state_id, lga_id, commodity_id, destination_id, port_id, certification_type_id),
            follow_redirects=False,
        )
        assert_true(response.status_code in (302, 303), "Partner actor form could not create actor with dropdown values")

        response = client.post(
            "/partner/actors/new",
            data=actor_form_data(crop_id, name="Fallback Text Exporter"),
            follow_redirects=False,
        )
        assert_true(response.status_code in (302, 303), "Partner actor form fallback text submission failed")

        with app.app_context():
            dropdown_actor = MarketActor.query.filter_by(name="Dropdown Quality Exporter").one()
            assert_true(dropdown_actor.source_reference_type == "partner_field_report", "Source reference type was not saved")
            assert_true(dropdown_actor.commodity_id == commodity_id, "Commodity dropdown value was not saved")
            assert_true(dropdown_actor.location.state_id == state_id and dropdown_actor.location.lga_id == lga_id, "State/LGA dropdown values were not saved")
            assert_true(dropdown_actor.export_profile.trade_destination_id == destination_id and dropdown_actor.export_profile.port_id == port_id, "Destination/port dropdown values were not saved")
            assert_true(dropdown_actor.certifications[0].certification_type_id == certification_type_id, "Certification type dropdown value was not saved")

            fallback_actor = MarketActor.query.filter_by(name="Fallback Text Exporter").one()
            assert_true(fallback_actor.location.state_name == "Lagos" and fallback_actor.export_profile.trade_destination_name == "United Kingdom", "Free-text fallback values were not saved")

            sparse_actor = MarketActor.query.filter_by(name="Sparse Actor").one()
            sparse_score = calculate_actor_quality_score(sparse_actor)
            full_score = calculate_actor_quality_score(dropdown_actor)
            assert_true(sparse_score["score"] < 40 and sparse_score["grade"] == "low", "Sparse actor did not receive low quality score")
            assert_true(full_score["score"] > sparse_score["score"], "Full actor quality score did not increase")
            assert_true(full_score["grade"] in ("high", "complete"), "Full actor did not receive high quality grade")
            assert_true(PartnerRecordChange.query.filter_by(market_actor_id=dropdown_actor.id).first() is not None, "Dropdown actor did not create PartnerRecordChange")
            sparse_actor_id = sparse_actor.id

        response = client.get("/partner/actors")
        page = response.get_data(as_text=True)
        assert_true("Quality" in page, "Actor registry list did not render quality score")
        assert_true("+2348000000000" not in page and "restricted@example.com" not in page, "Actor list exposed restricted contact fields")

        response = client.get(f"/partner/actors/{sparse_actor_id}")
        detail_page = response.get_data(as_text=True)
        assert_true("Missing Sections" in detail_page and "missing contact" in detail_page.lower(), "Actor detail did not render missing sections")
        logout(client)

    print("Phase 2.1 reference options and quality validation passed.")


if __name__ == "__main__":
    run_validation()
