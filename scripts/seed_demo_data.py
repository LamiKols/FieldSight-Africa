"""Seed safe synthetic demo data for local FieldSight Africa walkthroughs.

This script is intentionally local/demo oriented. It creates synthetic records
that make the commercial, document, actor, and intelligence workflows easier to
show without granting paid access, creating files, storing private paths, or
changing payment provider behaviour.
"""

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app import app  # noqa: E402
from intelligence_engine import (  # noqa: E402
    create_manual_ingestion_run,
    create_publication_candidate_from_alert,
    update_alert_review,
    update_publication_candidate,
)
from models import (  # noqa: E402
    ActorCertification,
    ActorConsentRecord,
    ActorConstraint,
    ActorDocument,
    ActorExportProfile,
    ActorLocation,
    CommercialRequest,
    Crop,
    DocumentAccessRequest,
    DocumentAutomationRun,
    DocumentPublishControl,
    DocumentType,
    IntelligenceAlert,
    IntelligenceIngestionRun,
    IntelligencePublicationCandidate,
    IntelligenceSource,
    MarketActor,
    PartnerOrganization,
    PartnerUpdateBatch,
    PartnerUserProfile,
    Region,
    SubscriberIntelligenceDigest,
    User,
    consent_document_category_for_document_type,
    db,
)
from routes.partner_imports import create_import_batch_from_rows, import_batch_summary, is_import_batch  # noqa: E402


DEMO_ADMIN_EMAIL = "demo.admin@fieldsight-demo.invalid"
DEMO_SUBSCRIBER_EMAIL = "demo.subscriber@fieldsight-demo.invalid"
DEMO_PARTNER_EMAIL = "demo.partner-owner@fieldsight-demo.invalid"
DEMO_PASSWORD = "demo-validation-password"
DEMO_PARTNER_SLUG = "demo-sahel-produce-network"
DEMO_ACTOR_PUBLIC_ID = "demo-actor-sahel-0001"
DEMO_DOCUMENT_TITLE = "Demo Certificate Of Origin Metadata"
DEMO_IMPORT_TITLE = "Demo Monthly Live Actor Registry Import"


def utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


def get_or_create_user(name, email, role):
    user = User.query.filter_by(email=email).first()
    if user:
        if user.name != name:
            user.name = name
        if user.role != role:
            user.role = role
        return user

    user = User(name=name, email=email, role=role)
    user.set_password(DEMO_PASSWORD)
    db.session.add(user)
    db.session.flush()
    return user


def get_or_create_partner():
    partner = PartnerOrganization.query.filter_by(slug=DEMO_PARTNER_SLUG).first()
    if partner:
        partner.status = "active"
        partner.contact_name = None
        partner.contact_email = None
        partner.contact_phone = None
        return partner

    partner = PartnerOrganization(
        name="Demo Sahel Produce Network",
        slug=DEMO_PARTNER_SLUG,
        description="Synthetic partner organization used for local commercial demos.",
        country="Nigeria",
        status="active",
    )
    db.session.add(partner)
    db.session.flush()
    return partner


def get_or_create_partner_profile(user, partner, partner_role="partner_admin"):
    profile = PartnerUserProfile.query.filter_by(
        user_id=user.id,
        partner_organization_id=partner.id,
    ).first()
    if not profile:
        profile = PartnerUserProfile(
            user_id=user.id,
            partner_organization_id=partner.id,
            partner_role=partner_role,
            status="active",
        )
        db.session.add(profile)
    profile.partner_role = partner_role
    profile.status = "active"
    db.session.flush()
    return profile


def first_or_create_crop():
    crop = Crop.query.filter_by(name="Ginger").first()
    if crop:
        return crop
    crop = Crop(code="ginger", name="Ginger", active=True)
    db.session.add(crop)
    db.session.flush()
    return crop


def first_or_create_region():
    region = Region.query.filter_by(code="SW").first()
    if region:
        return region
    region = Region(code="SW", name="South West", country="Nigeria", active=True)
    db.session.add(region)
    db.session.flush()
    return region


