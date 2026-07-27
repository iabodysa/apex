# Copyright (c) 2026, AFMCO and contributors
"""A-303 — THE FIELD SENSITIVITY MODEL. Read this before you set a `permlevel`.

WHY THIS FILE EXISTS
--------------------
Frappe already ships per-field sensitivity: every DocField carries a ``permlevel``, and a
DocPerm row is written per level, so a role reads a level only if it holds a row AT that
level. We were not using it. Measured across the shipped tree (the numbers are reproduced
by ``test_field_sensitivity.TestTheModelMatchesTheShippedTree``):

    153 shipped DocTypes
     19 have at least one field above level 0
     16 have at least one DocPerm row above level 0
    134 are entirely level 0

On those 134, any role that can read the record reads EVERY field on it. Three separate
access decisions in one week each had to re-derive "is this field sensitive?" from scratch,
because the answer lived in nobody's head and no file. This is that file.

It is a MODEL, not a list. The categories below decide by KIND of data, so a field that
does not exist yet is already classified the moment someone names it.

THE LEVELS
----------
LEVEL 0 - OPERATIONAL. The default, and where most fields belong.
    Facts about the WORK: where a thing is, what state it is in, when it happened, which
    building / room / vehicle / project / trip it belongs to, quantities, dates, statuses,
    and links between operational records.
    RULE: if the record exists so that two people can coordinate work, the fields that
    describe that work are level 0. Withholding them breaks the coordination the record is
    FOR. Do not raise a field just because it feels important - importance is not
    sensitivity.

LEVEL 1 - PERSONAL OR FINANCIAL. Everything the five categories below name.
    RULE: the field identifies a natural person, values a natural person, or is unbounded
    prose ABOUT a natural person. Exposure harms a PERSON, not an operation.

LEVEL 2 - DOES NOT EXIST, DELIBERATELY.
    A third level is only worth its DocPerm rows when some role must read one of the two
    level-1 kinds and NOT the other - finance sees pay but not the national ID, say. Today
    no role wants that split: on Freelancer, the one DocType carrying both, Finance Manager
    holds a single level-1 row covering the government ID AND the salary, and that is the
    intended access. Invent level 2 when a role appears that needs one half; until then a
    second level is two more rows per DocType buying nothing.

THE CATEGORIES
--------------
Two are ABSOLUTE - the data is personal wherever it appears, so the rule needs no context:

  1. SIGNATURE   - fieldtype ``Signature``. A captured human mark. Biometric-adjacent, and
                   the raw material for forging an acknowledgement. Never operational.
  2. GOVERNMENT ID - national ID, iqama, passport, civil ID, border number, on a text
                   field. A state identifier for a person; the highest-harm identifier the
                   app stores.

Three are CONTEXTUAL - the same field name is sensitive on a person and mundane on an
asset, so they apply only on a PERSON MASTER (see ``is_person_master``): a record whose own
subject IS a person, because it carries that person's name or government ID as its own
field. A Maintenance Work Order that links to an employee is NOT a person master; the
record is about the work.

  3. PERSONAL CONTACT - mobile, phone, whatsapp, personal email, contact number. Reaching
                   a person outside work. On an asset (a company SIM's own number) the same
                   name is an asset identifier and stays level 0.
  4. PER-PERSON PAY - a Currency amount named salary, wage, basic/gross/net pay, stipend,
                   or a deduction amount. What one named person is paid or costs. A policy
                   ceiling (``global_max_percent_of_salary``) is a rule, not a person's pay,
                   and stays level 0 - which is why this category requires ``Currency`` and
                   a person master, not the word "salary".
  5. FREE-TEXT ABOUT A PERSON - notes, remarks, description, reason, resolution/triage
                   notes on a person master. Unbounded operator prose cannot be classified
                   in advance, and empirically collects grievance, medical and disciplinary
                   detail that no field label predicted.

WHAT THIS MODEL CANNOT DO - read this before trusting a level
-------------------------------------------------------------
A ``permlevel`` is enforced in the DOCUMENT and DESK-VIEW layers only.

  * ENFORCED on the document: loading strips unreadable level fields
    (``frappe/model/document.py:754-781``); saving RESTORES them from the stored record
    instead of blanking them (``frappe/model/base_document.py:1288,1291``), so a role that
    cannot see a level field still cannot destroy it.
  * ENFORCED on the Desk view: the list/report view drops an unreadable level column
    (``frappe/desk/reportview.py:126-128``), and ``frappe.get_list`` drops it too
    (``frappe/model/db_query.py:270`` -> ``:668``).
  * ENFORCED on print: ``is_visible`` hides an unreadable level field from the print
    layout (``frappe/www/printview.py:542-548``). Checked, because a print format looked
    like an obvious hole and is not one.
  * NOT ENFORCED in a Notification: neither ``frappe/email/doctype/notification/
    notification.py`` nor ``frappe/core/doctype/communication/email.py`` mentions
    permlevel, so a notification template that interpolates a level-1 field mails it to
    whoever the recipient rule names. Raising a field does not audit the templates that
    already reference it.
  * NOT ENFORCED under ``frappe.get_all``. That same db_query filter returns early on
    ``ignore_permissions`` (``db_query.py:683-684``), and ``frappe.get_all`` sets exactly
    that flag (``frappe/__init__.py:2050``). So ``get_all`` hands a level-1 column to
    anyone. ``frappe.db.sql`` and ``frappe.qb`` never reach the filter at all.
    THIS IS NOT THEORETICAL: every Script Report in this app reads with ``get_all``. A
    level is NOT a defence against a report - the report's own column list is the only
    thing standing there. When you raise a field, grep the report tree for it.
  * NOT ENFORCED: category 5 is the one the guard below cannot police. Whether a free-text
    field is sensitive depends on what operators type into it, which no static rule reads.
    The guard covers it on person masters only; everywhere else category 5 is a rule for a
    human reviewer, and the guard is silent by design rather than noisy.

So: raising a field to level 1 controls who sees it on the FORM and in the DESK LIST. It
does not control who sees it in a Script Report, and it never controls what a report
already selected.
"""

import re

LEVEL_OPERATIONAL = 0
LEVEL_PERSONAL = 1

# Layout fields hold no value and can never be sensitive. Frappe itself skips them when it
# restores level fields (`display_fieldtypes`, frappe/model/base_document.py:1270).
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

# A person master names its subject with one of these as its OWN field. `employee_name` is
# absent on purpose: it is almost always a `fetch_from` display of a Link to someone the
# record merely references, which would make every operational record a person master.
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
