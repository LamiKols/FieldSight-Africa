"""Validate Phase 4.2 commercial operations and request fulfilment.

This script uses an in-memory SQLite database and Flask's test client so it
does not touch Replit PostgreSQL data, payment providers, or real API secrets.
"""

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SESSION_SECRET", "phase-4-2-validation-secret")
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
    ApiClient,
    ApiKey,
    AuditLog,
    CommercialFulfilmentAction,
    CommercialRequest,
    License,
    LiveIntelligenceAccess,
    Payment,
    Subscription,
    User,
)


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


def future_date(days=45):
    return (utcnow().date() + timedelta(days=days)).isoformat()


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


def create_commercial_request(user, request_type, product, status="pending", organization="Validation Buyer Ltd"):
    commercial_request = CommercialRequest(
        user_id=user.id,
        request_type=request_type,
        organization_name=organization,
        contact_name=user.name,
        contact_email=user.email,
        requested_product=product,
        dataset_code="document_metadata" if request_type == "api_access" else "market_prices",
        region_code="SW",
        crop_name="Ginger",
        message=f"Please review {product} for Phase 4.2 validation.",
        context_json={
            "requested_scopes": ["document_metadata:read"] if request_type == "api_access" else [],
            "commercial_packaging_phase": "4.2-validation",
            "auto_access_granted": False,
        },
        status=status,
    )
    db.session.add(commercial_request)
    db.session.flush()
    return commercial_request


def create_api_client_with_key(user):
    api_client = ApiClient(
        name="Existing Subscriber API Client",
        slug="existing-subscriber-api-client",
        owner_user_id=user.id,
        status="active",
        scopes=["document_metadata:read"],
    )
    db.session.add(api_client)
    db.session.flush()
    api_key = ApiKey(
        api_client_id=api_client.id,
        name="Existing Key",
        status="active",
        scopes=["document_metadata:read"],
    )
    api_key.set_secret("phase-4-2-raw-secret")
    db.session.add(api_key)
    db.session.flush()
    return api_client, api_key


def count_payment_objects():
    return {
        "payments": Payment.query.count(),
        "subscriptions": Subscription.query.count(),
        "licenses": License.query.count(),
    }


def assert_payment_counts_unchanged(before_counts):
    after_counts = count_payment_objects()
    assert_true(after_counts == before_counts, f"Payment objects changed: before={before_counts}, after={after_counts}")


