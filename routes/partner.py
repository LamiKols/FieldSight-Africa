"""Partner data portal routes."""

from datetime import datetime
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from models import (
    ACTOR_TYPES,
    COMMON_STATUSES,
    PARTNER_DATASET_TYPES,
    PARTNER_ROLES,
    ActorCertification,
    ActorContact,
    ActorConstraint,
    ActorExportProfile,
    ActorLocation,
    AuditLog,
    Crop,
    MarketActor,
    PartnerOrganization,
    PartnerRecordChange,
    PartnerUpdateBatch,
    PartnerUserProfile,
    Region,
    db,
)

partner_bp = Blueprint("partner", __name__, url_prefix="/partner")

EDITOR_ROLES = ("partner_admin", "data_editor")
SUBMITTER_ROLES = ("partner_admin", "data_reviewer")
RESTRICTED_CONTACT_ROLES = ("partner_admin", "data_editor", "data_reviewer")


def get_partner_profile_for_user(user):
    if not user or not getattr(user, "is_authenticated", False):
        return None

    return (
        PartnerUserProfile.query.join(PartnerOrganization)
        .filter(
            PartnerUserProfile.user_id == user.id,
            PartnerUserProfile.status == "active",
            PartnerUserProfile.partner_role.in_(PARTNER_ROLES),
            PartnerOrganization.status == "active",
        )
        .order_by(PartnerUserProfile.updated_at.desc())
        .first()
    )


def get_current_partner_profile():
    return get_partner_profile_for_user(current_user)


def get_current_partner_org():
    profile = get_current_partner_profile()
    if not profile:
        return None
    return profile.partner_organization


def require_partner_user(func):
    @wraps(func)
    def decorated_function(*args, **kwargs):
        profile = get_current_partner_profile()
        if not profile:
            flash("Partner portal access requires an active partner profile.", "error")
            return redirect(url_for("subscriber.dashboard"))
        return func(*args, **kwargs)

    return decorated_function


def require_partner_role(*allowed_roles):
    def decorator(func):
        @wraps(func)
        def decorated_function(*args, **kwargs):
            profile = get_current_partner_profile()
            if not profile:
                flash("Partner portal access requires an active partner profile.", "error")
                return redirect(url_for("subscriber.dashboard"))
            if profile.partner_role != "partner_admin" and profile.partner_role not in allowed_roles:
                flash("Your partner role does not allow that action.", "error")
                return redirect(url_for("partner.dashboard"))
            return func(*args, **kwargs)

        return decorated_function

    return decorator


def can_view_restricted_contacts(profile):
    return bool(profile and profile.partner_role in RESTRICTED_CONTACT_ROLES)


def can_edit_partner_records(profile):
    return bool(profile and profile.partner_role in EDITOR_ROLES)


def can_submit_partner_batches(profile):
    return bool(profile and profile.partner_role in SUBMITTER_ROLES)


def get_partner_actor_or_404(actor_id, profile):
    actor = MarketActor.query.filter_by(
        id=actor_id,
        partner_organization_id=profile.partner_organization_id,
    ).first()
    if not actor:
        abort(404)
    return actor


def get_partner_batch_or_404(batch_id, profile):
    batch = PartnerUpdateBatch.query.filter_by(
        id=batch_id,
        partner_organization_id=profile.partner_organization_id,
    ).first()
    if not batch:
        abort(404)
    return batch


def clean_form_value(field_name):
    value = request.form.get(field_name, "")
    if value is None:
        return ""
    return value.strip()


def parse_optional_int(field_name, label, errors):
    value = clean_form_value(field_name)
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        errors.append(f"{label} must be a number.")
        return None


def parse_optional_date(field_name, label, errors):
    value = clean_form_value(field_name)
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        errors.append(f"{label} must use YYYY-MM-DD format.")
        return None


