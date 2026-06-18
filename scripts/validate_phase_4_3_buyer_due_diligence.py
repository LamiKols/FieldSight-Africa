"""Validate Phase 4.3 buyer due diligence and controlled document access.

This script uses an in-memory SQLite database and Flask's test client so it
does not touch Replit PostgreSQL data, private document files, or payment
providers.
"""

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SESSION_SECRET", "phase-4-3-validation-secret")
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
    ActorDocument,
    ActorLocation,
    AuditLog,
    Crop,
    DocumentAccessFulfilmentAction,
    DocumentAccessLog,
    DocumentAccessRequest,
    DocumentExtractionRun,
    DocumentPublishControl,
    DocumentType,
    MarketActor,
    PartnerOrganization,
    Region,
    Subscription,
    User,
    consent_document_category_for_document_type,
)


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


def future_datetime(days=45):
    return utcnow() + timedelta(days=days)


def future_date(days=365):
    return (utcnow().date() + timedelta(days=days))


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
        provider_subscription_id=f"phase-4-3-sub-{user.id}",
        plan_code="STARTER",
        status="active",
        current_period_end=future_datetime(),
        regions_selected=["SW"],
        crops_selected=["Ginger"],
    )
    db.session.add(subscription)
    db.session.flush()
    return subscription


def create_publish_control(document, target, status="ready"):
    control = DocumentPublishControl(
        actor_document_id=document.id,
        publish_target=target,
        status=status,
        readiness_checks_json=[{"key": "validation", "status": "pass"}] if status == "ready" else [],
        blocking_reasons_json=[] if status == "ready" else ["Validation blocked target"],
        admin_decision="validation",
        last_evaluated_at=utcnow(),
    )
    db.session.add(control)
    db.session.flush()
    return control


def create_valid_document(owner_user, organization, *, with_consent=True, target_status="ready", title_suffix="valid"):
    region = Region.query.filter_by(code="SW").one()
    crop = Crop.query.filter_by(name="Ginger").one()
    actor = MarketActor(
        partner_organization_id=organization.id,
        created_by_user_id=owner_user.id,
        actor_type="exporter",
        name=f"Hidden Exporter {title_suffix}",
        crop_id=crop.id,
        status="active",
    )
    db.session.add(actor)
    db.session.flush()
    db.session.add(ActorLocation(
        market_actor_id=actor.id,
        region_id=region.id,
        location_text="Hidden actor location",
        is_primary=True,
    ))
    document_type = DocumentType.query.filter_by(name="Certificate of Origin").one()
    document = ActorDocument(
        market_actor_id=actor.id,
        partner_organization_id=organization.id,
        document_type_id=document_type.id,
        uploaded_by_user_id=owner_user.id,
        title=f"Due Diligence Certificate {title_suffix}",
        description="Internal restricted description should not render.",
        original_filename="unsafe-original-certificate.pdf",
        stored_filename="unsafe-stored-certificate.pdf",
        storage_path="/private_uploads/unsafe/should-not-render.pdf",
        file_hash="unsafe-file-hash-should-not-render",
        document_reference_number=f"COO-PHASE-43-{title_suffix}",
        issuing_body="Nigerian Export Promotion Council",
        linked_crop_id=crop.id,
        document_status="approved",
        review_status="approved",
        verification_status="verified",
        redaction_status="completed",
        subscriber_access_level="metadata_only",
        visibility_level="metadata_only",
        issued_at=utcnow().date(),
        expires_at=future_date(),
    )
    db.session.add(document)
    db.session.flush()
    db.session.add(DocumentExtractionRun(
        actor_document_id=document.id,
        status="completed",
        document_type_code=document_type.code,
        extracted_fields_json={"document_reference_number": document.document_reference_number},
        metadata_mismatches_json=[],
        risk_flags_json=[],
        expiry_renewal_json={"status": "current", "days_until_expiry": 365},
        quality_score=92,
        document_intelligence_status="reconciled",
        raw_text_excerpt="Unsafe raw extraction text should not render.",
        created_by_user_id=owner_user.id,
    ))

    document_category = consent_document_category_for_document_type(document_type)
    if with_consent:
        db.session.add(ActorConsentRecord(
            market_actor_id=actor.id,
            partner_organization_id=organization.id,
            consent_status="granted",
            consent_method="written",
            consent_reference=f"CONSENT-PHASE-43-{title_suffix}",
            consent_scope_json=[
                "share_document_metadata_with_subscribers",
                "share_redacted_documents_with_subscribers",
                "share_full_documents_with_approved_users",
            ],
            permitted_document_categories_json=[document_category],
            sharing_channels_json=[
                "subscriber_portal",
                "approved_buyer_due_diligence",
                "api",
            ],
            granted_by_name="Hidden Actor Contact",
            granted_at=utcnow(),
            expires_at=future_datetime(365),
            captured_by_user_id=owner_user.id,
            active=True,
        ))

    create_publish_control(document, "subscriber_portal_metadata", status="ready")
    create_publish_control(document, "redacted_document_candidate", status=target_status)
    create_publish_control(document, "full_document_restricted_candidate", status=target_status)
    db.session.flush()
    return document


