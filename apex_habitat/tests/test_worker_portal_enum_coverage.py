"""Guard: the worker-portal enum translation maps must cover the live Select options.

The worker portal localizes server enum values (DocType Select options) for Arabic
mode through hand-maintained maps in ``worker_portal/src/i18n.js`` (``enums.ar`` +
``translateEnum``). ``translateEnum`` falls back to the raw English value when a key
is missing — so a new or renamed Select option silently renders ENGLISH inside the
Arabic UI (the owner's recurring "language changes in places" class), with nothing
to catch the drift (T-125 / T-158).

This test reads each enum namespace's keys out of i18n.js and asserts that every
live option of the DocType Select field it localizes has a key — failing the build
the moment an option is added/renamed without updating the map. (The durable fix is
to server-drive the label; until then this locks the map. See T-159.)

ENUM_SOURCES was verified against the live options on 2026-06-17; all seven
namespaces fully covered their fields then.
"""

import re

import frappe
from frappe.tests.utils import FrappeTestCase

APP = frappe.get_app_path("apex_habitat")
I18N = f"{APP}/worker_portal/src/i18n.js"

# i18n.js enum namespace -> (DocType, Select fieldname) it localizes.
ENUM_SOURCES = {
    "status": ("Employee", "status"),
    "stayType": ("Accommodation Assignment", "stay_type"),
    "requestType": ("Transport Request", "request_type"),
    "transportStatus": ("Transport Request", "status"),
    "requestCategory": ("Accommodation Resident Request", "request_category"),
    "requestStatus": ("Accommodation Resident Request", "status"),
    "priority": ("Accommodation Resident Request", "priority"),
}


def _map_keys(js, namespace):
    """Return the set of keys defined under ``<namespace>: { ... }`` in i18n.js,
    or None if the namespace block is absent. Keys are quoted ("Pest Control") or
    bareword (Active); the enum values never contain ``}`` so a non-nested match
    is exact."""
    m = re.search(r"(?<![A-Za-z])" + re.escape(namespace) + r"\s*:\s*\{([^}]*)\}", js)
    if not m:
        return None
    keys = set()
    for line in m.group(1).splitlines():
        km = re.match(r'\s*(?:"([^"]+)"|([A-Za-z]\w*))\s*:', line)
        if km:
            keys.add(km.group(1) or km.group(2))
    return keys


class TestWorkerPortalEnumCoverage(FrappeTestCase):
    def test_enum_maps_cover_live_options(self):
        with open(I18N, encoding="utf-8") as fh:
            js = fh.read()
        missing = []
        for ns, (dt, field) in ENUM_SOURCES.items():
            keys = _map_keys(js, ns)
            self.assertIsNotNone(keys, f"enum namespace '{ns}' not found in i18n.js")
            meta_field = frappe.get_meta(dt).get_field(field)
            self.assertIsNotNone(
                meta_field, f"{dt}.{field} missing (declared enum source for '{ns}')"
            )
            options = [o.strip() for o in (meta_field.options or "").split("\n") if o.strip()]
            for opt in options:
                if opt not in keys:
                    missing.append(f"{ns} ({dt}.{field}): '{opt}'")
        self.assertEqual(
            sorted(missing),
            [],
            "worker-portal Select options with no Arabic enum entry "
            f"(would render English in Arabic mode): {sorted(missing)}",
        )
