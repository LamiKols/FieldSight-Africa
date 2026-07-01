"""Partner actor registry import helpers.

The import foundation stores sanitized row-review metadata in partner batch
records. Real contact values are only written to restricted ActorContact rows
when a new draft actor is created for partner/admin review.
"""

import csv
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime

from werkzeug.utils import secure_filename

from models import (
    ActorCertification,
    ActorContact,
    ActorConstraint,
    ActorExportProfile,
    ActorLocation,
    Commodity,
    Crop,
    LGA,
    MarketActor,
    PartnerRecordChange,
    PartnerUpdateBatch,
    Region,
    State,
    db,
)


IMPORT_ROW_ENTITY_TYPE = "actor_registry_import_row"
IMPORT_BATCH_NOTE_MARKER = "bulk_import=true"
MAX_IMPORT_ROWS = 1000

CANONICAL_COLUMNS = {
    "commodity_category": "COMMODITY CATEGORY",
    "actor_name": "FARMER/AGGREAGATOR",
    "location": "LOCATION",
    "state": "STATE",
    "phone": "PHONE",
    "email": "EMAIL",
    "lga": "LGA",
    "registration_status": "REGISTRATION STATUS",
    "date_of_registration": "DATE OF REGISTRATION",
    "years_in_export_trade": "NUMBER OF YEARS IN EXPORT TRADE",
    "trade_destination": "TRADE DESTINATION",
    "export_capacity": "EXPORT CAPACITY",
    "certification": "ERTIFICATION",
    "port_of_exit": "PORT OF EXIT",
    "constraint": "CONSTRAINT",
}

COLUMN_ALIASES = {
    "COMMODITY CATEGORY": "commodity_category",
    "COMMODITY": "commodity_category",
    "CROP": "commodity_category",
    "FARMER/AGGREAGATOR": "actor_name",
    "FARMER/AGGREGATOR": "actor_name",
    "FARMER AGGREAGATOR": "actor_name",
    "FARMER AGGREGATOR": "actor_name",
    "ACTOR NAME": "actor_name",
    "EXPORTER NAME": "actor_name",
    "LOCATION": "location",
    "STATE": "state",
    "PHONE": "phone",
    "PHONE NUMBER": "phone",
    "EMAIL": "email",
    "EMAIL ADDRESS": "email",
    "LGA": "lga",
    "REGISTRATION STATUS": "registration_status",
    "DATE OF REGISTRATION": "date_of_registration",
    "NUMBER OF YEARS IN EXPORT TRADE": "years_in_export_trade",
    "YEARS IN EXPORT TRADE": "years_in_export_trade",
    "TRADE DESTINATION": "trade_destination",
    "EXPORT CAPACITY": "export_capacity",
    "ERTIFICATION": "certification",
    "CERTIFICATION": "certification",
    "PORT OF EXIT": "port_of_exit",
    "CONSTRAINT": "constraint",
    "DATA FRESHNESS DATE": "data_freshness_date",
    "LAST VERIFIED DATE": "last_verified_date",
    "SOURCE OF UPDATE": "update_source",
    "UPDATE SOURCE": "update_source",
    "UPDATE CYCLE": "update_cycle",
    "PARTNER NOTES": "partner_notes",
}

DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d")


def safe_text(value, limit=255):
    cleaned = " ".join(str(value or "").strip().split())
    if len(cleaned) > limit:
        return cleaned[:limit].rstrip()
    return cleaned


def normalize_header(value):
    text = safe_text(value).upper()
    text = re.sub(r"[^A-Z0-9/ ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_match_value(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def parse_date_value(value):
    cleaned = safe_text(value, limit=80)
    if not cleaned:
        return None, None
    for date_format in DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, date_format).date(), None
        except ValueError:
            continue
    return None, f"Could not parse date value '{cleaned}'."


def parse_int_value(value):
    cleaned = safe_text(value, limit=40)
    if not cleaned:
        return None, None
    try:
        return int(float(cleaned)), None
    except ValueError:
        return None, f"Years in export trade must be numeric; '{cleaned}' was stored as a warning."