def first_or_create_document_type():
    document_type = DocumentType.query.filter_by(name="Certificate of Origin").first()
    if document_type:
        return document_type
    document_type = DocumentType(
        code="certificate_of_origin",
        name="Certificate of Origin",
        category="export_compliance",
        description="Synthetic document type fallback for local demo data.",
        sensitive=False,
        requires_expiry_date=True,
        requires_issuing_body=True,
        requires_reference_number=True,
        active=True,
    )
    db.session.add(document_type)
    db.session.flush()
    return document_type


def seed_actor_registry(admin, partner):
    crop = first_or_create_crop()
    region = first_or_create_region()
    actor = MarketActor.query.filter_by(public_id=DEMO_ACTOR_PUBLIC_ID).first()
    if not actor:
        actor = MarketActor(
            public_id=DEMO_ACTOR_PUBLIC_ID,
            partner_organization_id=partner.id,
            created_by_user_id=admin.id,
            updated_by_id=admin.id,
            actor_type="exporter",
            name="Demo Sahel Ginger Exporter",
            crop_id=crop.id,
            registration_status="demo_registered",
            status="active",
            source_reference_type="demo_seed",
            source_reference="commercial-demo-launch-readiness",
            metadata_json={
                "synthetic_demo_record": True,
                "real_contact_details": False,
                "data_freshness_date": (utcnow().date() - timedelta(days=7)).isoformat(),
                "last_verified_date": (utcnow().date() - timedelta(days=5)).isoformat(),
                "update_source": "demo_partner_owner_review",
                "update_cycle": "monthly",
                "partner_notes": "Synthetic baseline actor for partner owner onboarding.",
                "partner_maintained_record": True,
                "actor_confirmed_record": False,
                "subscriber_safe": False,
            },
        )
        db.session.add(actor)
        db.session.flush()
    else:
        actor.partner_organization_id = partner.id
        actor.updated_by_id = admin.id
        actor.crop_id = crop.id
        actor.status = "active"
        actor.archived_at = None
        actor.metadata_json = {
            **(actor.metadata_json or {}),
            "data_freshness_date": (utcnow().date() - timedelta(days=7)).isoformat(),
            "last_verified_date": (utcnow().date() - timedelta(days=5)).isoformat(),
            "update_source": "demo_partner_owner_review",
            "update_cycle": "monthly",
            "partner_notes": "Synthetic baseline actor for partner owner onboarding.",
            "partner_maintained_record": True,
            "actor_confirmed_record": False,
            "subscriber_safe": False,
        }

    location = ActorLocation.query.filter_by(market_actor_id=actor.id).first()
    if not location:
        location = ActorLocation(market_actor_id=actor.id)
        db.session.add(location)
    location.region_id = region.id
    location.location_text = "Demo aggregation zone, South West region"
    location.location = "Demo aggregation zone"
    location.country = "Nigeria"
    location.is_primary = True

    export_profile = ActorExportProfile.query.filter_by(market_actor_id=actor.id).first()
    if not export_profile:
        export_profile = ActorExportProfile(market_actor_id=actor.id)
        db.session.add(export_profile)
    export_profile.years_in_export_trade = 4
    export_profile.trade_destination_name = "Demo ECOWAS buyer market"
    export_profile.export_capacity = "Demo-ready monthly volume"
    export_profile.export_capacity_unit = "metric_tonnes"
    export_profile.port_of_exit = "Demo Lagos export corridor"
    export_profile.notes = "Synthetic export profile for commercial walkthroughs."

    certification = ActorCertification.query.filter_by(
        market_actor_id=actor.id,
        reference_number="DEMO-CERT-001",
    ).first()
    if not certification:
        certification = ActorCertification(
            market_actor_id=actor.id,
            certification_name="Demo Export Readiness Certificate",
            reference_number="DEMO-CERT-001",
        )
        db.session.add(certification)
    certification.certificate_number = "DEMO-CERT-001"
    certification.issuing_body = "Demo Export Desk"
    certification.verification_status = "verified"
    certification.status = "active"
    certification.issued_at = utcnow().date() - timedelta(days=30)
    certification.expires_at = utcnow().date() + timedelta(days=330)
    certification.notes = "Synthetic certification metadata only."

    constraint = ActorConstraint.query.filter_by(
        market_actor_id=actor.id,
        constraint_category="demo_readiness",
    ).first()
    if not constraint:
        constraint = ActorConstraint(
            market_actor_id=actor.id,
            constraint_category="demo_readiness",
        )
        db.session.add(constraint)
    constraint.constraint_text = "Synthetic note: buyer verification workflow remains governed."
    constraint.severity = "low"
    constraint.status = "active"
    db.session.flush()
    return actor


