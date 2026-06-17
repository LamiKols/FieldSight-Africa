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
    ActorCertification,
    ActorContact,
    ActorConstraint,
    ActorDocument,
    ActorDocumentVersion,
    ActorExportProfile,
    ActorLocation,
    ApiClient,
    ApiKey,
    ApiUsageEvent,
    AuditLog,
    Commodity,
    Crop,
    DocumentAccessLog,
    DocumentType,
    LGA,
    MarketActor,
    PartnerOrganization,
    PartnerRecordChange,
    PartnerUpdateBatch,
    PartnerUserProfile,
    Region,
    State,
    User,
)


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def utc_now():
    return datetime.now().replace(microsecond=0)


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
        assert_true(sensitive_doc.category == "identity", "DocumentType category was not seeded")
        assert_true("exporter" in sensitive_doc.applies_to_actor_types, "DocumentType actor applicability was not seeded")
        assert_true(sensitive_doc.requires_reference_number is True, "DocumentType reference-number requirement was not seeded")

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

        crop = Crop.query.filter_by(code="ginger").one()
        commodity = Commodity(
            crop_id=crop.id,
            code="ginger_dried_split",
            name="Dried Split Ginger",
            category="Ginger",
            active=True,
        )
        db.session.add(commodity)
        db.session.flush()

        actor = MarketActor(
            partner_organization_id=org.id,
            created_by_user_id=user.id,
            updated_by_id=user.id,
            actor_type="exporter",
            name="Validation Exporter",
            crop_id=crop.id,
            commodity_id=commodity.id,
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
            location_text="Ikeja aggregation hub",
            region_id=region.id,
            state_id=state.id,
            state_name=state.name,
            lga_id=lga.id,
            lga_name=lga.name,
            is_primary=True,
        )
        contact = ActorContact(
            market_actor_id=actor.id,
            contact_role="export_manager",
            contact_name="Restricted Contact",
            phone="+2348000000000",
            email="restricted@example.com",
            is_primary=True,
        )
        export_profile = ActorExportProfile(
            market_actor_id=actor.id,
            years_in_export_trade=5,
            trade_destination_name="United Kingdom",
            export_capacity="20",
            export_capacity_unit="MT/month",
            port_of_exit="Apapa Port",
        )
        certification = ActorCertification(
            market_actor_id=actor.id,
            certification_name="NEPC Registration",
            certificate_number="CERT-001",
            reference_number="REF-001",
            issuing_body="NEPC",
            verification_status="submitted",
            status="active",
        )
        constraint = ActorConstraint(
            market_actor_id=actor.id,
            constraint_category="logistics",
            constraint_text="Limited refrigerated transport access",
            severity="medium",
            status="active",
        )
        batch = PartnerUpdateBatch(
            partner_organization_id=org.id,
            title="June actor registry update",
            submitted_by_user_id=user.id,
            reviewed_by_user_id=user.id,
            dataset_type="actor_registry",
            reporting_month="2026-06",
            status="draft",
            reviewed_at=utc_now(),
            review_comments="Validation review comment",
            published_at=utc_now(),
        )
        db.session.add_all([location, contact, export_profile, certification, constraint, batch])
        db.session.flush()

        record_change = PartnerRecordChange(
            partner_update_batch_id=batch.id,
            market_actor_id=actor.id,
            created_by_user_id=user.id,
            entity_type="market_actor",
            entity_id=actor.id,
            change_type="create",
            after_values={"name": actor.name},
            status="draft",
        )
        db.session.add(record_change)

        document_type = DocumentType.query.filter_by(code="cac_certificate").one()
        document = ActorDocument(
            market_actor_id=actor.id,
            partner_organization_id=org.id,
            document_type_id=document_type.id,
            uploaded_by_user_id=user.id,
            title="CAC Certificate metadata",
            original_filename="cac-certificate.pdf",
            stored_filename="cac-certificate-v1.pdf",
            storage_path="private_uploads/validation/cac-certificate-v1.pdf",
            mime_type="application/pdf",
            file_size=1024,
            file_hash="a" * 64,
            version_number=1,
            document_reference_number="CAC-12345",
            issuing_body="Corporate Affairs Commission",
            linked_crop_id=crop.id,
            linked_commodity_id=commodity.id,
            document_status="draft",
            verification_status="unverified",
            redaction_status="not_redacted",
            subscriber_access_level=document_type.default_visibility_level,
            review_status="pending",
            reviewed_by_user_id=user.id,
            reviewed_at=utc_now(),
            review_comments="Validation document review",
            visibility_level=document_type.default_visibility_level,
            is_current_version=True,
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
        db.session.flush()

        document_access_log = DocumentAccessLog(
            actor_document_id=document.id,
            actor_document_version_id=version.id,
            user_id=user.id,
            api_client_id=client.id,
            access_type="metadata_view",
            access_channel="validation_script",
            subscriber_organization_name="Validation Subscriber",
            visibility_level=document.visibility_level,
            ip_address="127.0.0.1",
            user_agent="phase-1-validation",
        )
        db.session.add(document_access_log)

        api_usage_event = ApiUsageEvent(
            api_client_id=client.id,
            api_key_id=api_key.id,
            user_id=user.id,
            endpoint="/future/api/actor-registry",
            method="GET",
            dataset_type="actor_registry",
            snapshot_month="2026-06",
            filters_json={"region": "SW", "crop": "Ginger"},
            row_count=1,
            status_code=200,
            units=1,
        )
        db.session.add(api_usage_event)

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
            created_at=utc_now(),
        )
        db.session.add(audit_log)
        db.session.commit()

        assert_true(PartnerOrganization.query.filter_by(slug="validation-partner").first() is not None, "PartnerOrganization was not created")
        assert_true(PartnerUserProfile.query.filter_by(user_id=user.id).first() is not None, "PartnerUserProfile was not linked to User")
        assert_true(MarketActor.query.filter_by(name="Validation Exporter").first() is not None, "MarketActor was not created")
        assert_true(actor.public_id and actor.public_id != str(actor.id), "MarketActor public_id was not generated")
        assert_true(actor.crop_id == crop.id, "MarketActor crop_id was not stored")
        assert_true(actor.updated_by_id == user.id, "MarketActor updated_by_id was not stored")
        assert_true(location.region_id == region.id and location.is_primary is True, "ActorLocation region/is_primary fields were not stored")
        assert_true(location.location_text == location.location, "ActorLocation location_text was not stored")
        assert_true(contact.restricted is True, "ActorContact is not restricted by default")
        assert_true(contact.contact_role == "export_manager" and contact.is_primary is True, "ActorContact role/is_primary fields were not stored")
        assert_true(export_profile.export_capacity_unit == "MT/month", "ActorExportProfile export_capacity_unit was not stored")
        assert_true(certification.issuing_body == "NEPC", "ActorCertification issuing_body was not stored")
        assert_true(certification.reference_number == "REF-001", "ActorCertification reference_number was not stored")
        assert_true(certification.status == "active", "ActorCertification status was not stored")
        assert_true(constraint.constraint_category == "logistics", "ActorConstraint category was not stored")
        assert_true(batch.title == "June actor registry update", "PartnerUpdateBatch title was not stored")
        assert_true(batch.reviewed_by_user_id == user.id and batch.reviewed_at is not None, "PartnerUpdateBatch review fields were not stored")
        assert_true(batch.review_comments == "Validation review comment" and batch.published_at is not None, "PartnerUpdateBatch comments/published_at were not stored")
        assert_true(record_change.market_actor_id == actor.id and record_change.created_by_user_id == user.id, "PartnerRecordChange actor/creator fields were not stored")
        assert_true(document.original_filename == "cac-certificate.pdf", "ActorDocument original filename was not stored")
        assert_true(document.stored_filename == "cac-certificate-v1.pdf", "ActorDocument stored filename was not stored")
        assert_true(document.storage_path.startswith("private_uploads/"), "ActorDocument private storage path was not stored")
        assert_true(document.mime_type == "application/pdf", "ActorDocument MIME type was not stored")
        assert_true(document.file_size == 1024 and document.file_hash == "a" * 64, "ActorDocument file metadata was not stored")
        assert_true(document.document_reference_number == "CAC-12345", "ActorDocument reference number was not stored")
        assert_true(document.issuing_body == "Corporate Affairs Commission", "ActorDocument issuing body was not stored")
        assert_true(document.linked_crop_id == crop.id and document.linked_commodity_id == commodity.id, "ActorDocument crop/commodity links were not stored")
        assert_true(document.redaction_status == "not_redacted", "ActorDocument redaction status was not stored")
        assert_true(document.subscriber_access_level == document_type.default_visibility_level, "ActorDocument subscriber access level was not stored")
        assert_true(document.review_status == "pending", "ActorDocument review status was not stored")
        assert_true(document.reviewed_by_user_id == user.id and document.reviewed_at is not None, "ActorDocument review user/date fields were not stored")
        assert_true(document.is_current_version is True, "ActorDocument current-version flag was not stored")
        assert_true(ActorDocumentVersion.query.filter_by(actor_document_id=document.id).first() is not None, "ActorDocumentVersion was not created")
        assert_true(ApiClient.query.filter_by(slug="validation-api-client").first() is not None, "ApiClient was not created")
        assert_true(api_key.key_prefix == raw_secret[:8], "ApiKey prefix was not stored correctly")
        assert_true(api_key.key_hash != raw_secret, "ApiKey stored raw secret instead of a hash")
        assert_true(not hasattr(api_key, "raw_secret"), "ApiKey exposes a raw_secret attribute")
        assert_true(document_access_log.api_client_id == client.id, "DocumentAccessLog api_client_id was not stored")
        assert_true(document_access_log.access_channel == "validation_script", "DocumentAccessLog access_channel was not stored")
        assert_true(document_access_log.subscriber_organization_name == "Validation Subscriber", "DocumentAccessLog subscriber organization was not stored")
        assert_true(api_usage_event.user_id == user.id, "ApiUsageEvent user_id was not stored")
        assert_true(api_usage_event.dataset_type == "actor_registry", "ApiUsageEvent dataset_type was not stored")
        assert_true(api_usage_event.snapshot_month == "2026-06", "ApiUsageEvent snapshot_month was not stored")
        assert_true(api_usage_event.filters_json["region"] == "SW", "ApiUsageEvent filters_json was not stored")
        assert_true(api_usage_event.row_count == 1, "ApiUsageEvent row_count was not stored")
        assert_true(AuditLog.query.filter_by(action="validate_phase_1_foundation").first() is not None, "AuditLog was not created")

    print("Phase 1 data foundation validation passed.")


if __name__ == "__main__":
    run_validation()
