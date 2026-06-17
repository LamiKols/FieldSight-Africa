"""Validate Phase 3.0 actor consent and data-sharing behavior.

This script uses an in-memory SQLite database and Flask's test client so it
does not touch Replit PostgreSQL data or real private document storage.
"""

import os
import sys
from datetime import datetime, timedelta, UTC
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SESSION_SECRET", "phase-3-0-validation-secret")
os.environ.setdefault("PRIVATE_UPLOAD_ROOT", "private_uploads")
os.environ.setdefault("DOCUMENT_STORAGE_BACKEND", "local_private")
os.environ.setdefault("MAX_DOCUMENT_UPLOAD_MB", "1")

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
    AuditLog,
    DocumentType,
    MarketActor,
    PartnerOrganization,
    PartnerUserProfile,
    User,
    actor_can_share_data,
    actor_can_share_documents,
    actor_has_active_consent,
    consent_document_category_for_document_type,
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


def granted_consent_form_data():
    return {
        "consent_status": "granted",
        "consent_method": "written",
        "consent_reference": "CONSENT-001",
        "granted_by_name": "Ada Exporter",
        "granted_by_role": "Managing Director",
        "granted_by_email": "ada@example.com",
        "granted_by_phone": "+2348000000000",
        "granted_at": "2026-06-01T10:00",
        "expires_at": "2027-06-01T00:00",
        "review_status": "pending_review",
        "review_notes": "Validation consent record",
        "consent_scope_json": [
            "store_actor_profile_data",
            "store_actor_documents",
            "share_basic_profile_with_subscribers",
            "share_document_metadata_with_subscribers",
            "include_in_paid_data_packs",
        ],
        "permitted_data_categories_json": [
            "identity_profile",
            "location",
            "crop_commodity",
            "export_profile",
        ],
        "permitted_document_categories_json": [
            "company_registration_document",
            "export_compliance_document",
        ],
        "sharing_channels_json": [
            "internal_review",
            "admin_review",
            "subscriber_portal",
            "licensed_data_pack",
        ],
    }