def seed_document_and_requests(admin, subscriber, partner, actor):
    document_type = first_or_create_document_type()
    crop = first_or_create_crop()
    document = ActorDocument.query.filter_by(
        market_actor_id=actor.id,
        title=DEMO_DOCUMENT_TITLE,
    ).first()
    if not document:
        document = ActorDocument(
            market_actor_id=actor.id,
            partner_organization_id=partner.id,
            document_type_id=document_type.id,
            uploaded_by_user_id=admin.id,
            title=DEMO_DOCUMENT_TITLE,
        )
        db.session.add(document)

    document.description = "Synthetic metadata-only document record for due diligence demos."
    document.original_filename = None
    document.stored_filename = None
    document.storage_path = None
    document.mime_type = None
    document.file_size = None
    document.file_hash = None
    document.version_number = 1
    document.document_reference_number = "DEMO-COO-001"
    document.issuing_body = "Demo Export Desk"
    document.linked_crop_id = crop.id
    document.document_status = "approved"
    document.verification_status = "verified"
    document.redaction_status = "not_required"
    document.subscriber_access_level = "metadata_only"
    document.review_status = "approved"
    document.reviewed_by_user_id = admin.id
    document.reviewed_at = utcnow()
    document.review_comments = "Synthetic admin-approved metadata for local demo only."
    document.visibility_level = "metadata_only"
    document.issued_at = utcnow().date() - timedelta(days=30)
    document.expires_at = utcnow().date() + timedelta(days=330)
    document.is_current_version = True
    document.archived_at = None
    document.metadata_json = {
        "synthetic_demo_record": True,
        "metadata_only": True,
        "file_record_created": False,
        "real_contact_details": False,
    }
    db.session.flush()

    document_category = consent_document_category_for_document_type(document_type)
    consent = ActorConsentRecord.query.filter_by(
        market_actor_id=actor.id,
        partner_organization_id=partner.id,
        consent_reference="DEMO-CONSENT-001",
    ).first()
    if not consent:
        consent = ActorConsentRecord(
            market_actor_id=actor.id,
            partner_organization_id=partner.id,
            consent_reference="DEMO-CONSENT-001",
        )
        db.session.add(consent)
    consent.consent_status = "granted"
    consent.consent_scope_json = ["metadata_demo"]
    consent.permitted_data_categories_json = ["actor_profile", "export_profile"]
    consent.permitted_document_categories_json = [document_category]
    consent.sharing_channels_json = ["subscriber_portal", "buyer_due_diligence"]
    consent.consent_method = "synthetic_demo_attestation"
    consent.consent_document_id = None
    consent.granted_by_name = None
    consent.granted_by_role = None
    consent.granted_by_email = None
    consent.granted_by_phone = None
    consent.granted_at = utcnow() - timedelta(days=14)
    consent.expires_at = utcnow() + timedelta(days=180)
    consent.withdrawn_at = None
    consent.captured_by_user_id = admin.id
    consent.review_status = "approved"
    consent.reviewed_by_user_id = admin.id
    consent.reviewed_at = utcnow()
    consent.review_notes = "Synthetic consent context for local demo only."
    consent.active = True

    for target, status, note in [
        ("subscriber_portal_metadata", "ready", "Metadata can be demonstrated when entitlement gates pass."),
        ("redacted_document_candidate", "blocked", "No redacted file exists in demo seed."),
        ("full_document_restricted_candidate", "blocked", "Full document access remains out of scope."),
    ]:
        control = DocumentPublishControl.query.filter_by(
            actor_document_id=document.id,
            publish_target=target,
        ).first()
        if not control:
            control = DocumentPublishControl(
                actor_document_id=document.id,
                publish_target=target,
            )
            db.session.add(control)
        control.status = status
        control.readiness_checks_json = [{"key": "synthetic_demo_metadata", "status": "pass"}] if status == "ready" else []
        control.blocking_reasons_json = [] if status == "ready" else [note]
        control.admin_decision = "demo_seed"
        control.notes = note
        control.decided_by_user_id = admin.id
        control.decided_at = utcnow()
        control.last_evaluated_at = utcnow()

    access_request = DocumentAccessRequest.query.filter_by(
        actor_document_id=document.id,
        user_id=subscriber.id,
        request_type="redacted_document",
    ).first()
    if not access_request:
        access_request = DocumentAccessRequest(
            actor_document_id=document.id,
            user_id=subscriber.id,
            request_type="redacted_document",
        )
        db.session.add(access_request)
    access_request.request_channel = "subscriber_portal"
    access_request.organization_name = "Demo Buyer Consortium"
    access_request.purpose = "Synthetic due diligence request for local walkthroughs."
    access_request.status = "in_review"
    access_request.review_notes = "Synthetic request; no file access has been granted."

    automation_run = DocumentAutomationRun.query.filter_by(
        actor_document_id=document.id,
        trigger_source="demo_seed",
    ).first()
    if not automation_run:
        automation_run = DocumentAutomationRun(
            actor_document_id=document.id,
            trigger_source="demo_seed",
            requested_by_user_id=admin.id,
        )
        db.session.add(automation_run)
    automation_run.status = "queued"
    automation_run.job_type = "document_intelligence"
    automation_run.eligibility_checks_json = [
        {"key": "metadata_only_demo_document", "status": "pass"},
        {"key": "no_private_file_seeded", "status": "pass"},
    ]
    automation_run.confidence_summary_json = {"overall": 82, "requires_human_review": True}
    automation_run.event_log_json = [
        {"event": "demo_seed_created", "safe_metadata_only": True, "auto_published": False}
    ]
    automation_run.notes = "Synthetic queued run for launch readiness dashboards."
    automation_run.error_message = None
    automation_run.queued_at = utcnow()
    automation_run.started_at = None
    automation_run.completed_at = None
    automation_run.cancelled_at = None
    db.session.flush()
    return document


