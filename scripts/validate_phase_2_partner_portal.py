"""Validate Phase 2 partner portal behavior.

This script uses an in-memory SQLite database and Flask's test client so it
does not touch Replit PostgreSQL data.
"""

import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SESSION_SECRET", "phase-2-validation-secret")
os.environ.setdefault("PRIVATE_UPLOAD_ROOT", "private_uploads")
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
)
from models import (  # noqa: E402
    ActorContact,
    ActorConstraint,
    ActorExportProfile,
    AuditLog,
    Crop,
    MarketActor,
    PartnerOrganization,
    PartnerRecordChange,
    PartnerUpdateBatch,
    PartnerUserProfile,
    User,
)
from routes.partner import get_partner_profile_for_user  # noqa: E402


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def create_user(name, email, password="validation-password"):
    user = User(name=name, email=email, role="subscriber")
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


def actor_form_data(crop_id, name="Validation Exporter"):
    return {
        "name": name,
        "actor_type": "exporter",
        "crop_id": str(crop_id),
        "commodity_category": "Ginger",
        "registration_status": "registered",
        "date_of_registration": "2026-06-01",
        "status": "active",
        "source_reference": "validation-template-row-1",
        "region_id": "",
        "state_name": "Lagos",
        "lga_name": "Ikeja",
        "location_text": "Ikeja aggregation hub",
        "contact_role": "export_manager",
        "contact_name": "Restricted Contact",
        "contact_phone": "+2348000000000",
        "contact_email": "restricted@example.com",
        "contact_restricted": "true",
        "years_in_export_trade": "5",
        "trade_destination_name": "United Kingdom",
        "export_capacity": "20",
        "export_capacity_unit": "MT/month",
        "port_of_exit": "Apapa Port",
        "certification_name": "NEPC Registration",
        "certificate_number": "CERT-001",
        "reference_number": "REF-001",
        "issuing_body": "NEPC",
        "constraint_category": "logistics",
        "constraint_text": "Limited refrigerated transport access",
        "constraint_severity": "medium",
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

        org = PartnerOrganization(name="Validation Partner", slug="validation-partner", status="active")
        other_org = PartnerOrganization(name="Other Partner", slug="other-partner", status="active")
        db.session.add_all([org, other_org])
        db.session.flush()

        partner_admin = create_user("Partner Admin", "partner-admin@example.com")
        partner_viewer = create_user("Partner Viewer", "partner-viewer@example.com")
        ordinary_user = create_user("Ordinary User", "ordinary@example.com")
        other_partner_admin = create_user("Other Partner Admin", "other-admin@example.com")

        link_partner_user(partner_admin, org, "partner_admin")
        link_partner_user(partner_viewer, org, "partner_viewer")
        link_partner_user(other_partner_admin, other_org, "partner_admin")
        db.session.commit()

        assert_true(PartnerOrganization.query.filter_by(slug="validation-partner").first() is not None, "Partner organization was not created")
        assert_true(PartnerUserProfile.query.filter_by(user_id=partner_admin.id).first() is not None, "User was not linked to partner organization")

        profile = get_partner_profile_for_user(partner_admin)
        assert_true(profile is not None, "Partner helper did not find active profile")
        assert_true(profile.partner_organization_id == org.id, "Partner helper returned the wrong organization")

        crop = Crop.query.filter_by(code="ginger").one()

        other_actor = MarketActor(
            partner_organization_id=other_org.id,
            created_by_user_id=other_partner_admin.id,
            updated_by_id=other_partner_admin.id,
            actor_type="exporter",
            name="Other Organization Exporter",
            status="active",
        )
        db.session.add(other_actor)
        db.session.commit()
        org_id = org.id
        crop_id = crop.id
        other_actor_id = other_actor.id

    client = app.test_client()

    response = client.get("/partner/actors", follow_redirects=False)
    assert_true(response.status_code == 302 and "/login" in response.headers.get("Location", ""), "Actor list did not require login")

    with client:
        login(client, "ordinary@example.com")
        response = client.get("/partner/", follow_redirects=False)
        assert_true(response.status_code in (302, 303), "Ordinary subscriber without partner profile accessed partner portal")
        logout(client)

        login(client, "partner-admin@example.com")
        response = client.post("/partner/actors/new", data=actor_form_data(crop_id), follow_redirects=False)
        assert_true(response.status_code in (302, 303), "Actor creation route did not redirect after success")

        with app.app_context():
            actor = MarketActor.query.filter_by(name="Validation Exporter").one()
            assert_true(actor.partner_organization_id == org_id, "Actor was not attached to partner organization")
            assert_true(actor.location is not None and actor.location.state_name == "Lagos", "Actor location was not created")
            assert_true(ActorContact.query.filter_by(market_actor_id=actor.id).first() is not None, "Actor contact was not created")
            assert_true(ActorExportProfile.query.filter_by(market_actor_id=actor.id).first() is not None, "Actor export profile was not created")
            assert_true(ActorConstraint.query.filter_by(market_actor_id=actor.id).first() is not None, "Actor constraint was not created")
            assert_true(PartnerRecordChange.query.filter_by(market_actor_id=actor.id, change_type="create").first() is not None, "Actor create change was not recorded")

        response = client.get("/partner/actors")
        page = response.get_data(as_text=True)
        assert_true("+2348000000000" not in page and "restricted@example.com" not in page, "Actor list exposed restricted contact fields")

        response = client.get(f"/partner/actors/{other_actor_id}", follow_redirects=False)
        assert_true(response.status_code == 404, "Actor detail allowed cross-organization access")
        response = client.get(f"/partner/actors/{other_actor_id}/edit", follow_redirects=False)
        assert_true(response.status_code == 404, "Actor edit allowed cross-organization access")

        with app.app_context():
            actor = MarketActor.query.filter_by(name="Validation Exporter").one()
            actor_id = actor.id

        edit_data = actor_form_data(crop_id, name="Validation Exporter Updated")
        response = client.post(f"/partner/actors/{actor_id}/edit", data=edit_data, follow_redirects=False)
        assert_true(response.status_code in (302, 303), "Actor edit route did not redirect after success")

        response = client.post(
            "/partner/batches/new",
            data={"title": "June actor registry update", "dataset_type": "actor_registry", "reporting_month": "2026-06", "notes": "Validation batch"},
            follow_redirects=False,
        )
        assert_true(response.status_code in (302, 303), "Batch creation route did not redirect after success")

        with app.app_context():
            actor = MarketActor.query.filter_by(name="Validation Exporter Updated").one()
            batch = PartnerUpdateBatch.query.filter_by(title="June actor registry update").one()
            batch_id = batch.id
            assert_true(batch.status == "draft", "Batch was not created in draft status")
            assert_true(PartnerRecordChange.query.filter_by(market_actor_id=actor.id, change_type="update").first() is not None, "Actor update change was not recorded")

        response = client.post(f"/partner/batches/{batch_id}/submit", follow_redirects=False)
        assert_true(response.status_code in (302, 303), "Batch submit route did not redirect after success")

        with app.app_context():
            submitted_batch = db.session.get(PartnerUpdateBatch, batch_id)
            assert_true(submitted_batch.status == "submitted", "Draft batch was not submitted")
            assert_true(submitted_batch.submitted_at is not None, "Submitted batch timestamp was not set")
            assert_true(AuditLog.query.filter_by(action="partner_actor_created").first() is not None, "Actor create audit log was not written")
            assert_true(AuditLog.query.filter_by(action="partner_actor_updated").first() is not None, "Actor update audit log was not written")
            assert_true(AuditLog.query.filter_by(action="partner_batch_submitted").first() is not None, "Batch submit audit log was not written")

        logout(client)

        login(client, "partner-viewer@example.com")
        with app.app_context():
            actor = MarketActor.query.filter_by(name="Validation Exporter Updated").one()
            actor_id = actor.id
        response = client.get(f"/partner/actors/{actor_id}")
        detail_page = response.get_data(as_text=True)
        assert_true("+2348000000000" not in detail_page, "Viewer saw restricted phone field")
        assert_true("restricted@example.com" not in detail_page, "Viewer saw restricted email field")
        logout(client)

    print("Phase 2 partner portal validation passed.")


if __name__ == "__main__":
    run_validation()
