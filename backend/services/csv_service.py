"""CSV parsing and validation for client uploads."""

import csv
import io
import uuid
from typing import Optional

from config import MAX_CSV_ROWS, KNOWN_INSURERS

# Map flexible header names to canonical field names
_HEADER_MAP = {
    "name": "name",
    "client name": "name",
    "full name": "name",
    "email": "email",
    "email address": "email",
    "phone": "phone",
    "phone number": "phone",
    "mobile": "phone",
    "whatsapp": "whatsapp",
    "wa": "whatsapp",
    "whatsapp number": "whatsapp",
    "insurer": "insurer",
    "insurance company": "insurer",
    "company": "insurer",
    "policy type": "policy_type",
    "policy_type": "policy_type",
    "type": "policy_type",
    "product type": "policy_type",
    "policy number": "policy_number",
    "policy_number": "policy_number",
    "policy no": "policy_number",
    "policy no.": "policy_number",
    "plan name": "plan_name",
    "plan_name": "plan_name",
    "plan": "plan_name",
    "product name": "plan_name",
    "remarks": "remarks",
    "notes": "remarks",
    "comment": "remarks",
    "comments": "remarks",
}

REQUIRED_FIELDS = {"name", "insurer", "policy_type", "policy_number"}


def parse_csv(content: str) -> dict:
    """Parse CSV content and return {"clients": [...], "errors": [...], "warnings": [...]}."""
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        return {"clients": [], "errors": ["CSV has no headers."], "warnings": []}

    # Map headers
    header_mapping = {}
    for raw_header in reader.fieldnames:
        canonical = _HEADER_MAP.get(raw_header.strip().lower())
        if canonical:
            header_mapping[raw_header] = canonical

    mapped_fields = set(header_mapping.values())
    missing = REQUIRED_FIELDS - mapped_fields
    if missing:
        return {
            "clients": [],
            "errors": [f"Missing required columns: {', '.join(sorted(missing))}"],
            "warnings": [],
        }

    clients = []
    errors = []
    warnings = []
    insurer_lower = {i.lower(): i for i in KNOWN_INSURERS}

    for row_num, row in enumerate(reader, start=2):
        if row_num - 1 > MAX_CSV_ROWS:
            errors.append(f"CSV exceeds maximum of {MAX_CSV_ROWS} rows.")
            break

        mapped = {}
        for raw_key, canonical_key in header_mapping.items():
            mapped[canonical_key] = (row.get(raw_key) or "").strip()

        # Validate required fields
        row_errors = []
        if not mapped.get("name"):
            row_errors.append("missing name")
        if not mapped.get("insurer"):
            row_errors.append("missing insurer")
        if not mapped.get("policy_type"):
            row_errors.append("missing policy type")
        if not mapped.get("policy_number"):
            row_errors.append("missing policy number")

        if row_errors:
            errors.append(f"Row {row_num}: {', '.join(row_errors)}")
            continue

        # Check at least one contact method
        has_contact = any(mapped.get(f) for f in ("email", "phone", "whatsapp"))
        if not has_contact:
            warnings.append(f"Row {row_num} ({mapped['name']}): no contact info (email/phone/whatsapp)")

        # Normalise insurer name
        insurer_norm = insurer_lower.get(mapped["insurer"].lower())
        if insurer_norm:
            mapped["insurer"] = insurer_norm
        else:
            warnings.append(f"Row {row_num}: unknown insurer '{mapped['insurer']}' (will still be included)")

        clients.append({
            "id": str(uuid.uuid4()),
            "name": mapped["name"],
            "email": mapped.get("email", ""),
            "phone": mapped.get("phone", ""),
            "whatsapp": mapped.get("whatsapp", ""),
            "insurer": mapped["insurer"],
            "policy_type": mapped["policy_type"],
            "policy_number": mapped["policy_number"],
            "plan_name": mapped.get("plan_name", ""),
            "remarks": mapped.get("remarks", ""),
        })

    return {"clients": clients, "errors": errors, "warnings": warnings}
