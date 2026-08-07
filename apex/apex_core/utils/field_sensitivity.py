# Copyright (c) 2026, afmcoltd
"""THE FIELD SENSITIVITY MODEL. Read this before you set a `permlevel`."""

import re

LEVEL_OPERATIONAL = 0
LEVEL_PERSONAL = 1

DISPLAY_FIELDTYPES = frozenset(
    {"Section Break", "Column Break", "Tab Break", "HTML", "Heading", "Fold", "Button", "Image"}
)
TEXT_FIELDTYPES = frozenset({"Data", "Small Text", "Text", "Long Text", "Text Editor"})
FREETEXT_FIELDTYPES = frozenset({"Small Text", "Text", "Long Text", "Text Editor"})

GOVERNMENT_ID = re.compile(
    r"national_id|iqama|passport_no|passport_number|civil_id|residency_no|border_no"
)
PERSONAL_CONTACT = re.compile(r"mobile|phone|whatsapp|personal_email|contact_number")
PER_PERSON_PAY = re.compile(r"salary|wage|basic_pay|gross_pay|net_pay|stipend|deduction_amount")
FREE_TEXT = re.compile(r"notes|remarks|comment|description|reason")

PERSON_NAME = re.compile(r"^(full_name|worker_name|resident_name|driver_name|holder_name)$")

CATEGORIES = ("signature", "government_id", "personal_contact", "per_person_pay", "free_text")


def is_person_master(doctype_json):
    """True when the record's OWN subject is a natural person.

    The test is a self-owned personal name or government ID. A ``fetch_from`` field is
    skipped: it displays a value belonging to a linked record, so it says the document
    REFERENCES a person, not that it is ABOUT one.
    """
    for field in doctype_json.get("fields") or []:
        if field.get("fetch_from"):
            continue
        fieldname = field.get("fieldname") or ""
        fieldtype = field.get("fieldtype") or ""
        if fieldtype in TEXT_FIELDTYPES and GOVERNMENT_ID.search(fieldname):
            return True
        if fieldtype == "Data" and PERSON_NAME.match(fieldname):
            return True
    return False


def categorise(field, *, person_master):
    """The sensitivity category of one DocField, or None when it is operational.

    ``person_master`` gates the three contextual categories; the two absolute ones ignore
    it. Order matters only in that the absolute categories are tried first.

    """
    fieldname = field.get("fieldname") or ""
    fieldtype = field.get("fieldtype") or ""

    if fieldtype in DISPLAY_FIELDTYPES:
        return None
    if fieldtype == "Signature":
        return "signature"
    if fieldtype in TEXT_FIELDTYPES and GOVERNMENT_ID.search(fieldname):
        return "government_id"
    if not person_master:
        return None
    if fieldtype == "Data" and PERSONAL_CONTACT.search(fieldname):
        return "personal_contact"
    if fieldtype == "Currency" and PER_PERSON_PAY.search(fieldname):
        return "per_person_pay"
    if fieldtype in FREETEXT_FIELDTYPES and FREE_TEXT.search(fieldname):
        return "free_text"
    return None


def sensitive_fields(doctype_json):
    """(fieldname, category, permlevel) for every field the model calls sensitive."""
    person_master = is_person_master(doctype_json)
    out = []
    for field in doctype_json.get("fields") or []:
        category = categorise(field, person_master=person_master)
        if category:
            out.append(
                (field.get("fieldname") or "", category, int(field.get("permlevel") or 0))
            )
    return out


def offenders(doctypes):
    """{doctype: [(fieldname, category)]} for sensitive fields still at level 0.

    ``doctypes`` is the mapping ``apex.tests.shipped_doctypes.shipped_doctypes`` returns.
    """
    found = {}
    for name, data in doctypes.items():
        at_zero = [
            (fieldname, category)
            for fieldname, category, permlevel in sensitive_fields(data)
            if permlevel == LEVEL_OPERATIONAL
        ]
        if at_zero:
            found[name] = sorted(at_zero)
    return found
