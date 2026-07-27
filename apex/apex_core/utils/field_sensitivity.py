# Copyright (c) 2026, AFMCO and contributors
"""THE FIELD SENSITIVITY MODEL. Read this before you set a `permlevel`.

Frappe already ships per-field sensitivity via DocField ``permlevel`` plus a per-level
DocPerm row, but the app was not using it. Measured across the shipped tree (reproduced
by ``test_field_sensitivity.TestTheModelMatchesTheShippedTree``): 153 DocTypes, 20 with a
field above level 0, 17 with a DocPerm row above level 0 -- 133 entirely level 0, so any
role that can read one of those records reads EVERY field on it. This model classifies
by KIND of data, so a field that does not exist yet is already classified.
LEVELS -- 0 OPERATIONAL (default): facts about the WORK -- location, state, timing,
links between operational records; withholding these breaks the coordination the record
is FOR, and importance alone is not sensitivity. 1 PERSONAL OR FINANCIAL: the field
identifies, values, or is unbounded prose about a natural person -- harms a PERSON, not
an operation. 2 DOES NOT EXIST, DELIBERATELY: only worth its DocPerm rows once some role
needs one level-1 kind and not the other; today Finance Manager on Freelancer holds one
row covering both the government ID and the salary, so a second level buys nothing yet.
CATEGORIES -- two ABSOLUTE, sensitive wherever they appear: (1) SIGNATURE, fieldtype
``Signature``, biometric-adjacent and the raw material for forgery; (2) GOVERNMENT ID,
national ID/iqama/passport/civil ID/border number on a text field. Three are CONTEXTUAL,
sensitive only on a person master (``is_person_master``: a record whose own subject IS a
person, carrying that person's name or government ID as its OWN field, not merely a Link
to one): (3) PERSONAL CONTACT, mobile/phone/whatsapp/personal email/contact number; (4)
PER-PERSON PAY, a Currency named salary/wage/basic-gross-net pay/stipend/deduction -- a
policy ceiling like ``global_max_percent_of_salary`` is a rule, not a person's pay, and
stays level 0, why this category requires ``Currency`` and not the word "salary"; (5)
FREE-TEXT ABOUT A PERSON, notes/remarks/description/reason/resolution on a person
master -- unbounded prose cannot be classified in advance.
LIMITS -- ``permlevel`` is enforced in the DOCUMENT and DESK-VIEW layers only. ENFORCED
on load (``frappe/model/document.py:754-781``) and on save, which RESTORES the stored
value instead of blanking it (``frappe/model/base_document.py:1288,1291``); on the Desk
list/report column (``frappe/desk/reportview.py:126-128``,
``frappe/model/db_query.py:270`` -> ``:668``); and on print
(``frappe/www/printview.py:542-548``). NOT ENFORCED in a Notification -- neither
``frappe/email/doctype/notification/notification.py`` nor
``frappe/core/doctype/communication/email.py`` checks permlevel, so a template mails a
level-1 field to whoever the recipient rule names. NOT ENFORCED under
``frappe.get_all`` -- ``db_query.py:683-684`` returns early on ``ignore_permissions``,
always set by ``frappe.get_all`` (``frappe/__init__.py:2050``); every Script Report here
reads with ``get_all``, so raising a field is not a defence against a report -- grep the
report tree for it. ``frappe.db.sql``/``frappe.qb`` never reach the filter at all. NOT
ENFORCED for category 5 outside person masters -- sensitivity depends on what an
operator typed, which no static rule reads; that is a human reviewer's call there.
So: raising a field controls the FORM and the DESK LIST, not a Script Report, and never
controls what a report already selected.
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