def parse_actor_form(profile):
    errors = []
    name = clean_form_value("name")
    actor_type = clean_form_value("actor_type")
    status = clean_form_value("status") or "active"
    registration_status = clean_form_value("registration_status")
    commodity_category = clean_form_value("commodity_category")
    source_reference = clean_form_value("source_reference")
    date_of_registration = parse_optional_date("date_of_registration", "Date of registration", errors)
    crop_id = parse_optional_int("crop_id", "Crop", errors)
    region_id = parse_optional_int("region_id", "Region", errors)
    years_in_export_trade = parse_optional_int("years_in_export_trade", "Years in export trade", errors)

    if not name:
        errors.append("Actor name is required.")
    if actor_type not in ACTOR_TYPES:
        errors.append("Please select a supported actor type.")
    if status not in COMMON_STATUSES:
        errors.append("Please select a supported actor status.")

    crop = None
    if crop_id:
        crop = Crop.query.get(crop_id)
        if not crop:
            errors.append("Selected crop was not found.")

    region = None
    if region_id:
        region = Region.query.get(region_id)
        if not region:
            errors.append("Selected region was not found.")

    constraint_values = [
        clean_form_value("constraint_category"),
        clean_form_value("constraint_text"),
        clean_form_value("constraint_severity"),
    ]
    if any(constraint_values) and not clean_form_value("constraint_text"):
        errors.append("Constraint text is required when adding a constraint.")

    batch_id = parse_optional_int("batch_id", "Draft batch", errors)
    selected_batch = None
    if batch_id:
        selected_batch = PartnerUpdateBatch.query.filter_by(
            id=batch_id,
            partner_organization_id=profile.partner_organization_id,
            status="draft",
        ).first()
        if not selected_batch:
            errors.append("Selected batch must be a draft batch for your partner organization.")

    return errors, {
        "name": name,
        "actor_type": actor_type,
        "status": status,
        "registration_status": registration_status or None,
        "commodity_category": commodity_category or (crop.name if crop else None),
        "source_reference": source_reference or None,
        "date_of_registration": date_of_registration,
        "crop_id": crop_id,
        "region_id": region_id,
        "years_in_export_trade": years_in_export_trade,
        "selected_batch": selected_batch,
    }


def update_actor_core(actor, values, profile):
    actor.name = values["name"]
    actor.actor_type = values["actor_type"]
    actor.status = values["status"]
    actor.registration_status = values["registration_status"]
    actor.commodity_category = values["commodity_category"]
    actor.source_reference = values["source_reference"]
    actor.date_of_registration = values["date_of_registration"]
    actor.crop_id = values["crop_id"]
    actor.updated_by_id = current_user.id
    actor.partner_organization_id = profile.partner_organization_id


def form_has_any(*field_names):
    return any(clean_form_value(field_name) for field_name in field_names)


def update_actor_location(actor, values):
    if not form_has_any("location_text", "state_name", "lga_name") and not values["region_id"]:
        return

    location = actor.location
    if not location:
        location = ActorLocation(market_actor_id=actor.id)
        db.session.add(location)

    location.location_text = clean_form_value("location_text") or None
    location.location = location.location_text
    location.region_id = values["region_id"]
    location.state_name = clean_form_value("state_name") or None
    location.lga_name = clean_form_value("lga_name") or None
    location.country = clean_form_value("country") or "Nigeria"
    location.is_primary = True


def update_actor_contact(actor):
    if not form_has_any("contact_role", "contact_name", "contact_phone", "contact_email", "contact_notes"):
        return

    contact = actor.contacts[0] if actor.contacts else None
    if not contact:
        contact = ActorContact(market_actor_id=actor.id)
        db.session.add(contact)

    contact.contact_role = clean_form_value("contact_role") or None
    contact.contact_name = clean_form_value("contact_name") or None
    contact.phone = clean_form_value("contact_phone") or None
    contact.email = clean_form_value("contact_email") or None
    contact.notes = clean_form_value("contact_notes") or None
    contact.restricted = request.form.get("contact_restricted", "true") == "true"
    contact.visibility_level = "hidden" if contact.restricted else "metadata_only"
    contact.is_primary = True


def update_actor_export_profile(actor, values):
    if not form_has_any("trade_destination_name", "export_capacity", "export_capacity_unit", "port_of_exit", "export_notes") and values["years_in_export_trade"] is None:
        return

    profile = actor.export_profile
    if not profile:
        profile = ActorExportProfile(market_actor_id=actor.id)
        db.session.add(profile)

    profile.years_in_export_trade = values["years_in_export_trade"]
    profile.trade_destination_name = clean_form_value("trade_destination_name") or None
    profile.export_capacity = clean_form_value("export_capacity") or None
    profile.export_capacity_unit = clean_form_value("export_capacity_unit") or None
    profile.port_of_exit = clean_form_value("port_of_exit") or None
    profile.notes = clean_form_value("export_notes") or None


def update_actor_certification(actor):
    if not form_has_any("certification_name", "certificate_number", "reference_number", "issuing_body", "certification_notes"):
        return

    certification = actor.certifications[0] if actor.certifications else None
    if not certification:
        certification = ActorCertification(market_actor_id=actor.id)
        db.session.add(certification)

    certification.certification_name = clean_form_value("certification_name") or None
    certification.certificate_number = clean_form_value("certificate_number") or None
    certification.reference_number = clean_form_value("reference_number") or None
    certification.issuing_body = clean_form_value("issuing_body") or None
    certification.verification_status = clean_form_value("certification_verification_status") or "unverified"
    certification.status = clean_form_value("certification_status") or "active"
    certification.notes = clean_form_value("certification_notes") or None