def get_or_create_source(source_code, name, category, trust_level, cadence, admin):
    source = IntelligenceSource.query.filter_by(source_code=source_code).first()
    if not source:
        source = IntelligenceSource(source_code=source_code, created_by_user_id=admin.id)
        db.session.add(source)
    source.name = name
    source.description = "Synthetic intelligence source for local commercial demos."
    source.category = category
    source.status = "active"
    source.trust_level = trust_level
    source.cadence = cadence
    source.owner_team = "Demo Intelligence Desk"
    source.public_reference_url = "https://example.com/fieldsight-demo-source"
    source.safe_configuration_json = {
        "synthetic_demo_source": True,
        "region_code": "SW",
        "crop": "Ginger",
        "manual_ingestion_only": True,
    }
    source.allowed_summary_fields_json = ["region_code", "crop", "signal_type", "confidence"]
    source.updated_by_user_id = admin.id
    source.archived_at = None
    db.session.flush()
    return source


def ensure_run_for_source(source, admin):
    run = IntelligenceIngestionRun.query.filter_by(source_id=source.id).first()
    if run:
        return run
    run, result = create_manual_ingestion_run(source, actor_user_id=admin.id)
    if not result.get("created"):
        raise RuntimeError(f"Could not create demo ingestion run for {source.source_code}: {result.get('message')}")
    db.session.flush()
    return run


