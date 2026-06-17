"""Validate Phase 1 data foundation models and seed idempotency.

This script is intentionally lightweight because the existing repository does
not include a test framework yet. It uses an in-memory SQLite database so it
does not touch Replit PostgreSQL data.
"""

import os
import sys
from datetime import date, datetime
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SESSION_SECRET", "phase-1-validation-secret")
os.environ.setdefault("PRIVATE_UPLOAD_ROOT", "private_uploads")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app import (  # noqa: E402
    app,
    db,
    DOCUMENT_TYPE_NAMES,
    REFERENCE_CROPS,
    REFERENCE_REGIONS,
    seed_datasets,
    seed_document_types,
    seed_licensed_packs,
    seed_payment_plans,
    seed_reference_data,
)
from models import (  # noqa: E402
    ActorContact,
    ActorDocument,
    ActorDocumentVersion,
    ActorExportProfile,
    ActorLocation,
    ApiClient,
    ApiKey,
    AuditLog,
    Crop,
    DocumentType,
    LGA,
    MarketActor,
    PartnerOrganization,
    PartnerUpdateBatch,
    PartnerUserProfile,
    Region,
    State,
    User,
)


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def run_validation():
    with app.app_context():
        db.drop_all()
        db.create_all()

        seed_payment_plans()
        seed_datasets()
        seed_licensed_packs()
        seed_reference_data()
        seed_document_types()
        seed_reference_data()
        seed_document_types()

        assert_true(Region.query.count() == len(REFERENCE_REGIONS), "Region seed is not idempotent")
        assert_true(Crop.query.count() == len(REFERENCE_CROPS), "Crop seed is not idempotent")
        assert_true(DocumentType.query.count() == len(DOCUMENT_TYPE_NAMES), "Document type seed is not idempotent")

        sensitive_doc = DocumentType.query.filter_by(code="national_id").one()
        assert_true(sensitive_doc.sensitive is True, "Sensitive document type was not marked sensitive")
        assert_true(sensitive_doc.default_visibility_level == "hidden", "Sensitive document type is not restricted")

        org = PartnerOrganization(
            name="Validation Partner",
            slug="validation-partner",
            contact_name="Validation Lead",
            contact_email="lead@example.com",
            country="Nigeria",
            status="active",
        )
        db.session.add(org)

        user = User(name="Partner User", email="partner@example.com", role="subscriber")
        user.set_password("validation-password")
        db.session.add(user)
        db.session.flush()

        profile = PartnerUserProfile(
            user_id=user.id,
            partner_organization_id=org.id,
            partner_role="partner_admin",
            status="active",
        )
        db.session.add(profile)

        region = Region.query.filter_by(code="SW").one()
        state = State(region_id=region.id, code="LA", name="Lagos", active=True)
        db.session.add(state)
        db.session.flush()

        lga = LGA(state_id=state.id, name="Ikeja", active=True)
        db.session.add(lga)

        actor = MarketActor(
            partner_organization_id=org.id,
            created_by_user_id=user.id,
            actor_type="exporter",
            name="Validation Exporter",
            commodity_category="Ginger",
            registration_status="registered",
            date_of_registration=date(2026, 1, 15),
            status="active",
        )
        db.session.add(actor)
        db.session.flush()

        location = ActorLocation(
            market_actor_id=actor.id,
            location="Ikeja aggregation hub",
            state_id=state.id,
            state_name=state.name,
            lga_id=lga.id,
            lga_name=lga.name,
        )
        contact = ActorContact(
            market_actor_id=actor.id,
            contact_name="Restricted Contact",
            phone="+2348000000000",
            email="restricted@example.com",
        )
        export_profile = ActorExportProfile(
            market_actor_id=actor.id,
            years_in_export_trade=5,
            trade_destination_name="United Kingdom",
            export_capacity="20 MT/month",
            port_of_exit="Apapa Port",
        )
        batch = PartnerUpdateBatch(
            partner_organization_id=org.id,
            submitted_by_user_id=user.id,
            dataset_type="actor_registry",
            reporting_month="2026-06",
            status="draft",
        )
        db.session.add_all([location, contact, export_profile, batch])

        document_type = DocumentType.query.filter_by(code="cac_certificate").one()
        document = ActorDocument(
            market_actor_id=actor.id,
            partner_organization_id=org.id,
            document_type_id=document_type.id,
            title="CAC Certificate metadata",
            document_status="draft",
            verification_status="unverified",
            visibility_level=document_type.default_visibility_level,
        )
        db.session.add(document)
        db.session.flush()

        version = ActorDocumentVersion(
            actor_document_id=document.id,
            version_number=1,
            storage_backend="local_private",
            storage_path="private_uploads/validation/cac-certificate.pdf",
            original_filename="cac-certificate.pdf",
            content_type="application/pdf",
            file_size_bytes=1024,
            uploaded_by_user_id=user.id,
        )
        db.session.add(version)

        client = ApiClient(
            name="Validation API Client",
            slug="validation-api-client",
            owner_user_id=user.id,
            partner_organization_id=org.id,
            status="active",
            scopes=["actor_registry:read"],
        )
        db.session.add(client)
        db.session.flush()

        raw_secret = "fsa_validation_secret_1234567890"
        api_key = ApiKey(
            api_client_id=client.id,
            name="Validation key",
            scopes=["actor_registry:read"],
        )
        api_key.set_secret(raw_secret)
        db.session.add(api_key)

        audit_log = AuditLog(
            user_id=user.id,
            organization_type="partner_organization",
            organization_id=org.id,
            action="validate_phase_1_foundation",
            entity_type="market_actor",
            entity_id=actor.id,
            before_values=None,
            after_values={"status": "created"},
            ip_address="127.0.0.1",
            user_agent="phase-1-validation",
            created_at=datetime.utcnow(),
        )
        db.session.add(audit_log)
        db.session.commit()

        assert_true(PartnerOrganization.query.filter_by(slug="validation-partner").first() is not None, "PartnerOrganization was not created")
        assert_true(PartnerUserProfile.query.filter_by(user_id=user.id).first() is not None, "PartnerUserProfile was not linked to User")
        assert_true(MarketActor.query.filter_by(name="Validation Exporter").first() is not None, "MarketActor was not created")
        assert_true(ActorContact.query.filter_by(market_actor_id=actor.id).first().restricted is True, "ActorContact is not restricted by default")
        assert_true(ActorExportProfile.query.filter_by(market_actor_id=actor.id).first() is not None, "ActorExportProfile was not created")
        assert_true(PartnerUpdateBatch.query.filter_by(dataset_type="actor_registry").first() is not None, "PartnerUpdateBatch was not created")
        assert_true(ActorDocument.query.filter_by(title="CAC Certificate metadata").first() is not None, "ActorDocument metadata was not created")
        assert_true(ActorDocumentVersion.query.filter_by(actor_document_id=document.id).first() is not None, "ActorDocumentVersion was not created")
        assert_true(ApiClient.query.filter_by(slug="validation-api-client").first() is not None, "ApiClient was not created")
        assert_true(api_key.key_prefix == raw_secret[:8], "ApiKey prefix was not stored correctly")
        assert_true(api_key.key_hash != raw_secret, "ApiKey stored raw secret instead of a hash")
        assert_true(not hasattr(api_key, "raw_secret"), "ApiKey exposes a raw_secret attribute")
        assert_true(AuditLog.query.filter_by(action="validate_phase_1_foundation").first() is not None, "AuditLog was not created")

    print("Phase 1 data foundation validation passed.")


if __name__ == "__main__":
    run_validation()