def update_actor_constraint(actor):
    if not form_has_any("constraint_category", "constraint_text", "constraint_severity"):
        return

    constraint = actor.constraints[0] if actor.constraints else None
    if not constraint:
        constraint = ActorConstraint(market_actor_id=actor.id)
        db.session.add(constraint)

    constraint.constraint_category = clean_form_value("constraint_category") or None
    constraint.constraint_text = clean_form_value("constraint_text")
    constraint.severity = clean_form_value("constraint_severity") or None
    constraint.status = clean_form_value("constraint_status") or "active"


def apply_actor_form(actor, values, profile):
    update_actor_core(actor, values, profile)
    update_actor_location(actor, values)
    update_actor_contact(actor)
    update_actor_export_profile(actor, values)
    update_actor_certification(actor)
    update_actor_constraint(actor)


def iso_date(value):
    return value.isoformat() if value else None


def actor_snapshot(actor):
    location = actor.location
    contact = actor.contacts[0] if actor.contacts else None
    export_profile = actor.export_profile
    certification = actor.certifications[0] if actor.certifications else None
    constraint = actor.constraints[0] if actor.constraints else None

    return {
        "id": actor.id,
        "public_id": actor.public_id,
        "partner_organization_id": actor.partner_organization_id,
        "actor_type": actor.actor_type,
        "name": actor.name,
        "crop_id": actor.crop_id,
        "commodity_category": actor.commodity_category,
        "registration_status": actor.registration_status,
        "date_of_registration": iso_date(actor.date_of_registration),
        "status": actor.status,
        "source_reference": actor.source_reference,
        "location": {
            "location_text": location.location_text if location else None,
            "region_id": location.region_id if location else None,
            "state_name": location.state_name if location else None,
            "lga_name": location.lga_name if location else None,
            "country": location.country if location else None,
        },
        "contact": {
            "contact_role": contact.contact_role if contact else None,
            "contact_name": contact.contact_name if contact else None,
            "phone": contact.phone if contact else None,
            "email": contact.email if contact else None,
            "restricted": contact.restricted if contact else None,
        },
        "export_profile": {
            "years_in_export_trade": export_profile.years_in_export_trade if export_profile else None,
            "trade_destination_name": export_profile.trade_destination_name if export_profile else None,
            "export_capacity": export_profile.export_capacity if export_profile else None,
            "export_capacity_unit": export_profile.export_capacity_unit if export_profile else None,
            "port_of_exit": export_profile.port_of_exit if export_profile else None,
        },
        "certification": {
            "certification_name": certification.certification_name if certification else None,
            "certificate_number": certification.certificate_number if certification else None,
            "reference_number": certification.reference_number if certification else None,
            "issuing_body": certification.issuing_body if certification else None,
            "status": certification.status if certification else None,
        },
        "constraint": {
            "constraint_category": constraint.constraint_category if constraint else None,
            "constraint_text": constraint.constraint_text if constraint else None,
            "severity": constraint.severity if constraint else None,
            "status": constraint.status if constraint else None,
        },
    }


def add_audit_log(action, entity_type, entity_id, before_values=None, after_values=None, organization_id=None):
    db.session.add(AuditLog(
        user_id=current_user.id,
        organization_type="partner_organization",
        organization_id=organization_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_values=before_values,
        after_values=after_values,
        ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
        user_agent=request.headers.get("User-Agent"),
    ))


def get_or_create_direct_change_batch(profile):
    month = datetime.utcnow().strftime("%Y-%m")
    title = f"Direct actor changes - {month}"
    batch = PartnerUpdateBatch.query.filter_by(
        partner_organization_id=profile.partner_organization_id,
        title=title,
        dataset_type="actor_registry",
        status="draft",
    ).first()

    if batch:
        return batch

    batch = PartnerUpdateBatch(
        partner_organization_id=profile.partner_organization_id,
        title=title,
        dataset_type="actor_registry",
        reporting_month=month,
        status="draft",
        notes="Auto-created by the partner actor form to track direct create/edit changes.",
    )
    db.session.add(batch)
    db.session.flush()
    add_audit_log(
        "partner_batch_created",
        "partner_update_batch",
        batch.id,
        after_values=batch_snapshot(batch),
        organization_id=profile.partner_organization_id,
    )
    return batch