def read_csv_rows(content):
    text = content.decode("utf-8-sig", errors="replace")
    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample)
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    return list(reader)


def column_index(cell_ref):
    letters = "".join(character for character in cell_ref if character.isalpha())
    index = 0
    for character in letters:
        index = index * 26 + (ord(character.upper()) - ord("A") + 1)
    return max(index - 1, 0)


def read_xlsx_rows(content):
    rows = []
    with zipfile.ZipFile(io.BytesIO(content)) as workbook:
        shared_strings = []
        if "xl/sharedStrings.xml" in workbook.namelist():
            shared_root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
            for item in shared_root.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"):
                shared_strings.append(item.text or "")
        sheet_name = "xl/worksheets/sheet1.xml"
        if sheet_name not in workbook.namelist():
            raise ValueError("The workbook must contain a first worksheet.")
        root = ET.fromstring(workbook.read(sheet_name))
        namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
        for row in root.iter(f"{namespace}row"):
            values = []
            for cell in row.iter(f"{namespace}c"):
                cell_type = cell.attrib.get("t")
                cell_value = cell.find(f"{namespace}v")
                value = cell_value.text if cell_value is not None else ""
                if cell_type == "s" and value:
                    value = shared_strings[int(value)] if int(value) < len(shared_strings) else ""
                cell_idx = column_index(cell.attrib.get("r", "A1"))
                while len(values) <= cell_idx:
                    values.append("")
                values[cell_idx] = value
            if any(safe_text(value) for value in values):
                rows.append(values)
    if not rows:
        return []
    headers = [safe_text(value) for value in rows[0]]
    return [
        {headers[index]: row[index] if index < len(row) else "" for index in range(len(headers))}
        for row in rows[1:]
    ]


def rows_from_upload(file_storage):
    if not file_storage or not file_storage.filename:
        return None, ["Please choose a CSV or XLSX spreadsheet."]

    filename = secure_filename(file_storage.filename)
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in {"csv", "txt", "xlsx"}:
        return None, ["Please upload a CSV or XLSX spreadsheet export."]

    content = file_storage.read()
    file_storage.seek(0)
    if not content:
        return None, ["The uploaded spreadsheet is empty."]

    try:
        rows = read_xlsx_rows(content) if extension == "xlsx" else read_csv_rows(content)
    except Exception as exc:
        return None, [f"Could not read spreadsheet safely: {exc}"]

    if len(rows) > MAX_IMPORT_ROWS:
        return None, [f"Imports are limited to {MAX_IMPORT_ROWS} rows per batch."]
    return rows, []


def normalized_import_row(raw_row):
    normalized = {key: "" for key in CANONICAL_COLUMNS}
    for header, value in (raw_row or {}).items():
        canonical_key = COLUMN_ALIASES.get(normalize_header(header))
        if canonical_key:
            normalized[canonical_key] = safe_text(value)
    return normalized


def find_state(value):
    cleaned = normalize_match_value(value)
    if not cleaned:
        return None
    return next(
        (
            state for state in State.query.filter_by(active=True).all()
            if normalize_match_value(state.name) == cleaned or normalize_match_value(state.code) == cleaned
        ),
        None,
    )


def find_lga(value, state=None):
    cleaned = normalize_match_value(value)
    if not cleaned:
        return None
    query = LGA.query.filter_by(active=True)
    if state:
        query = query.filter_by(state_id=state.id)
    return next((lga for lga in query.all() if normalize_match_value(lga.name) == cleaned), None)


def find_crop_or_commodity(value):
    cleaned = normalize_match_value(value)
    if not cleaned:
        return None, None
    crop = next(
        (item for item in Crop.query.filter_by(active=True).all() if normalize_match_value(item.name) == cleaned or normalize_match_value(item.code) == cleaned),
        None,
    )
    commodity = next(
        (
            item for item in Commodity.query.filter_by(active=True).all()
            if normalize_match_value(item.name) == cleaned or normalize_match_value(item.code) == cleaned or normalize_match_value(item.category) == cleaned
        ),
        None,
    )
    return crop, commodity