def create_access_request(user, document, request_type="redacted_document", status="pending", organization_name="Buyer Due Diligence Ltd"):
    access_request = DocumentAccessRequest(
        actor_document_id=document.id,
        user_id=user.id,
        request_type=request_type,
        request_channel="subscriber_portal",
        organization_name=organization_name,
        purpose="Validate buyer onboarding without exposing restricted fields.",
        status=status,
    )
    db.session.add(access_request)
    db.session.flush()
    return access_request


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

        subscriber = create_user("Due Diligence Subscriber", "subscriber@example.com")
        other_user = create_user("Other Subscriber", "other@example.com")
        admin = create_user("Due Diligence Admin", "admin@example.com", role="admin")
        create_subscription(subscriber)
        create_subscription(other_user)

        organization = PartnerOrganization(name="Phase 4.3 Partner", slug="phase-4-3-partner", status="active")
        db.session.add(organization)
        db.session.flush()

        valid_document = create_valid_document(admin, organization, title_suffix="valid")
        blocked_document = create_valid_document(admin, organization, with_consent=False, title_suffix="blocked")
        full_document = create_valid_document(admin, organization, title_suffix="full")

        valid_request = create_access_request(subscriber, valid_document, "redacted_document")
        full_request = create_access_request(subscriber, full_document, "full_document_restricted")
        blocked_request = create_access_request(subscriber, blocked_document, "redacted_document")
        rejected_request = create_access_request(subscriber, valid_document, "redacted_document")
        cancelled_request = create_access_request(subscriber, valid_document, "full_document_restricted")
        other_request = create_access_request(other_user, valid_document, "redacted_document", organization_name="Other Buyer Ltd")
        db.session.commit()

        ids = {
            "subscriber": subscriber.id,
            "admin": admin.id,
            "valid_request": valid_request.id,
            "full_request": full_request.id,
            "blocked_request": blocked_request.id,
            "rejected_request": rejected_request.id,
            "cancelled_request": cancelled_request.id,
            "other_request": other_request.id,
        }

    client = app.test_client()

    for path in [
        "/admin/due-diligence-requests",
        f"/admin/due-diligence-requests/{ids['valid_request']}",
    ]:
        response = client.get(path, follow_redirects=False)
        assert_true(response.status_code == 302 and "/login" in response.headers.get("Location", ""), f"{path} did not require login")

    with client:
        login(client, "subscriber@example.com")
        for path in [
            "/admin/due-diligence-requests",
            f"/admin/due-diligence-requests/{ids['valid_request']}",
        ]:
            response = client.get(path, follow_redirects=False)
            assert_true(response.status_code in (302, 303), f"{path} was not admin-only")

        response = client.get("/subscriber/document-access-requests")
        assert_true(response.status_code == 200, "Subscriber document access request list did not render")
        page = response.get_data(as_text=True)
        assert_true("Buyer Due Diligence Ltd" not in page, "Subscriber list should not need organization names for matching")
        assert_true("Other Buyer Ltd" not in page, "Subscriber list leaked another user's access request")
        assert_true("Redacted Document" in page, "Subscriber list missed own redacted request")

        response = client.get(f"/subscriber/document-access-requests/{ids['valid_request']}")
        assert_true(response.status_code == 200, "Subscriber own access request detail did not render")
        page = response.get_data(as_text=True)
        assert_true("Request Details" in page, "Subscriber request detail missing")
        for unsafe in [
            "/private_uploads/",
            "unsafe-original-certificate.pdf",
            "unsafe-stored-certificate.pdf",
            "unsafe-file-hash-should-not-render",
            "Unsafe raw extraction text",
            "Hidden Exporter",
            "Hidden Actor Contact",
            "Hidden actor location",
        ]:
            assert_true(unsafe not in page, f"Unsafe value leaked on subscriber detail: {unsafe}")

        response = client.get(f"/subscriber/document-access-requests/{ids['other_request']}")
        assert_true(response.status_code == 404, "Subscriber could view another user's document access request")
        logout(client)

        login(client, "admin@example.com")
        response = client.get("/admin/due-diligence-requests")
        assert_true(response.status_code == 200, "Admin due diligence queue did not render")
        page = response.get_data(as_text=True)
        assert_true("Due Diligence Requests" in page, "Admin due diligence queue title missing")
        assert_true("Full Document Restricted" in page, "Admin due diligence queue missed full document request")

        response = client.get(f"/admin/due-diligence-requests/{ids['valid_request']}")
        assert_true(response.status_code == 200, "Admin due diligence detail did not render")
        page = response.get_data(as_text=True)
        assert_true("Visibility Separation" in page, "Admin detail missing visibility separation")
        assert_true("Redacted Access Candidate" in page, "Admin detail missing redacted candidate")
        assert_true("Restricted Full-Document Candidate" in page, "Admin detail missing full document candidate")
        for unsafe in [
            "/private_uploads/",
            "unsafe-original-certificate.pdf",
            "unsafe-stored-certificate.pdf",
            "unsafe-file-hash-should-not-render",
            "Unsafe raw extraction text",
            "Hidden Exporter",
            "Hidden Actor Contact",
            "Hidden actor location",
        ]:
            assert_true(unsafe not in page, f"Unsafe value leaked on admin detail: {unsafe}")

        response = client.post(
            f"/admin/due-diligence-requests/{ids['valid_request']}/decision",
            data={
                "status": "approved_for_redacted_access",
                "review_notes": "Approved for redacted fulfilment recording.",
            },
            follow_redirects=False,
        )
        assert_true(response.status_code in (302, 303), "Admin due diligence approval did not redirect")
        with app.app_context():
            refreshed = db.session.get(DocumentAccessRequest, ids["valid_request"])
            assert_true(refreshed.status == "approved_for_redacted_access", "Approved due diligence status did not persist")
            assert_true(refreshed.reviewed_by_user_id == ids["admin"], "Due diligence reviewer was not recorded")
            decision_audit = AuditLog.query.filter_by(
                action="admin_due_diligence_request_status_updated",
                entity_id=ids["valid_request"],
            ).first()
            assert_true(decision_audit is not None, "Due diligence decision audit missing")
            assert_true(decision_audit.after_values.get("access_granted") is False, "Decision audit should record no auto access")

        response = client.post(
            f"/admin/due-diligence-requests/{ids['valid_request']}/fulfilment",
            data={
                "action_type": "redacted_access_recorded",
                "visibility_level": "redacted_document_candidate",
                "notes": "Redacted access fulfilment recorded externally by controlled process.",
            },
            follow_redirects=False,
        )
        assert_true(response.status_code in (302, 303), "Due diligence fulfilment did not redirect")
        with app.app_context():
            action = DocumentAccessFulfilmentAction.query.filter_by(
                document_access_request_id=ids["valid_request"],
                action_type="redacted_access_recorded",
            ).first()
            assert_true(action is not None, "Due diligence fulfilment action missing")
            assert_true(action.visibility_level == "redacted_document_candidate", "Fulfilment visibility was not stored")
            fulfilment_audit = AuditLog.query.filter_by(
                action="admin_due_diligence_fulfilment_recorded",
                entity_id=ids["valid_request"],
            ).first()
            assert_true(fulfilment_audit is not None, "Due diligence fulfilment audit missing")
            assert_true(fulfilment_audit.after_values.get("file_exposed") is False, "Fulfilment audit should record no file exposure")
            access_log = DocumentAccessLog.query.filter_by(
                actor_document_id=refreshed.actor_document_id,
                access_type="admin_due_diligence_fulfilment_recorded",
            ).first()
            assert_true(access_log is not None, "Due diligence fulfilment access log missing")

        response = client.post(
            f"/admin/due-diligence-requests/{ids['blocked_request']}/decision",
            data={
                "status": "approved_for_redacted_access",
                "review_notes": "This should be blocked because consent is missing.",
            },
            follow_redirects=False,
        )
        assert_true(response.status_code in (302, 303), "Blocked approval did not redirect")
        with app.app_context():
            blocked = db.session.get(DocumentAccessRequest, ids["blocked_request"])
            assert_true(blocked.status == "pending", "Blocked request should not be approved")
            blocked_audit = AuditLog.query.filter_by(
                action="admin_due_diligence_decision_blocked",
                entity_id=ids["blocked_request"],
            ).first()
            assert_true(blocked_audit is not None, "Blocked due diligence decision audit missing")

        response = client.post(
            f"/admin/due-diligence-requests/{ids['rejected_request']}/decision",
            data={"status": "rejected", "review_notes": "Rejected during validation."},
            follow_redirects=False,
        )
        assert_true(response.status_code in (302, 303), "Rejected decision did not redirect")
        with app.app_context():
            actions_before = DocumentAccessFulfilmentAction.query.count()
        response = client.post(
            f"/admin/due-diligence-requests/{ids['rejected_request']}/fulfilment",
            data={
                "action_type": "redacted_access_recorded",
                "visibility_level": "redacted_document_candidate",
                "notes": "This should be blocked.",
            },
            follow_redirects=False,
        )
        assert_true(response.status_code in (302, 303), "Rejected fulfilment block did not redirect")
        with app.app_context():
            assert_true(DocumentAccessFulfilmentAction.query.count() == actions_before, "Rejected request created fulfilment access")
            rejected_block = AuditLog.query.filter_by(
                action="admin_due_diligence_fulfilment_blocked",
                entity_id=ids["rejected_request"],
            ).first()
            assert_true(rejected_block is not None, "Rejected request blocked fulfilment audit missing")

        response = client.post(
            f"/admin/due-diligence-requests/{ids['cancelled_request']}/decision",
            data={"status": "cancelled", "review_notes": "Cancelled during validation."},
            follow_redirects=False,
        )
        assert_true(response.status_code in (302, 303), "Cancelled decision did not redirect")
        with app.app_context():
            actions_before_cancelled = DocumentAccessFulfilmentAction.query.count()
        response = client.post(
            f"/admin/due-diligence-requests/{ids['cancelled_request']}/fulfilment",
            data={
                "action_type": "restricted_full_document_review_recorded",
                "visibility_level": "full_document_restricted_candidate",
                "notes": "This should be blocked.",
            },
            follow_redirects=False,
        )
        assert_true(response.status_code in (302, 303), "Cancelled fulfilment block did not redirect")
        with app.app_context():
            assert_true(
                DocumentAccessFulfilmentAction.query.count() == actions_before_cancelled,
                "Cancelled request created fulfilment access",
            )
            cancelled_block = AuditLog.query.filter_by(
                action="admin_due_diligence_fulfilment_blocked",
                entity_id=ids["cancelled_request"],
            ).first()
            assert_true(cancelled_block is not None, "Cancelled request blocked fulfilment audit missing")

    print("Phase 4.3 buyer due diligence validation passed.")


if __name__ == "__main__":
    run_validation()