def create_record_change(batch, actor, change_type, before_values, after_values):
    db.session.add(PartnerRecordChange(
        partner_update_batch_id=batch.id,
        market_actor_id=actor.id,
        created_by_user_id=current_user.id,
        entity_type="market_actor",
        entity_id=actor.id,
        change_type=change_type,
        before_values=before_values,
        after_values=after_values,
        status=batch.status,
    ))


def batch_snapshot(batch):
    return {
        "id": batch.id,
        "partner_organization_id": batch.partner_organization_id,
        "title": batch.title,
        "dataset_type": batch.dataset_type,
        "reporting_month": batch.reporting_month,
        "status": batch.status,
        "submitted_at": batch.submitted_at.isoformat() if batch.submitted_at else None,
    }


def actor_form_context(profile, actor=None):
    return {
        "profile": profile,
        "organization": profile.partner_organization,
        "actor": actor,
        "actor_types": ACTOR_TYPES,
        "status_choices": COMMON_STATUSES,
        "regions": Region.query.filter_by(active=True).order_by(Region.name).all(),
        "crops": Crop.query.filter_by(active=True).order_by(Crop.name).all(),
        "draft_batches": PartnerUpdateBatch.query.filter_by(
            partner_organization_id=profile.partner_organization_id,
            status="draft",
        ).order_by(PartnerUpdateBatch.updated_at.desc()).all(),
    }


@partner_bp.route("/")
@login_required
@require_partner_user
def dashboard():
    profile = get_current_partner_profile()
    org = profile.partner_organization
    actor_count = MarketActor.query.filter_by(partner_organization_id=org.id).count()
    draft_batch_count = PartnerUpdateBatch.query.filter_by(
        partner_organization_id=org.id,
        status="draft",
    ).count()
    submitted_batch_count = PartnerUpdateBatch.query.filter_by(
        partner_organization_id=org.id,
        status="submitted",
    ).count()

    return render_template(
        "partner/dashboard.html",
        profile=profile,
        organization=org,
        actor_count=actor_count,
        draft_batch_count=draft_batch_count,
        submitted_batch_count=submitted_batch_count,
        can_edit=can_edit_partner_records(profile),
        can_submit=can_submit_partner_batches(profile),
    )


@partner_bp.route("/actors")
@login_required
@require_partner_user
def actors():
    profile = get_current_partner_profile()
    actor_rows = (
        MarketActor.query.filter_by(partner_organization_id=profile.partner_organization_id)
        .order_by(MarketActor.updated_at.desc())
        .all()
    )
    return render_template(
        "partner/actors.html",
        profile=profile,
        organization=profile.partner_organization,
        actors=actor_rows,
        can_edit=can_edit_partner_records(profile),
    )


@partner_bp.route("/actors/new", methods=["GET", "POST"])
@login_required
@require_partner_user
@require_partner_role(*EDITOR_ROLES)
def new_actor():
    profile = get_current_partner_profile()

    if request.method == "POST":
        errors, values = parse_actor_form(profile)
        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("partner/actor_form.html", **actor_form_context(profile))

        actor = MarketActor(
            partner_organization_id=profile.partner_organization_id,
            created_by_user_id=current_user.id,
            updated_by_id=current_user.id,
            actor_type=values["actor_type"],
            name=values["name"],
        )
        db.session.add(actor)
        db.session.flush()
        apply_actor_form(actor, values, profile)
        db.session.flush()

        after_values = actor_snapshot(actor)
        batch = values["selected_batch"] or get_or_create_direct_change_batch(profile)
        create_record_change(batch, actor, "create", None, after_values)
        add_audit_log(
            "partner_actor_created",
            "market_actor",
            actor.id,
            after_values=after_values,
            organization_id=profile.partner_organization_id,
        )
        db.session.commit()

        flash("Actor record created.", "success")
        return redirect(url_for("partner.actor_detail", actor_id=actor.id))

    return render_template("partner/actor_form.html", **actor_form_context(profile))


@partner_bp.route("/actors/<int:actor_id>")
@login_required
@require_partner_user
def actor_detail(actor_id):
    profile = get_current_partner_profile()
    actor = get_partner_actor_or_404(actor_id, profile)
    return render_template(
        "partner/actor_detail.html",
        profile=profile,
        organization=profile.partner_organization,
        actor=actor,
        can_edit=can_edit_partner_records(profile),
        show_restricted_contacts=can_view_restricted_contacts(profile),
    )