def infer_actor_type(fields):
    name_text = fields.get("actor_name", "").lower()
    if "farmer" in name_text:
        return "farmer"
    if "processor" in name_text:
        return "processor"
    if "cooperative" in name_text:
        return "cooperative"
    if "buyer" in name_text:
        return "buyer"
    if fields.get("trade_destination") or fields.get("export_capacity") or fields.get("port_of_exit"):
        return "exporter"
    return "aggregator"


def existing_actor_candidates(fields, partner_organization_id):
    actor_name_key = normalize_match_value(fields.get("actor_name"))
    commodity_key = normalize_match_value(fields.get("commodity_category"))
    state_key = normalize_match_value(fields.get("state"))
    lga_key = normalize_match_value(fields.get("lga"))
    location_key = normalize_match_value(fields.get("location"))
    candidates = []
    for actor in MarketActor.query.filter_by(partner_organization_id=partner_organization_id).all():
        if normalize_match_value(actor.name) != actor_name_key:
            continue
        actor_commodity_key = normalize_match_value(actor.commodity_category or (actor.crop.name if actor.crop else ""))
        location = actor.location
        actor_state_key = normalize_match_value(location.state_name if location else "")
        actor_lga_key = normalize_match_value(location.lga_name if location else "")
        actor_location_key = normalize_match_value(location.location_text if location else "")
        score = 1
        if commodity_key and commodity_key == actor_commodity_key:
            score += 1
        if state_key and state_key == actor_state_key:
            score += 1
        if lga_key and lga_key == actor_lga_key:
            score += 1
        if location_key and location_key == actor_location_key:
            score += 1
        candidates.append({"actor": actor, "score": score})
    return sorted(candidates, key=lambda item: item["score"], reverse=True)


