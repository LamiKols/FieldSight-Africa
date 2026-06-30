"""Validate Intelligence Engine Release 1."""

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SESSION_SECRET", "intelligence-engine-release-1-validation")
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
from intelligence_engine import create_manual_ingestion_run  # noqa: E402
from models import (  # noqa: E402
    AuditLog,
    IntelligenceAlert,
    IntelligenceChangeEvent,
    IntelligenceIngestionRun,
    IntelligencePublicationCandidate,
    IntelligenceSource,
    SubscriberIntelligenceDigest,
    User,
)


UNSAFE_VALUES = [
    "C:\\private\\source-file.csv",
    "unsafe-source-file.csv",
    "unsafe-source-hash",
    "api-secret-token",
    "key-hash-value",
    "secret-source@example.com",
    "Hidden Source Contact",
    "RAW SECRET EXTRACTION TEXT",
    "restricted_document_field_value",
]


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


def login(client, email, password="validation-password"):
    response = client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )
    assert_true(response.status_code in (302, 303), f"Login failed for {email}")


def logout(client):
    client.get("/logout", follow_redirects=False)


def assert_no_unsafe_text(text, surface):
    for unsafe in UNSAFE_VALUES:
        assert_true(unsafe not in text, f"Unsafe value rendered on {surface}: {unsafe}")


def assert_record_safe(record, label):
    text = str(record)
    for unsafe in UNSAFE_VALUES:
        assert_true(unsafe not in text, f"Unsafe value persisted in {label}: {unsafe}")


def source_payload(source_code, *, status="active", name="Weekly Market Signal"):
    return {
        "source_code": source_code,
        "name": name,
        "description": "Public market signal source for safe internal ingestion.",
        "category": "market_signal",
        "status": status,
        "trust_level": "verified",
        "cadence": "weekly",
        "owner_team": "Intelligence Desk",
        "public_reference_url": "https://example.com/public-market-signal",
        "safe_configuration_json": (
            '{"region_code":"SW","crop":"Ginger","signal_type":"price_watch",'
            '"api_secret":"api-secret-token","private_path":"C:\\\\private\\\\source-file.csv",'
            '"filename":"unsafe-source-file.csv","file_hash":"unsafe-source-hash",'
            '"contact_email":"secret-source@example.com","contact_name":"Hidden Source Contact",'
            '"raw_text":"RAW SECRET EXTRACTION TEXT","restricted_field":"restricted_document_field_value"}'
        ),
        "allowed_summary_fields_json": "region_code, crop, signal_type, file_hash, contact_email",
    }