def approve_request(client, request_id, notes="Approved for Phase 4.2 validation."):
    response = client.post(
        f"/admin/commercial-requests/{request_id}/decision",
        data={
            "status": "approved_for_fulfilment",
            "review_notes": notes,
        },
        follow_redirects=False,
    )
    assert_true(response.status_code in (302, 303), f"Decision post failed for request {request_id}")


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

        subscriber = create_user("Validation Subscriber", "subscriber@example.com")
        other_user = create_user("Other Subscriber", "other@example.com")
        admin = create_user("Validation Admin", "admin@example.com", role="admin")

        _existing_client, existing_key = create_api_client_with_key(subscriber)
        api_request = create_commercial_request(subscriber, "api_access", "API Metadata Access")
        live_request = create_commercial_request(subscriber, "live_intelligence", "Live Market Intelligence")
        upgrade_request = create_commercial_request(subscriber, "upgrade", "National Upgrade")
        rejected_api_request = create_commercial_request(subscriber, "api_access", "Rejected API Metadata")
        cancelled_live_request = create_commercial_request(subscriber, "live_intelligence", "Cancelled Live Access")
        other_request = create_commercial_request(other_user, "upgrade", "Other Private Upgrade", organization="Other Buyer Ltd")
        db.session.commit()

        ids = {
            "subscriber": subscriber.id,
            "admin": admin.id,
            "api_request": api_request.id,
            "live_request": live_request.id,
            "upgrade_request": upgrade_request.id,
            "rejected_api_request": rejected_api_request.id,
            "cancelled_live_request": cancelled_live_request.id,
            "other_request": other_request.id,
        }
        raw_hash = existing_key.key_hash
        raw_secret = "phase-4-2-raw-secret"

    client = app.test_client()

    for path in [
        "/admin/commercial-requests",
        f"/admin/commercial-requests/{ids['api_request']}",
    ]:
        response = client.get(path, follow_redirects=False)
        assert_true(response.status_code == 302 and "/login" in response.headers.get("Location", ""), f"{path} did not require login")

    with client:
        login(client, "subscriber@example.com")
        for path in [
            "/admin/commercial-requests",
            f"/admin/commercial-requests/{ids['api_request']}",
        ]:
            response = client.get(path, follow_redirects=False)
            assert_true(response.status_code in (302, 303), f"{path} was not admin-only")

        response = client.get("/subscriber/commercial-requests")
        assert_true(response.status_code == 200, "Subscriber commercial request list did not render")
        page = response.get_data(as_text=True)
        assert_true("API Metadata Access" in page, "Subscriber list did not show own API request")
        assert_true("Other Private Upgrade" not in page, "Subscriber list leaked another user's commercial request")

        response = client.get(f"/subscriber/commercial-requests/{ids['api_request']}")
        assert_true(response.status_code == 200, "Subscriber own request detail did not render")
        assert_true("API Metadata Access" in response.get_data(as_text=True), "Subscriber request detail missed own request")

        response = client.get(f"/subscriber/commercial-requests/{ids['other_request']}")
        assert_true(response.status_code == 404, "Subscriber could view another user's commercial request")
        logout(client)

        login(client, "admin@example.com")
        response = client.get("/admin/commercial-requests")
        assert_true(response.status_code == 200, "Admin commercial request queue did not render")
        page = response.get_data(as_text=True)
        assert_true("Commercial Requests" in page, "Admin commercial queue title missing")
        assert_true("API Metadata Access" in page, "Admin queue missing API request")
        assert_true("Other Private Upgrade" in page, "Admin queue missing another subscriber request")

        response = client.get(f"/admin/commercial-requests/{ids['api_request']}")
        assert_true(response.status_code == 200, "Admin commercial request detail did not render")
        page = response.get_data(as_text=True)
        assert_true("Controlled Fulfilment" in page, "Admin detail missing fulfilment section")
        assert_true(raw_secret not in page, "Raw API secret leaked on admin request detail")
        assert_true(raw_hash not in page, "API key hash leaked on admin request detail")
        assert_true("key_hash" not in page, "API key hash field name leaked on admin request detail")

        approve_request(client, ids["api_request"])
        with app.app_context():
            refreshed = db.session.get(CommercialRequest, ids["api_request"])
            assert_true(refreshed.status == "approved_for_fulfilment", "Admin decision status did not persist")
            assert_true(refreshed.reviewed_by_user_id == ids["admin"], "Admin decision reviewer was not recorded")
            assert_true(refreshed.reviewed_at is not None, "Admin decision timestamp missing")
            decision_audit = AuditLog.query.filter_by(
                action="admin_commercial_request_status_updated",
                entity_id=ids["api_request"],
            ).first()
            assert_true(decision_audit is not None, "Admin decision audit log missing")
            assert_true(decision_audit.after_values.get("payment_flow_changed") is False, "Decision audit did not record payment non-change")

            baseline_clients = ApiClient.query.count()
            baseline_keys = ApiKey.query.count()

        response = client.post(
            f"/admin/commercial-requests/{ids['api_request']}/fulfilment",
            data={
                "action_type": "api_client_setup",
                "notes": "Create setup record only. No API key should be generated.",
            },
            follow_redirects=True,
        )
        assert_true(response.status_code == 200, "API fulfilment did not redirect to detail")
        page = response.get_data(as_text=True)
        assert_true("No API key was created" in page, "API fulfilment confirmation missing")
        assert_true(raw_secret not in page, "Raw API secret leaked after API fulfilment")
        assert_true(raw_hash not in page, "API key hash leaked after API fulfilment")
        assert_true("key_hash" not in page, "API key hash field name leaked after API fulfilment")
        with app.app_context():
            assert_true(ApiClient.query.count() == baseline_clients + 1, "API fulfilment did not create one API client setup record")
            assert_true(ApiKey.query.count() == baseline_keys, "API fulfilment created an API key")
            api_client = ApiClient.query.filter_by(slug=f"commercial-request-{ids['api_request']}-api-client").one()
            assert_true(api_client.status == "pending", "API setup record should remain pending")
            assert_true(api_client.owner_user_id == ids["subscriber"], "API setup record owner mismatch")
            fulfilment_action = CommercialFulfilmentAction.query.filter_by(
                commercial_request_id=ids["api_request"],
                action_type="api_client_setup",
            ).first()
            assert_true(fulfilment_action is not None, "API fulfilment action missing")
            assert_true(fulfilment_action.resulting_api_client_id == api_client.id, "API fulfilment action was not linked to client")
            fulfilment_audit = AuditLog.query.filter_by(
                action="admin_commercial_request_fulfilment_recorded",
                entity_id=ids["api_request"],
            ).first()
            assert_true(fulfilment_audit is not None, "API fulfilment audit log missing")
            assert_true(fulfilment_audit.after_values.get("api_key_created") is False, "API fulfilment audit did not record no-key behavior")

        with app.app_context():
            live_count_before_decision = LiveIntelligenceAccess.query.count()
        approve_request(client, ids["live_request"])
        with app.app_context():
            assert_true(
                LiveIntelligenceAccess.query.count() == live_count_before_decision,
                "Approving Live Intelligence request created access before fulfilment",
            )
        response = client.post(
            f"/admin/commercial-requests/{ids['live_request']}/fulfilment",
            data={
                "action_type": "live_intelligence_access",
                "notes": "Explicit admin fulfilment for Live Intelligence.",
                "start_date": utcnow().date().isoformat(),
                "end_date": future_date(60),
                "regions": ["SW", "NE"],
                "crops": "Ginger, Maize",
            },
            follow_redirects=False,
        )
        assert_true(response.status_code in (302, 303), "Live Intelligence fulfilment did not redirect")
        with app.app_context():
            assert_true(
                LiveIntelligenceAccess.query.count() == live_count_before_decision + 1,
                "Live Intelligence fulfilment did not create access",
            )
            live_access = LiveIntelligenceAccess.query.order_by(LiveIntelligenceAccess.id.desc()).first()
            assert_true(live_access.active is True, "Live Intelligence fulfilment did not activate access")
            assert_true(live_access.regions_selected == ["SW", "NE"], "Live Intelligence regions were not stored")
            live_action = CommercialFulfilmentAction.query.filter_by(
                commercial_request_id=ids["live_request"],
                action_type="live_intelligence_access",
            ).first()
            assert_true(live_action is not None, "Live Intelligence fulfilment action missing")
            assert_true(live_action.resulting_live_intelligence_access_id == live_access.id, "Live fulfilment action was not linked")

        approve_request(client, ids["upgrade_request"])
        with app.app_context():
            payment_counts = count_payment_objects()
        response = client.post(
            f"/admin/commercial-requests/{ids['upgrade_request']}/fulfilment",
            data={
                "action_type": "upgrade_followup",
                "notes": "Commercial team contacted subscriber. Payment provider flow remains unchanged.",
            },
            follow_redirects=False,
        )
        assert_true(response.status_code in (302, 303), "Upgrade fulfilment did not redirect")
        with app.app_context():
            assert_payment_counts_unchanged(payment_counts)
            upgrade_action = CommercialFulfilmentAction.query.filter_by(
                commercial_request_id=ids["upgrade_request"],
                action_type="upgrade_followup",
            ).first()
            assert_true(upgrade_action is not None, "Upgrade fulfilment action missing")
            assert_true(upgrade_action.metadata_json.get("payment_flow_changed") is False, "Upgrade action did not record payment non-change")

        response = client.post(
            f"/admin/commercial-requests/{ids['rejected_api_request']}/decision",
            data={"status": "rejected", "review_notes": "Rejected during validation."},
            follow_redirects=False,
        )
        assert_true(response.status_code in (302, 303), "Rejected decision did not redirect")
        with app.app_context():
            clients_before_rejected_fulfilment = ApiClient.query.count()
        response = client.post(
            f"/admin/commercial-requests/{ids['rejected_api_request']}/fulfilment",
            data={"action_type": "api_client_setup", "notes": "This should be blocked."},
            follow_redirects=False,
        )
        assert_true(response.status_code in (302, 303), "Rejected API fulfilment block did not redirect")
        with app.app_context():
            assert_true(ApiClient.query.count() == clients_before_rejected_fulfilment, "Rejected request created an API client")
            blocked_audit = AuditLog.query.filter_by(
                action="admin_commercial_request_fulfilment_blocked",
                entity_id=ids["rejected_api_request"],
            ).first()
            assert_true(blocked_audit is not None, "Rejected request blocked fulfilment audit missing")

        response = client.post(
            f"/admin/commercial-requests/{ids['cancelled_live_request']}/decision",
            data={"status": "cancelled", "review_notes": "Cancelled during validation."},
            follow_redirects=False,
        )
        assert_true(response.status_code in (302, 303), "Cancelled decision did not redirect")
        with app.app_context():
            live_before_cancelled_fulfilment = LiveIntelligenceAccess.query.count()
        response = client.post(
            f"/admin/commercial-requests/{ids['cancelled_live_request']}/fulfilment",
            data={
                "action_type": "live_intelligence_access",
                "notes": "This should be blocked.",
                "start_date": utcnow().date().isoformat(),
                "end_date": future_date(30),
                "regions": ["SW"],
            },
            follow_redirects=False,
        )
        assert_true(response.status_code in (302, 303), "Cancelled Live fulfilment block did not redirect")
        with app.app_context():
            assert_true(
                LiveIntelligenceAccess.query.count() == live_before_cancelled_fulfilment,
                "Cancelled request created Live Intelligence access",
            )
            blocked_live_audit = AuditLog.query.filter_by(
                action="admin_commercial_request_fulfilment_blocked",
                entity_id=ids["cancelled_live_request"],
            ).first()
            assert_true(blocked_live_audit is not None, "Cancelled request blocked fulfilment audit missing")

    print("Phase 4.2 commercial operations validation passed.")


if __name__ == "__main__":
    run_validation()