def seed_intelligence(admin):
    source_configs = [
        ("demo_market_signal_sw_ginger", "Demo South West Ginger Market Signal", "market_signal", "verified", "weekly"),
        ("demo_export_flow_watch", "Demo Export Flow Watch", "manual_research", "high", "manual"),
    ]
    sources = [
        get_or_create_source(source_code, name, category, trust_level, cadence, admin)
        for source_code, name, category, trust_level, cadence in source_configs
    ]
    runs = [ensure_run_for_source(source, admin) for source in sources]

    publishable_alert = IntelligenceAlert.query.filter_by(ingestion_run_id=runs[0].id).first()
    if publishable_alert:
        if publishable_alert.status != "approved":
            update_alert_review(
                publishable_alert,
                "approved",
                review_notes="Synthetic alert approved for safe digest demo.",
                actor_user_id=admin.id,
            )
        candidate, _result = create_publication_candidate_from_alert(publishable_alert, actor_user_id=admin.id)
        if candidate and candidate.status != "approved":
            update_publication_candidate(
                candidate,
                "approve",
                actor_user_id=admin.id,
                title="Demo Ginger Market Readiness Signal",
                summary="Synthetic safe digest: ginger supply signals are ready for commercial discussion.",
                review_notes="Approved synthetic digest for local demo only.",
            )

    open_alert = IntelligenceAlert.query.filter_by(ingestion_run_id=runs[1].id).first()
    if open_alert:
        open_alert.status = "open"
        open_alert.summary = "Synthetic internal alert remains open for admin review demonstration."
        open_alert.safe_payload_json = {
            **(open_alert.safe_payload_json or {}),
            "synthetic_demo_alert": True,
            "internal_review_only": True,
        }
    db.session.flush()
    return {
        "sources": len(sources),
        "runs": len(runs),
        "alerts": IntelligenceAlert.query.filter(IntelligenceAlert.source_id.in_([source.id for source in sources])).count(),
        "candidates": IntelligencePublicationCandidate.query.count(),
        "digests": SubscriberIntelligenceDigest.query.count(),
    }


def seed_commercial_requests(subscriber):
    request_specs = [
        ("upgrade", "National Intelligence Demo Upgrade", "pending"),
        ("api_access", "Document Metadata API Demo Access", "in_review"),
        ("live_intelligence", "Live Market Intelligence Demo Scope", "contacted"),
    ]
    created = 0
    for request_type, product, status in request_specs:
        commercial_request = CommercialRequest.query.filter_by(
            user_id=subscriber.id,
            request_type=request_type,
            requested_product=product,
        ).first()
        if not commercial_request:
            commercial_request = CommercialRequest(
                user_id=subscriber.id,
                request_type=request_type,
                requested_product=product,
            )
            db.session.add(commercial_request)
            created += 1
        commercial_request.organization_name = "Demo Buyer Consortium"
        commercial_request.contact_name = "Demo Commercial Desk"
        commercial_request.contact_email = None
        commercial_request.dataset_code = "market_changes" if request_type == "upgrade" else None
        commercial_request.region_code = "SW" if request_type == "upgrade" else None
        commercial_request.crop_name = "Ginger" if request_type == "upgrade" else None
        commercial_request.message = "Synthetic commercial request for local demo walkthroughs."
        commercial_request.context_json = {
            "synthetic_demo_record": True,
            "auto_granted": False,
            "payment_flow_changed": False,
        }
        commercial_request.status = status
    db.session.flush()
    return created