def make_actor(name, organization, user, actor_type="exporter"):
    actor = MarketActor(
        partner_organization_id=organization.id,
        created_by_user_id=user.id,
        updated_by_id=user.id,
        actor_type=actor_type,
        name=name,
        status="active",
    )
    db.session.add(actor)
    db.session.flush()
    return actor


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

        org = PartnerOrganization(name="Consent Partner", slug="consent-partner", status="active")
        other_org = PartnerOrganization(name="Other Consent Partner", slug="other-consent-partner", status="active")
        db.session.add_all([org, other_org])
        db.session.flush()

        editor = create_user("Consent Editor", "editor@example.com")
        ordinary = create_user("Ordinary Subscriber", "ordinary@example.com")
        other_editor = create_user("Other Editor", "other-editor@example.com")

        link_partner_user(editor, org, "data_editor")
        link_partner_user(other_editor, other_org, "data_editor")

        actor = make_actor("Consent Validation Exporter", org, editor)
        missing_actor = make_actor("Missing Consent Actor", org, editor)
        refused_actor = make_actor("Refused Consent Actor", org, editor)
        expired_actor = make_actor("Expired Consent Actor", org, editor)
        other_actor = make_actor("Other Consent Exporter", other_org, other_editor)

        document_type = DocumentType.query.filter_by(name="CAC Certificate").one()
        document = ActorDocument(
            market_actor_id=actor.id,
            partner_organization_id=org.id,
            document_type_id=document_type.id,
            uploaded_by_user_id=editor.id,
            title="Consent Validation CAC",
            document_status="submitted",
            subscriber_access_level="hidden",
            visibility_level="hidden",
            version_number=1,
        )
        db.session.add(document)

        refused_record = ActorConsentRecord(
            market_actor_id=refused_actor.id,
            partner_organization_id=org.id,
            consent_status="refused",
            consent_method="written",
            granted_by_name="Refused Actor",
            captured_by_user_id=editor.id,
            active=True,
        )
        expired_record = ActorConsentRecord(
            market_actor_id=expired_actor.id,
            partner_organization_id=org.id,
            consent_status="granted",
            consent_method="written",
            consent_scope_json=["share_basic_profile_with_subscribers"],
            permitted_data_categories_json=["identity_profile"],
            permitted_document_categories_json=["company_registration_document"],
            sharing_channels_json=["subscriber_portal"],
            granted_by_name="Expired Actor",
            granted_at=utcnow() - timedelta(days=60),
            expires_at=utcnow() - timedelta(days=1),
            captured_by_user_id=editor.id,
            active=True,
        )
        db.session.add_all([refused_record, expired_record])
        db.session.commit()

        actor_id = actor.id
        missing_actor_id = missing_actor.id
        refused_actor_id = refused_actor.id
        expired_actor_id = expired_actor.id
        other_actor_id = other_actor.id
        document_id = document.id
        document_category = consent_document_category_for_document_type(document_type)

        assert_true(actor_has_active_consent(missing_actor) is False, "Missing consent helper returned true")
        assert_true(actor_has_active_consent(refused_actor) is False, "Refused consent helper returned true")
        assert_true(actor_has_active_consent(expired_actor) is False, "Expired consent helper returned true")

    client = app.test_client()

    response = client.get(f"/partner/actors/{actor_id}/consent", follow_redirects=False)
    assert_true(response.status_code == 302 and "/login" in response.headers.get("Location", ""), "Consent route did not require login")

    with client:
        login(client, "ordinary@example.com")
        response = client.get(f"/partner/actors/{actor_id}/consent", follow_redirects=False)
        assert_true(response.status_code in (302, 303), "Ordinary subscriber accessed consent route")
        logout(client)

        login(client, "other-editor@example.com")
        response = client.get(f"/partner/actors/{actor_id}/consent", follow_redirects=False)
        assert_true(response.status_code == 404, "Cross-organization partner accessed consent history")
        response = client.get(f"/partner/actors/{actor_id}/consent/new", follow_redirects=False)
        assert_true(response.status_code == 404, "Cross-organization partner accessed consent form")
        logout(client)

        login(client, "editor@example.com")
        response = client.get(f"/partner/actors/{actor_id}")
        actor_page = response.get_data(as_text=True)
        assert_true(response.status_code == 200 and "Consent And Data Sharing" in actor_page, "Actor detail did not render consent status")
        assert_true("No active consent is recorded" in actor_page, "Actor detail did not show missing consent warning")

        response = client.get(f"/partner/documents/{document_id}")
        document_page = response.get_data(as_text=True)
        assert_true(response.status_code == 200 and "No active actor consent is recorded" in document_page, "Document detail did not show missing consent warning")

        response = client.post(
            f"/partner/actors/{actor_id}/consent/new",
            data=granted_consent_form_data(),
            follow_redirects=False,
        )
        assert_true(response.status_code in (302, 303), "Granted consent creation did not redirect after success")

        with app.app_context():
            actor = db.session.get(MarketActor, actor_id)
            consent_record = ActorConsentRecord.query.filter_by(market_actor_id=actor_id, consent_status="granted").one()
            consent_id = consent_record.id
            assert_true(actor_has_active_consent(actor) is True, "Active consent helper returned false for valid granted consent")
            assert_true(actor_can_share_data(actor, "subscriber_portal") is True, "Data sharing helper rejected valid consent")
            assert_true(actor_can_share_documents(actor, "subscriber_portal", document_category) is True, "Document sharing helper rejected valid consent")
            assert_true(AuditLog.query.filter_by(action="consent_created", entity_id=consent_id).first() is not None, "Consent create audit log was not written")

        response = client.get(f"/partner/actors/{actor_id}/consent")
        history_page = response.get_data(as_text=True)
        assert_true(response.status_code == 200 and "Consent History" in history_page and "Granted" in history_page, "Consent history page did not render granted consent")

        response = client.post(
            f"/partner/actors/{actor_id}/consent/{consent_id}/withdraw",
            data={"withdrawal_reason": "Actor withdrew data sharing permission"},
            follow_redirects=False,
        )
        assert_true(response.status_code in (302, 303), "Consent withdrawal did not redirect after success")

        with app.app_context():
            actor = db.session.get(MarketActor, actor_id)
            withdrawn_consent = db.session.get(ActorConsentRecord, consent_id)
            assert_true(withdrawn_consent.consent_status == "withdrawn", "Consent status was not set to withdrawn")
            assert_true(withdrawn_consent.withdrawn_at is not None, "Withdrawal timestamp was not set")
            assert_true(actor_has_active_consent(actor) is False, "Withdrawn consent helper returned true")
            assert_true(AuditLog.query.filter_by(action="consent_withdrawn", entity_id=consent_id).first() is not None, "Consent withdrawal audit log was not written")

        with app.app_context():
            assert_true(actor_has_active_consent(db.session.get(MarketActor, missing_actor_id)) is False, "Missing consent helper returned true after workflow")
            assert_true(actor_has_active_consent(db.session.get(MarketActor, refused_actor_id)) is False, "Refused consent helper returned true after workflow")
            assert_true(actor_has_active_consent(db.session.get(MarketActor, expired_actor_id)) is False, "Expired consent helper returned true after workflow")

        response = client.get(f"/partner/actors/{other_actor_id}", follow_redirects=False)
        assert_true(response.status_code == 404, "Partner editor accessed another organization's actor detail")
        logout(client)

    print("Phase 3.0 actor consent validation passed.")


if __name__ == "__main__":
    run_validation()
