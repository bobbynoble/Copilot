"""
HL7 v2 to FHIR R4 mapper.

Handles common message types (ADT, ORU, ORM) and maps each segment to the
appropriate FHIR R4 resource.

Z-segments (custom/local segments whose names start with 'Z') are a known v2
issue: they are non-standard, have no defined FHIR mapping, and many conversion
pipelines silently drop them. This module instead preserves each Z-segment as a
FHIR Basic resource carrying the raw segment text in a named extension, so
downstream consumers can audit or process the custom data rather than losing it.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import hl7

logger = logging.getLogger(__name__)

Z_SEGMENT_EXT_URL = (
    "http://hl7.org/fhir/StructureDefinition/v2-z-segment"
)


# ── Low-level field helpers ───────────────────────────────────────────────────

def _field(seg: hl7.Segment, idx: int) -> str:
    """Return segment field as a stripped string; empty string if absent."""
    try:
        return str(seg[idx]).strip()
    except IndexError:
        return ""


def _component(seg: hl7.Segment, field_idx: int, comp_idx: int) -> str:
    """Return a specific component (1-based) from a field, splitting on '^'."""
    parts = _field(seg, field_idx).split("^")
    return parts[comp_idx - 1].strip() if comp_idx <= len(parts) else ""


def _new_id() -> str:
    return str(uuid.uuid4())


def _ts_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_hl7_datetime(raw: str) -> str | None:
    """Convert HL7 datetime (YYYYMMDDHHMMSS) to ISO-8601; returns None if unparseable."""
    raw = raw.strip()
    if len(raw) >= 8:
        date = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
        if len(raw) >= 14:
            return f"{date}T{raw[8:10]}:{raw[10:12]}:{raw[12:14]}"
        return date
    return None


# ── Segment mappers ───────────────────────────────────────────────────────────

def _map_msh(seg: hl7.Segment) -> dict[str, Any]:
    """MSH → MessageHeader"""
    event = _field(seg, 9)  # e.g. "ADT^A01"
    event_code = event.split("^")[0] if event else ""

    resource: dict[str, Any] = {
        "resourceType": "MessageHeader",
        "id": _new_id(),
        "eventCoding": {
            "system": "http://terminology.hl7.org/CodeSystem/v2-0003",
            "code": event_code,
            "display": event,
        },
        "source": {
            "name": _field(seg, 3),
            "endpoint": _field(seg, 3) or "unknown",
        },
        "meta": {"lastUpdated": _ts_now()},
    }

    dest = _field(seg, 5)
    if dest:
        resource["destination"] = [{"name": dest}]

    return resource


_GENDER_MAP = {"M": "male", "F": "female", "O": "other", "U": "unknown"}


def _map_pid(seg: hl7.Segment) -> dict[str, Any]:
    """PID → Patient"""
    resource: dict[str, Any] = {
        "resourceType": "Patient",
        "id": _new_id(),
    }

    # PID-3: patient identifier list
    patient_id = _component(seg, 3, 1) or _field(seg, 3)
    if patient_id:
        resource["identifier"] = [{"value": patient_id}]

    # PID-5: name (family^given^middle)
    name: dict[str, Any] = {}
    family = _component(seg, 5, 1)
    given = _component(seg, 5, 2)
    if family:
        name["family"] = family
    if given:
        name["given"] = [given]
    if name:
        resource["name"] = [name]

    # PID-7: date of birth
    dob = _parse_hl7_datetime(_field(seg, 7))
    if dob:
        resource["birthDate"] = dob[:10]  # date only

    # PID-8: gender
    gender_code = _field(seg, 8).upper()
    resource["gender"] = _GENDER_MAP.get(gender_code, "unknown")

    # PID-11: address
    street = _component(seg, 11, 1)
    city = _component(seg, 11, 3)
    state = _component(seg, 11, 4)
    postal = _component(seg, 11, 5)
    if any([street, city, state, postal]):
        address: dict[str, Any] = {"use": "home"}
        if street:
            address["line"] = [street]
        if city:
            address["city"] = city
        if state:
            address["state"] = state
        if postal:
            address["postalCode"] = postal
        resource["address"] = [address]

    return resource


_ENCOUNTER_CLASS_MAP = {
    "I": "IMP",    # inpatient
    "O": "AMB",    # outpatient
    "E": "EMER",   # emergency
    "P": "PRENC",  # pre-admission
    "R": "AMB",    # recurring
    "B": "AMB",    # obstetrics
    "C": "AMB",    # commercial
    "N": "AMB",    # not applicable
    "U": "AMB",    # unknown
}


def _map_pv1(seg: hl7.Segment) -> dict[str, Any]:
    """PV1 → Encounter"""
    patient_class = _field(seg, 2).upper()
    class_code = _encounter_class_map_get(patient_class)

    resource: dict[str, Any] = {
        "resourceType": "Encounter",
        "id": _new_id(),
        "status": "finished",
        "class": {
            "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
            "code": class_code,
        },
    }

    admit_dt = _parse_hl7_datetime(_field(seg, 44))
    discharge_dt = _parse_hl7_datetime(_field(seg, 45))
    if admit_dt or discharge_dt:
        period: dict[str, str] = {}
        if admit_dt:
            period["start"] = admit_dt
        if discharge_dt:
            period["end"] = discharge_dt
        resource["period"] = period

    return resource


def _encounter_class_map_get(code: str) -> str:
    return _ENCOUNTER_CLASS_MAP.get(code, "AMB")


_OBX_STATUS_MAP = {
    "F": "final",
    "P": "preliminary",
    "C": "corrected",
    "X": "cancelled",
    "R": "registered",
    "I": "registered",
    "S": "partial",
    "U": "unknown",
}


def _map_obx(seg: hl7.Segment) -> dict[str, Any]:
    """OBX → Observation"""
    obs_status = _OBX_STATUS_MAP.get(_field(seg, 11).upper(), "unknown")

    # OBX-3: observation identifier (code^display^system)
    code = _component(seg, 3, 1)
    display = _component(seg, 3, 2)
    coding_system = _component(seg, 3, 3) or "http://loinc.org"
    # Normalise common coding system names to canonical URIs
    if coding_system.upper() in ("LN", "LOINC"):
        coding_system = "http://loinc.org"

    resource: dict[str, Any] = {
        "resourceType": "Observation",
        "id": _new_id(),
        "status": obs_status,
        "code": {
            "coding": [{"system": coding_system, "code": code, "display": display}],
            "text": display or code,
        },
    }

    # OBX-5: observation value
    value_raw = _field(seg, 5)
    # OBX-6: units (code^display)
    units_code = _component(seg, 6, 1)
    units_display = _component(seg, 6, 2) or units_code

    if value_raw:
        try:
            resource["valueQuantity"] = {
                "value": float(value_raw),
                "unit": units_display,
                "system": "http://unitsofmeasure.org",
                "code": units_code,
            }
        except ValueError:
            resource["valueString"] = value_raw

    # OBX-14: date/time of observation
    obs_dt = _parse_hl7_datetime(_field(seg, 14))
    if obs_dt:
        resource["effectiveDateTime"] = obs_dt

    return resource


def _map_obr(seg: hl7.Segment) -> dict[str, Any]:
    """OBR → DiagnosticReport"""
    code = _component(seg, 4, 1)
    display = _component(seg, 4, 2)

    resource: dict[str, Any] = {
        "resourceType": "DiagnosticReport",
        "id": _new_id(),
        "status": "final",
        "code": {
            "coding": [{"system": "http://loinc.org", "code": code, "display": display}],
            "text": display or code,
        },
    }

    # OBR-7: observation datetime
    obs_dt = _parse_hl7_datetime(_field(seg, 7))
    if obs_dt:
        resource["effectiveDateTime"] = obs_dt

    # OBR-22: results report datetime
    report_dt = _parse_hl7_datetime(_field(seg, 22))
    if report_dt:
        resource["issued"] = report_dt

    return resource


def _map_nte(seg: hl7.Segment) -> dict[str, Any]:
    """NTE → Basic resource carrying the note text as an Annotation extension."""
    return {
        "resourceType": "Basic",
        "id": _new_id(),
        "code": {
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/v2-0076",
                "code": "NTE",
                "display": "Notes and Comments",
            }]
        },
        "extension": [{
            "url": "http://hl7.org/fhir/StructureDefinition/v2-nte-comment",
            "valueString": _field(seg, 3),
        }],
    }


def _map_z_segment(seg: hl7.Segment) -> dict[str, Any]:
    """
    Z-segment → Basic resource with raw-segment extension.

    Z-segments are local/custom segments not in the HL7 v2 standard.
    Rather than silently discarding them (a common source of data loss),
    we preserve the raw text as a FHIR extension on a Basic resource so
    downstream consumers can inspect or re-process the custom content.
    """
    seg_name = _field(seg, 0)
    raw_text = str(seg)

    logger.warning(
        "Non-standard Z-segment encountered: %s — preserved as Basic resource with extension",
        seg_name,
    )

    return {
        "resourceType": "Basic",
        "id": _new_id(),
        "code": {
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/v2-0076",
                "code": seg_name,
                "display": f"Custom Z-segment: {seg_name}",
            }]
        },
        "extension": [{
            "url": Z_SEGMENT_EXT_URL,
            "valueString": raw_text,
        }],
    }


_SEGMENT_MAPPERS: dict[str, Any] = {
    "MSH": _map_msh,
    "PID": _map_pid,
    "PV1": _map_pv1,
    "OBX": _map_obx,
    "OBR": _map_obr,
    "NTE": _map_nte,
}


# ── Public API ────────────────────────────────────────────────────────────────

def parse_hl7v2(raw: str) -> hl7.Message:
    """
    Parse a raw HL7 v2 message string.

    python-hl7 treats unknown segment names (including Z-segments) as generic
    Segment objects — no pre-processing or exception suppression required.
    Line endings are normalised first: HL7 v2 uses bare CR as the segment
    terminator, but messages often arrive with CRLF or LF line endings.
    """
    normalised = raw.replace("\r\n", "\r").replace("\n", "\r")
    return hl7.parse(normalised)


def map_to_fhir_bundle(msg: hl7.Message) -> tuple[dict[str, Any], list[str]]:
    """
    Convert a parsed HL7 v2 Message to a FHIR R4 Bundle (type=message).

    Returns:
        bundle       — the FHIR R4 Bundle dict
        z_seg_names  — names of any Z-segments that were encountered
    """
    entries: list[dict] = []
    z_seg_names: list[str] = []
    skipped: list[str] = []

    for segment in msg:
        seg_type = _field(segment, 0)
        if not seg_type:
            continue

        if seg_type in _SEGMENT_MAPPERS:
            resource = _SEGMENT_MAPPERS[seg_type](segment)
            entries.append({
                "fullUrl": f"urn:uuid:{resource['id']}",
                "resource": resource,
            })
        elif seg_type.startswith("Z"):
            z_seg_names.append(seg_type)
            resource = _map_z_segment(segment)
            entries.append({
                "fullUrl": f"urn:uuid:{resource['id']}",
                "resource": resource,
            })
        else:
            skipped.append(seg_type)

    if skipped:
        logger.debug("Skipped unmapped segment types: %s", ", ".join(sorted(set(skipped))))

    bundle: dict[str, Any] = {
        "resourceType": "Bundle",
        "id": _new_id(),
        "type": "message",
        "timestamp": _ts_now(),
        "meta": {
            "tag": [{
                "system": "http://terminology.hl7.org/CodeSystem/v2-0076",
                "code": "v2-converted",
                "display": "Converted from HL7 v2",
            }]
        },
        "entry": entries,
    }

    return bundle, z_seg_names


def convert(raw_message: str) -> tuple[dict[str, Any], list[str]]:
    """
    Parse a raw HL7 v2 string and return a FHIR R4 Bundle plus any Z-segment names found.

    Raises:
        hl7.ParseException  — if the message is structurally invalid HL7 v2.
    """
    msg = parse_hl7v2(raw_message)
    return map_to_fhir_bundle(msg)