def seed_partner_import_demo(partner_user, partner):
    existing = PartnerUpdateBatch.query.filter_by(
        partner_organization_id=partner.id,
        title=DEMO_IMPORT_TITLE,
    ).first()
    if existing and is_import_batch(existing):
        return import_batch_summary(existing)

    raw_rows = [
        {
            "COMMODITY CATEGORY": "Ginger",
            "FARMER/AGGREAGATOR": "Demo Fresh Ginger Aggregator",
            "LOCATION": "Demo aggregation zone B",
            "STATE": "Lagos",
            "PHONE": "+2340000000000",
            "EMAIL": "actor-contact@fieldsight-demo.invalid",
            "LGA": "Ikeja",
            "REGISTRATION STATUS": "registered",
            "DATE OF REGISTRATION": "2026-06-01",
            "NUMBER OF YEARS IN EXPORT TRADE": "3",
            "TRADE DESTINATION": "Demo ECOWAS buyer market",
            "EXPORT CAPACITY": "25 metric tonnes monthly",
            "ERTIFICATION": "Demo phytosanitary readiness",
            "PORT OF EXIT": "Demo Lagos export corridor",
            "CONSTRAINT": "Requires periodic certification refresh",
        },
        {
            "COMMODITY CATEGORY": "Ginger",
            "FARMER/AGGREAGATOR": "",
            "LOCATION": "Demo missing actor name zone",
            "STATE": "Lagos",
            "PHONE": "",
            "EMAIL": "",
            "LGA": "Ikeja",
            "REGISTRATION STATUS": "pending",
            "DATE OF REGISTRATION": "not-a-date",
            "NUMBER OF YEARS IN EXPORT TRADE": "2",
            "TRADE DESTINATION": "Demo buyer market",
            "EXPORT CAPACITY": "10 bags monthly",
            "ERTIFICATION": "Demo certificate pending",
            "PORT OF EXIT": "Demo port",
            "CONSTRAINT": "Missing actor name must be corrected",
        },
        {
            "COMMODITY CATEGORY": "Ginger",
            "FARMER/AGGREAGATOR": "Demo Sahel Ginger Exporter",
            "LOCATION": "Demo aggregation zone",
            "STATE": "Lagos",
            "PHONE": "",
            "EMAIL": "",
            "LGA": "Ikeja",
            "REGISTRATION STATUS": "registered",
            "DATE OF REGISTRATION": "2026-05-20",
            "NUMBER OF YEARS IN EXPORT TRADE": "4",
            "TRADE DESTINATION": "Demo ECOWAS buyer market",
            "EXPORT CAPACITY": "Updated monthly volume",
            "ERTIFICATION": "Demo Export Readiness Certificate",
            "PORT OF EXIT": "Demo Lagos export corridor",
            "CONSTRAINT": "Potential update candidate for existing actor",
        },
    ]
    batch = create_import_batch_from_rows(
        partner.id,
        partner_user.id,
        raw_rows,
        DEMO_IMPORT_TITLE,
        reporting_month=utcnow().strftime("%Y-%m"),
        defaults={
            "data_freshness_date": utcnow().date().isoformat(),
            "last_verified_date": utcnow().date().isoformat(),
            "update_source": "demo_partner_bulk_upload",
            "update_cycle": "monthly",
            "partner_notes": "Synthetic owner onboarding import with valid, rejected, and update candidate rows.",
        },
    )
    return import_batch_summary(batch)


def seed_demo_data(commit=True):
    admin = get_or_create_user("Demo Admin", DEMO_ADMIN_EMAIL, "admin")
    subscriber = get_or_create_user("Demo Subscriber", DEMO_SUBSCRIBER_EMAIL, "subscriber")
    partner_user = get_or_create_user("Demo Partner Owner", DEMO_PARTNER_EMAIL, "subscriber")
    partner = get_or_create_partner()
    get_or_create_partner_profile(partner_user, partner)
    actor = seed_actor_registry(admin, partner)
    document = seed_document_and_requests(admin, subscriber, partner, actor)
    intelligence_summary = seed_intelligence(admin)
    commercial_created = seed_commercial_requests(subscriber)
    partner_import_summary = seed_partner_import_demo(partner_user, partner)

    if commit:
        db.session.commit()

    return {
        "admin_user": admin.email,
        "subscriber_user": subscriber.email,
        "partner_user": partner_user.email,
        "partner": partner.slug,
        "actor_public_id": actor.public_id,
        "document_id": document.id,
        "commercial_requests_created": commercial_created,
        "partner_import_rows": partner_import_summary["total_rows"],
        **intelligence_summary,
    }


def parse_args():
    parser = argparse.ArgumentParser(description="Seed safe synthetic FieldSight Africa demo data.")
    parser.add_argument(
        "--confirm-demo-seed",
        action="store_true",
        help="Required confirmation that this is a local/demo seed run.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if not args.confirm_demo_seed:
        print("Refusing to seed without --confirm-demo-seed. This script is local/demo oriented.")
        return 2

    with app.app_context():
        summary = seed_demo_data(commit=True)
        print("Safe synthetic demo data seeded.")
        for key, value in summary.items():
            print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