def validate_import_row(raw_row, row_number, partner_organization_id, defaults):
    fields = normalized_import_row(raw_row)
    errors = []
    warnings = []

    if not fields.get("actor_name"):
        errors.append("Actor name is required.")

    crop, commodity = find_crop_or_commodity(fields.get("commodity_category"))
    if not fields.get("commodity_category"):
        warnings.append("Commodity category is missing; the row can be corrected before review.")
    elif not crop and not commodity:
        warnings.append("Commodity category will be stored as partner text because no reference match was found.")

    state = find_state(fields.get("state"))
    if fields.get("state") and not state:
        warnings.append("State was not matched to a reference value and will be captured as text.")
    lga = find_lga(fields.get("lga"), state=state)
    if fields.get("lga") and not lga:
        warnings.append("LGA was not matched to a reference value and will be captured as text.")

    registration_date, date_error = parse_date_value(fields.get("date_of_registration"))
    if date_error:
        errors.append(date_error)
    freshness_date, freshness_error = parse_date_value(fields.get("data_freshness_date") or defaults.get("data_freshness_date"))
    if freshness_error:
        warnings.append(freshness_error)
    last_verified_date, verified_error = parse_date_value(fields.get("last_verified_date") or defaults.get("last_verified_date"))
    if verified_error:
        warnings.append(verified_error)
    years_in_trade, years_warning = parse_int_value(fields.get("years_in_export_trade"))
    if years_warning:
        warnings.append(years_warning)

    candidates = existing_actor_candidates(fields, partner_organization_id) if fields.get("actor_name") else []
    action = "invalid"
    if not errors:
        if candidates and candidates[0]["score"] >= 3:
            action = "duplicate_warning"
            warnings.append("Likely duplicate detected; this row will not overwrite an existing actor.")
        elif candidates:
            action = "update_candidate"
            warnings.append("Existing actor candidate detected; no fields will be overwritten without review.")
        else:
            action = "create"

    safe_fields = {
        "actor_name": fields.get("actor_name"),
        "actor_type": infer_actor_type(fields),
        "commodity_category": fields.get("commodity_category"),
        "crop_id": crop.id if crop else (commodity.crop_id if commodity and commodity.crop_id else None),
        "commodity_id": commodity.id if commodity else None,
        "location_text": fields.get("location"),
        "state_id": state.id if state else None,
        "state_name": state.name if state else fields.get("state"),
        "lga_id": lga.id if lga else None,
        "lga_name": lga.name if lga else fields.get("lga"),
        "registration_status": fields.get("registration_status"),
        "date_of_registration": registration_date.isoformat() if registration_date else None,
        "years_in_export_trade": years_in_trade,
        "trade_destination_name": fields.get("trade_destination"),
        "export_capacity": fields.get("export_capacity"),
        "certification_name": fields.get("certification"),
        "port_of_exit": fields.get("port_of_exit"),
        "constraint_text": fields.get("constraint"),
        "data_freshness_date": freshness_date.isoformat() if freshness_date else None,
        "last_verified_date": last_verified_date.isoformat() if last_verified_date else None,
        "update_source": fields.get("update_source") or defaults.get("update_source") or "partner_bulk_upload",
        "update_cycle": fields.get("update_cycle") or defaults.get("update_cycle") or "monthly",
        "partner_notes": fields.get("partner_notes") or defaults.get("partner_notes"),
    }
    contact_values = {
        "phone": fields.get("phone"),
        "email": fields.get("email"),
    }
    duplicate_candidates = [
        {"actor_id": item["actor"].id, "actor_name": item["actor"].name, "score": item["score"]}
        for item in candidates[:3]
    ]

    return {
        "row_number": row_number,
        "row_status": "invalid" if errors else action,
        "action": action,
        "errors": errors,
        "warnings": warnings,
        "fields": safe_fields,
        "contact_values": contact_values,
        "contact_hints": {
            "phone_present": bool(contact_values["phone"]),
            "email_present": bool(contact_values["email"]),
        },
        "duplicate_candidates": duplicate_candidates,
    }