@partner_bp.route("/actors/<int:actor_id>/edit", methods=["GET", "POST"])
@login_required
@require_partner_user
@require_partner_role(*EDITOR_ROLES)
def edit_actor(actor_id):
    profile = get_current_partner_profile()
    actor = get_partner_actor_or_404(actor_id, profile)

    if request.method == "POST":
        errors, values = parse_actor_form(profile)
        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("partner/actor_form.html", **actor_form_context(profile, actor=actor))

        before_values = actor_snapshot(actor)
        apply_actor_form(actor, values, profile)
        db.session.flush()
        after_values = actor_snapshot(actor)
        batch = values["selected_batch"] or get_or_create_direct_change_batch(profile)
        create_record_change(batch, actor, "update", before_values, after_values)
        add_audit_log(
            "partner_actor_updated",
            "market_actor",
            actor.id,
            before_values=before_values,
            after_values=after_values,
            organization_id=profile.partner_organization_id,
        )
        db.session.commit()

        flash("Actor record updated.", "success")
        return redirect(url_for("partner.actor_detail", actor_id=actor.id))

    return render_template("partner/actor_form.html", **actor_form_context(profile, actor=actor))


@partner_bp.route("/batches")
@login_required
@require_partner_user
def batches():
    profile = get_current_partner_profile()
    batch_rows = (
        PartnerUpdateBatch.query.filter_by(partner_organization_id=profile.partner_organization_id)
        .order_by(PartnerUpdateBatch.updated_at.desc())
        .all()
    )
    return render_template(
        "partner/batches.html",
        profile=profile,
        organization=profile.partner_organization,
        batches=batch_rows,
        can_edit=can_edit_partner_records(profile),
    )


@partner_bp.route("/batches/new", methods=["GET", "POST"])
@login_required
@require_partner_user
@require_partner_role(*EDITOR_ROLES)
def new_batch():
    profile = get_current_partner_profile()

    if request.method == "POST":
        title = clean_form_value("title")
        dataset_type = clean_form_value("dataset_type") or "actor_registry"
        reporting_month = clean_form_value("reporting_month")
        notes = clean_form_value("notes")

        if not title:
            flash("Batch title is required.", "error")
            return render_template("partner/batch_form.html", profile=profile, organization=profile.partner_organization, dataset_types=PARTNER_DATASET_TYPES)
        if dataset_type not in PARTNER_DATASET_TYPES:
            flash("Please select a supported dataset type.", "error")
            return render_template("partner/batch_form.html", profile=profile, organization=profile.partner_organization, dataset_types=PARTNER_DATASET_TYPES)

        batch = PartnerUpdateBatch(
            partner_organization_id=profile.partner_organization_id,
            title=title,
            dataset_type=dataset_type,
            reporting_month=reporting_month or None,
            status="draft",
            notes=notes or None,
        )
        db.session.add(batch)
        db.session.flush()
        add_audit_log(
            "partner_batch_created",
            "partner_update_batch",
            batch.id,
            after_values=batch_snapshot(batch),
            organization_id=profile.partner_organization_id,
        )
        db.session.commit()

        flash("Draft batch created.", "success")
        return redirect(url_for("partner.batch_detail", batch_id=batch.id))

    return render_template(
        "partner/batch_form.html",
        profile=profile,
        organization=profile.partner_organization,
        dataset_types=PARTNER_DATASET_TYPES,
    )


@partner_bp.route("/batches/<int:batch_id>")
@login_required
@require_partner_user
def batch_detail(batch_id):
    profile = get_current_partner_profile()
    batch = get_partner_batch_or_404(batch_id, profile)
    return render_template(
        "partner/batch_detail.html",
        profile=profile,
        organization=profile.partner_organization,
        batch=batch,
        can_submit=can_submit_partner_batches(profile),
    )


@partner_bp.route("/batches/<int:batch_id>/submit", methods=["POST"])
@login_required
@require_partner_user
@require_partner_role(*SUBMITTER_ROLES)
def submit_batch(batch_id):
    profile = get_current_partner_profile()
    batch = get_partner_batch_or_404(batch_id, profile)

    if batch.status != "draft":
        flash("Only draft batches can be submitted.", "error")
        return redirect(url_for("partner.batch_detail", batch_id=batch.id))

    before_values = batch_snapshot(batch)
    batch.status = "submitted"
    batch.submitted_at = datetime.utcnow()
    batch.submitted_by_user_id = current_user.id
    for record_change in batch.record_changes:
        record_change.status = "submitted"
    db.session.flush()
    after_values = batch_snapshot(batch)
    add_audit_log(
        "partner_batch_submitted",
        "partner_update_batch",
        batch.id,
        before_values=before_values,
        after_values=after_values,
        organization_id=profile.partner_organization_id,
    )
    db.session.commit()

    flash("Batch submitted for review.", "success")
    return redirect(url_for("partner.batch_detail", batch_id=batch.id))
