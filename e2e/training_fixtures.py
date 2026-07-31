"""Idempotent SYNTHETIC housing fixtures for the training screenshots.

WHY THIS FILE EXISTS AT ALL: a screenshot publishes every pixel on screen. Point
a capture at a site holding real rows and it publishes resident names, employee
ids, phone numbers and building addresses into a public repository, where a later
`git rm` does not take them back. So the capture never reads live data — it reads
this, a fixed set of rows whose every visible value is invented here and prefixed
`Training`, which makes "is anything real in this image" answerable by looking at
the image instead of by trusting the operator who took it.

DETERMINISM: every name and value below is a constant, never a timestamp, a
sequence, a random suffix or today's date, because a re-capture has to produce
the same bytes for a diff to mean anything. The one date is fixed at 2030-01-15 —
far enough ahead that no lease-expiry or aging job re-colours the row, and
identical on every run.

SAFETY: refuses to write unless the connected site is the one SITE_NAME names.
Run through bench console as ONE compiled unit (bench console feeds stdin
cell-by-cell and breaks indented blocks):

    set -a; . <apex>/e2e/.env.local; set +a
    p='<apex>/e2e/training_fixtures.py'
    echo "exec(compile(open('$p').read(),'$p','exec'),{'__name__':'setup'})" \
        | bench --site "$SITE_NAME" console
"""
import os

import frappe

# One prefix on every row, so a reviewer can grep an image's OCR for it, and so a
# stray fixture on a bench is identifiable as this file's rather than a real record.
PREFIX = "Training"

_declared_site = os.environ.get("SITE_NAME")
if not _declared_site:
    raise SystemExit("SITE_NAME not set — source e2e/.env.local first")
if frappe.local.site != _declared_site:
    raise SystemExit(
        f"refusing to seed: connected to {frappe.local.site!r}, "
        f"SITE_NAME declares {_declared_site!r}"
    )


def _upsert(doctype, name, values):
    """Create ``name`` if absent, otherwise force it back to ``values``.

    Force, not skip: a fixture left half-edited by a previous session renders a
    different screenshot, and the whole point of re-running this is that the next
    capture starts from the state described here rather than from the last one.
    """
    if frappe.db.exists(doctype, name):
        doc = frappe.get_doc(doctype, name)
        doc.update(values)
        doc.save(ignore_permissions=True)
        return doc, "updated"
    doc = frappe.get_doc({"doctype": doctype, **values})
    doc.insert(ignore_permissions=True)
    return doc, "created"


_report = []


def _step(doctype, name, values):
    doc, action = _upsert(doctype, name, values)
    _report.append(f"{action:8s} {doctype}: {doc.name}")
    return doc


_site = _step("Site", f"{PREFIX} Site S01", {"site_name": f"{PREFIX} Site S01"})

_building = _step(
    "Building",
    f"{PREFIX} Building B01",
    {"building_name": f"{PREFIX} Building B01", "site": _site.name},
)

_room = _step(
    "Room",
    f"{PREFIX} Room R01",
    {"room_number": f"{PREFIX} Room R01", "building": _building.name},
)

# Two beds, both Available: the assignment screenshot is of the Bed link dropdown,
# and one row would not show that the list is filtered rather than empty.
for _code in ("B01", "B02"):
    _step(
        "Bed",
        f"{PREFIX} Bed {_code}",
        {"bed_code": f"{PREFIX} Bed {_code}", "room": _room.name, "status": "Available"},
    )

frappe.db.commit()

print(f"site: {frappe.local.site}")
for _line in _report:
    print(_line)