def protected_routes(source_id, run_id, alert_id, candidate_id):
    return [
        ("GET", "/admin/intelligence-sources"),
        ("GET", "/admin/intelligence-sources/new"),
        ("POST", "/admin/intelligence-sources/new"),
        ("GET", f"/admin/intelligence-sources/{source_id}"),
        ("GET", f"/admin/intelligence-sources/{source_id}/edit"),
        ("POST", f"/admin/intelligence-sources/{source_id}/edit"),
        ("POST", f"/admin/intelligence-sources/{source_id}/run"),
        ("GET", "/admin/intelligence-ingestion-runs"),
        ("GET", f"/admin/intelligence-ingestion-runs/{run_id}"),
        ("GET", "/admin/intelligence-alerts"),
        ("GET", f"/admin/intelligence-alerts/{alert_id}"),
        ("POST", f"/admin/intelligence-alerts/{alert_id}/review"),
        ("GET", "/admin/intelligence-publication-candidates"),
        ("GET", f"/admin/intelligence-publication-candidates/{candidate_id}"),
        ("POST", f"/admin/intelligence-publication-candidates/{candidate_id}"),
    ]


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

        admin = create_user("Engine Admin", "admin@example.com", role="admin")
        subscriber = create_user("Engine Subscriber", "subscriber@example.com")
        fixture_source = IntelligenceSource(
            source_code="fixture_source",
            name="Fixture Source",
            description="Safe fixture source.",
            category="manual_research",
            status="active",
            trust_level="high",
            cadence="manual",
            safe_configuration_json={"region_code": "SW"},
            allowed_summary_fields_json=["region_code"],
            created_by_user_id=admin.id,
            updated_by_user_id=admin.id,
        )
        db.session.add(fixture_source)
        db.session.flush()
        fixture_run, fixture_result = create_manual_ingestion_run(fixture_source, actor_user_id=admin.id)
        assert_true(fixture_result["created"], "Fixture ingestion run was not created")
        fixture_alert = IntelligenceAlert.query.filter_by(ingestion_run_id=fixture_run.id).one()
        fixture_alert.status = "approved"
        db.session.flush()
        fixture_candidate = IntelligencePublicationCandidate(
            intelligence_alert_id=fixture_alert.id,
            candidate_type="subscriber_digest",
            status="draft",
            title="Fixture Candidate",
            summary="Safe fixture candidate.",
            safe_payload_json={"metadata_only": True, "external_access_created": False},
        )
        db.session.add(fixture_candidate)
        db.session.commit()

        ids = {
            "source": fixture_source.id,
            "run": fixture_run.id,
            "alert": fixture_alert.id,
            "candidate": fixture_candidate.id,
        }

    client = app.test_client()

    for method, path in protected_routes(ids["source"], ids["run"], ids["alert"], ids["candidate"]):
        response = getattr(client, method.lower())(path, follow_redirects=False)
        assert_true(response.status_code == 302 and "/login" in response.headers.get("Location", ""), f"{path} did not require login")

    with client:
        login(client, "subscriber@example.com")
        for method, path in protected_routes(ids["source"], ids["run"], ids["alert"], ids["candidate"]):
            response = getattr(client, method.lower())(path, follow_redirects=False)
            assert_true(response.status_code in (302, 303), f"{path} was not admin-only")
        logout(client)

        login(client, "admin@example.com")
        response = client.post(
            "/admin/intelligence-sources/new",
            data=source_payload("weekly_market_signal"),
            follow_redirects=False,
        )
        assert_true(response.status_code in (302, 303), "Source creation did not redirect")

        with app.app_context():
            source = IntelligenceSource.query.filter_by(source_code="weekly_market_signal").one()
            assert_true(source.name == "Weekly Market Signal", "Source name did not persist")
            assert_true(source.safe_configuration_json.get("region_code") == "SW", "Safe region config missing")
            assert_true(source.safe_configuration_json.get("signal_type") == "price_watch", "Safe signal config missing")
            assert_true("api_secret" not in source.safe_configuration_json, "Unsafe API secret key persisted")
            assert_true("file_hash" not in source.allowed_summary_fields_json, "Unsafe allowed field persisted")
            assert_record_safe(source.safe_configuration_json, "source safe config")
            source_id = source.id

        response = client.get(f"/admin/intelligence-sources/{source_id}")
        assert_true(response.status_code == 200, "Source detail did not render")
        assert_no_unsafe_text(response.get_data(as_text=True), "source detail")

        paused_payload = source_payload("weekly_market_signal", status="paused")
        response = client.post(
            f"/admin/intelligence-sources/{source_id}/edit",
            data=paused_payload,
            follow_redirects=False,
        )
        assert_true(response.status_code in (302, 303), "Source edit did not redirect")
        response = client.post(f"/admin/intelligence-sources/{source_id}/run", follow_redirects=False)
        assert_true(response.status_code in (302, 303), "Paused run request did not redirect")
        with app.app_context():
            run_count = IntelligenceIngestionRun.query.filter_by(source_id=source_id).count()
            assert_true(run_count == 0, "Paused source created an ingestion run")
            blocked_audit = AuditLog.query.filter_by(action="intelligence_ingestion_run_blocked").first()
            assert_true(blocked_audit is not None, "Blocked ingestion audit missing")

        active_payload = source_payload("weekly_market_signal", status="active")
        response = client.post(
            f"/admin/intelligence-sources/{source_id}/edit",
            data=active_payload,
            follow_redirects=False,
        )
        assert_true(response.status_code in (302, 303), "Source activation did not redirect")
        response = client.post(f"/admin/intelligence-sources/{source_id}/run", follow_redirects=False)
        assert_true(response.status_code in (302, 303), "Active run request did not redirect")

        with app.app_context():
            run = IntelligenceIngestionRun.query.filter_by(source_id=source_id).one()
            assert_true(run.status == "completed", "Ingestion run did not complete safely")
            assert_true(run.detected_change_count == 1, "Change count not persisted")
            assert_true(run.generated_alert_count == 1, "Alert count not persisted")
            assert_record_safe(run.safe_summary_json, "run safe summary")
            change_event = IntelligenceChangeEvent.query.filter_by(ingestion_run_id=run.id).one()
            alert = IntelligenceAlert.query.filter_by(ingestion_run_id=run.id).one()
            assert_true(change_event.status == "linked_to_alert", "Change event was not linked to alert")
            assert_true(alert.status == "open", "Generated alert did not start open")
            run_id = run.id
            alert_id = alert.id

        for path, label in [
            ("/admin/intelligence-ingestion-runs", "ingestion run list"),
            (f"/admin/intelligence-ingestion-runs/{run_id}", "ingestion run detail"),
            ("/admin/intelligence-alerts", "alert list"),
            (f"/admin/intelligence-alerts/{alert_id}", "alert detail"),
        ]:
            response = client.get(path)
            assert_true(response.status_code == 200, f"{label} did not render")
            assert_no_unsafe_text(response.get_data(as_text=True), label)

        response = client.post(
            f"/admin/intelligence-alerts/{alert_id}/review",
            data={
                "status": "in_review",
                "review_notes": "Safe internal review note.",
                "create_publication_candidate": "true",
            },
            follow_redirects=False,
        )
        assert_true(response.status_code in (302, 303), "Alert review did not redirect")
        with app.app_context():
            candidate_count = IntelligencePublicationCandidate.query.filter_by(intelligence_alert_id=alert_id).count()
            assert_true(candidate_count == 0, "Publication candidate was created before alert approval")

        response = client.post(
            f"/admin/intelligence-alerts/{alert_id}/review",
            data={
                "status": "approved",
                "review_notes": "Approved safe intelligence alert.",
                "create_publication_candidate": "true",
            },
            follow_redirects=False,
        )
        assert_true(response.status_code in (302, 303), "Approved alert did not redirect")
        with app.app_context():
            alert = db.session.get(IntelligenceAlert, alert_id)
            candidate = IntelligencePublicationCandidate.query.filter_by(intelligence_alert_id=alert_id).one()
            assert_true(alert.status == "approved", "Alert approval did not persist")
            assert_true(candidate.status == "draft", "Candidate did not start draft")
            assert_record_safe(candidate.safe_payload_json, "candidate safe payload")
            candidate_id = candidate.id
            assert_true(AuditLog.query.filter_by(action="intelligence_publication_candidate_created", entity_id=candidate_id).first() is not None, "Candidate creation audit missing")

        response = client.get("/admin/intelligence-publication-candidates")
        assert_true(response.status_code == 200, "Candidate list did not render")
        assert_no_unsafe_text(response.get_data(as_text=True), "candidate list")
        response = client.get(f"/admin/intelligence-publication-candidates/{candidate_id}")
        assert_true(response.status_code == 200, "Candidate detail did not render")
        assert_no_unsafe_text(response.get_data(as_text=True), "candidate detail")

        response = client.post(
            f"/admin/intelligence-publication-candidates/{candidate_id}",
            data={
                "action": "approve",
                "title": "Approved Ginger Market Signal",
                "summary": "Approved safe digest summary for subscriber intelligence review.",
                "review_notes": "Safe publication candidate approval.",
            },
            follow_redirects=False,
        )
        assert_true(response.status_code in (302, 303), "Candidate approval did not redirect")
        with app.app_context():
            candidate = db.session.get(IntelligencePublicationCandidate, candidate_id)
            digest = SubscriberIntelligenceDigest.query.filter_by(publication_candidate_id=candidate_id).one()
            assert_true(candidate.status == "approved", "Candidate approval did not persist")
            assert_true(digest.status == "approved", "Approved digest was not created")
            assert_record_safe(digest.safe_payload_json, "subscriber digest safe payload")
            assert_true(AuditLog.query.filter_by(action="subscriber_intelligence_digest_created", entity_id=digest.id).first() is not None, "Digest audit missing")
            draft_digest = SubscriberIntelligenceDigest(
                publication_candidate_id=candidate_id,
                title="Hidden Draft Digest",
                summary="Hidden draft summary.",
                status="draft",
                safe_payload_json={"metadata_only": True},
                approved_at=utcnow(),
            )
            db.session.add(draft_digest)
            db.session.commit()
            digest_id = digest.id

        response = client.get(f"/admin/intelligence-publication-candidates/{candidate_id}")
        assert_true(response.status_code == 200, "Approved candidate detail did not render")
        assert_no_unsafe_text(response.get_data(as_text=True), "approved candidate detail")
        logout(client)

        login(client, "subscriber@example.com")
        response = client.get("/subscriber/intelligence-digests")
        assert_true(response.status_code == 200, "Subscriber digest list did not render")
        digest_page = response.get_data(as_text=True)
        assert_true("Approved Ginger Market Signal" in digest_page, "Approved digest missing from subscriber list")
        assert_true("Hidden Draft Digest" not in digest_page, "Draft digest rendered to subscriber")
        assert_no_unsafe_text(digest_page, "subscriber digest list")

        response = client.get(f"/subscriber/intelligence-digests/{digest_id}")
        assert_true(response.status_code == 200, "Subscriber digest detail did not render")
        detail_page = response.get_data(as_text=True)
        assert_true("Approved safe digest summary" in detail_page, "Approved digest summary missing")
        assert_no_unsafe_text(detail_page, "subscriber digest detail")

        with app.app_context():
            list_audit = AuditLog.query.filter_by(action="subscriber_intelligence_digest_list_viewed").first()
            detail_audit = AuditLog.query.filter_by(action="subscriber_intelligence_digest_detail_viewed", entity_id=digest_id).first()
            assert_true(list_audit is not None, "Subscriber digest list audit missing")
            assert_true(detail_audit is not None, "Subscriber digest detail audit missing")
            assert_true(IntelligencePublicationCandidate.query.filter_by(status="approved").count() == 1, "Unexpected publication candidate state")
            assert_true(SubscriberIntelligenceDigest.query.filter_by(status="approved").count() == 1, "Unexpected approved digest count")

    print("Intelligence Engine Release 1 validation passed.")


if __name__ == "__main__":
    run_validation()