def date_from_iso(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def create_actor_from_import_row(partner_organization_id, user_id, batch, row_result):
    fields = row_result["fields"]
    actor = MarketActor(
        partner_organization_id=partner_organization_id,
        created_by_user_id=user_id,
        updated_by_id=user_id,
        actor_type=fields["actor_type"],
        name=fields["actor_name"],
        crop_id=fields["crop_id"],
        commodity_id=fields["commodity_id"],
        commodity_category=fields["commodity_category"],
        registration_status=fields["registration_status"] or None,
        date_of_registration=date_from_iso(fields["date_of_registration"]),
        status="pending_review",
        source_reference_type="partner_bulk_import",
        source_reference=f"import_batch_{batch.id}",
        metadata_json={
            "data_freshness_date": fields["data_freshness_date"],
            "last_verified_date": fields["last_verified_date"],
            "update_source": fields["update_source"],
            "update_cycle": fields["update_cycle"],
            "partner_notes": fields["partner_notes"],
            "import_batch_id": batch.id,
            "admin_review_status": "pending_review",
            "subscriber_safe": False,
        },
    )
    db.session.add(actor)
    db.session.flush()

    if any([fields["location_text"], fields["state_name"], fields["lga_name"], fields["state_id"], fields["lga_id"]]):
        db.session.add(ActorLocation(
            market_actor_id=actor.id,
            location=fields["location_text"],
            location_text=fields["location_text"],
            state_id=fields["state_id"],
            state_name=fields["state_name"],
            lga_id=fields["lga_id"],
            lga_name=fields["lga_name"],
            country="Nigeria",
            is_primary=True,
        ))

    contact_values = row_result.get("contact_values") or {}
    if contact_values.get("phone") or contact_values.get("email"):
        db.session.add(ActorContact(
            market_actor_id=actor.id,
            contact_role="registry_update_contact",
            phone=contact_values.get("phone") or None,
            email=contact_values.get("email") or None,
            restricted=True,
            visibility_level="hidden",
            is_primary=True,
            notes="Restricted contact captured from partner import.",
        ))

    if any([fields["years_in_export_trade"] is not None, fields["trade_destination_name"], fields["export_capacity"], fields["port_of_exit"]]):
        db.session.add(ActorExportProfile(
            market_actor_id=actor.id,
            years_in_export_trade=fields["years_in_export_trade"],
            trade_destination_name=fields["trade_destination_name"],
            export_capacity=fields["export_capacity"],
            port_of_exit=fields["port_of_exit"],
        ))

    if fields["certification_name"]:
        db.session.add(ActorCertification(
            market_actor_id=actor.id,
            certification_name=fields["certification_name"],
            verification_status="unverified",
            status="active",
            notes="Certification text captured from partner import for admin review.",
        ))

    if fields["constraint_text"]:
        db.session.add(ActorConstraint(
            market_actor_id=actor.id,
            constraint_category="partner_reported",
            constraint_text=fields["constraint_text"],
            severity="needs_review",
            status="active",
        ))

    db.session.flush()
    return actor


def safe_row_payload(row_result):
    return {
        "row_number": row_result["row_number"],
        "row_status": row_result["row_status"],
        "action": row_result["action"],
        "errors": row_result["errors"],
        "warnings": row_result["warnings"],
        "fields": row_result["fields"],
        "contact_hints": row_result["contact_hints"],
        "duplicate_candidates": row_result["duplicate_candidates"],
        "uploaded_file_path_stored": False,
        "contact_values_exposed": False,
        "auto_published": False,
        "subscriber_access_created": False,
    }


def create_import_batch_from_rows(partner_organization_id, user_id, raw_rows, title, reporting_month=None, defaults=None):
    defaults = defaults or {}
    batch = PartnerUpdateBatch(
        partner_organization_id=partner_organization_id,
        submitted_by_user_id=user_id,
        title=title or f"Live Actor Registry Import {datetime.utcnow().strftime('%Y-%m-%d')}",
        dataset_type="actor_registry",
        reporting_month=reporting_month,
        status="draft",
        notes=(
            f"{IMPORT_BATCH_NOTE_MARKER}; update_cycle={defaults.get('update_cycle') or 'monthly'}; "
            "uploaded_file_path_stored=false; contact_values_stored_only_in_restricted_contacts=true"
        ),
    )
    db.session.add(batch)
    db.session.flush()

    for index, raw_row in enumerate(raw_rows, start=2):
        row_result = validate_import_row(raw_row, index, partner_organization_id, defaults)
        actor = None
        if row_result["action"] == "create" and not row_result["errors"]:
            actor = create_actor_from_import_row(partner_organization_id, user_id, batch, row_result)
        elif row_result["action"] == "update_candidate" and row_result["duplicate_candidates"]:
            actor = db.session.get(MarketActor, row_result["duplicate_candidates"][0]["actor_id"])

        db.session.add(PartnerRecordChange(
            partner_update_batch_id=batch.id,
            market_actor_id=actor.id if actor else None,
            created_by_user_id=user_id,
            entity_type=IMPORT_ROW_ENTITY_TYPE,
            entity_id=actor.id if actor else None,
            change_type=row_result["action"],
            before_values=None if not actor or row_result["action"] == "create" else {
                "actor_id": actor.id,
                "actor_name": actor.name,
                "status": actor.status,
                "contact_values_exposed": False,
            },
            after_values=safe_row_payload(row_result),
            status="draft" if not row_result["errors"] else "needs_correction",
        ))
    db.session.flush()
    return batch


def create_import_batch_from_upload(partner_organization_id, user_id, file_storage, title, reporting_month=None, defaults=None):
    rows, errors = rows_from_upload(file_storage)
    if errors:
        return None, errors
    if not rows:
        return None, ["The spreadsheet did not contain any data rows."]
    batch = create_import_batch_from_rows(partner_organization_id, user_id, rows, title, reporting_month=reporting_month, defaults=defaults)
    return batch, []


def is_import_batch(batch):
    if not batch:
        return False
    if batch.notes and IMPORT_BATCH_NOTE_MARKER in batch.notes:
        return True
    return any(change.entity_type == IMPORT_ROW_ENTITY_TYPE for change in batch.record_changes)


def import_batch_rows(batch):
    return [
        change for change in batch.record_changes
        if change.entity_type == IMPORT_ROW_ENTITY_TYPE
    ]


def import_batch_summary(batch):
    rows = import_batch_rows(batch)
    actions = Counter((row.after_values or {}).get("action") for row in rows)
    invalid_rows = [
        row for row in rows
        if (row.after_values or {}).get("row_status") == "invalid" or row.status == "needs_correction"
    ]
    warning_rows = [
        row for row in rows
        if (row.after_values or {}).get("warnings")
    ]
    valid_rows = [row for row in rows if row not in invalid_rows]
    created_actor_rows = [
        row for row in rows
        if (row.after_values or {}).get("action") == "create" and row.market_actor_id
    ]
    freshness_values = [
        (row.after_values or {}).get("fields", {}).get("data_freshness_date")
        for row in rows
        if (row.after_values or {}).get("fields", {}).get("data_freshness_date")
    ]
    verified_values = [
        (row.after_values or {}).get("fields", {}).get("last_verified_date")
        for row in rows
        if (row.after_values or {}).get("fields", {}).get("last_verified_date")
    ]
    update_cycles = Counter(
        (row.after_values or {}).get("fields", {}).get("update_cycle") or "not_set"
        for row in rows
    )
    return {
        "total_rows": len(rows),
        "valid_rows": len(valid_rows),
        "rows_with_warnings": len(warning_rows),
        "rejected_rows": len(invalid_rows),
        "duplicates": actions.get("duplicate_warning", 0),
        "missing_required_fields": sum(1 for row in invalid_rows if "Actor name is required." in ((row.after_values or {}).get("errors") or [])),
        "create_rows": actions.get("create", 0),
        "update_candidates": actions.get("update_candidate", 0),
        "duplicate_warnings": actions.get("duplicate_warning", 0),
        "created_actors": len(created_actor_rows),
        "updated_actors": 0,
        "status": batch.status,
        "update_cycles": dict(update_cycles),
        "freshness_summary": {
            "earliest_data_freshness_date": min(freshness_values) if freshness_values else None,
            "latest_data_freshness_date": max(freshness_values) if freshness_values else None,
            "earliest_last_verified_date": min(verified_values) if verified_values else None,
            "latest_last_verified_date": max(verified_values) if verified_values else None,
        },
        "uploaded_file_path_exposed": False,
        "contact_values_exposed": False,
        "auto_published": False,
    }


def submit_import_batch(batch, user_id):
    rows = import_batch_rows(batch)
    submittable = [
        row for row in rows
        if (row.after_values or {}).get("row_status") != "invalid"
    ]
    if not submittable:
        return False, "No valid rows are available to submit."
    for row in rows:
        if row in submittable:
            row.status = "submitted"
        else:
            row.status = "needs_correction"
    batch.status = "submitted"
    batch.submitted_by_user_id = user_id
    batch.submitted_at = datetime.utcnow()
    db.session.flush()
    return True, "Valid import rows submitted for admin review."


def error_csv_for_import_batch(batch):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["row_number", "actor_name", "action", "status", "messages"])
    for row in import_batch_rows(batch):
        payload = row.after_values or {}
        errors = payload.get("errors") or []
        if not errors and row.status != "needs_correction":
            continue
        fields = payload.get("fields") or {}
        writer.writerow([
            payload.get("row_number"),
            fields.get("actor_name"),
            payload.get("action"),
            payload.get("row_status"),
            "; ".join(errors or ["Correction required before submission."]),
        ])
    return output.getvalue()
