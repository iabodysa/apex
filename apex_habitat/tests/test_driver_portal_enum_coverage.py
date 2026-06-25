"""Guard: the driver-portal enum translation maps must cover their live source values.

The driver portal localizes server enum values (Dispatch Trip / Issue statuses and the
seeded Issue Type / Issue Priority masters) for Arabic mode through a hand-maintained
``enums`` map in ``driver_portal/src/i18n.js`` (consumed via ``translateEnum`` / ``te``).
``translateEnum`` falls back to the raw English value when a key is missing — so a new or
renamed option silently renders ENGLISH inside the Arabic UI (the owner's recurring
"language changes in places" class) with nothing to catch the drift.

This test reads each enum namespace's Arabic keys out of i18n.js and asserts that every
live source value of the field/master it localizes has a key — failing the build the
moment an option is added/renamed without updating the map. Mirrors the worker-portal
coverage guard (test_worker_portal_enum_coverage).
"""

import re

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.apex_core.setup.seeders.salis_issue_seed import (
    _ISSUE_PRIORITIES,
    _ISSUE_TYPES,
)

APP = frappe.get_app_path("apex_habitat")
I18N = f"{APP}/driver_portal/src/i18n.js"

# i18n.js enum namespace -> the live source of its option values. A Select field is
# ("doctype", "field"); a seeded master set is a plain list of stable English values.
ENUM_SOURCES = {
    "tripStatus": ("Dispatch Trip", "status"),
    "issueStatus": ("Issue", "status"),
    "issueCategory": _ISSUE_TYPES,
    "issuePriority": _ISSUE_PRIORITIES,
    "fuelStatus": ("Fuel Request", "status"),
}


def _ar_block(js):
    """Return the body of the ``ar: { ... }`` object inside the ``enums`` map by
    brace-matching (the block is nested, so a non-greedy ``[^}]`` slice won't do)."""
    anchor = re.search(r"const enums\s*=\s*\{", js)
    assert anchor, "enums map not found in i18n.js"
    ar = re.search(r"\bar\s*:\s*\{", js[anchor.end():])
    assert ar, "enums.ar block not found in i18n.js"
    start = anchor.end() + ar.end() - 1  # index of the opening brace of enums.ar
    depth = 0
    for i in range(start, len(js)):
        if js[i] == "{":
            depth += 1
        elif js[i] == "}":
            depth -= 1
            if depth == 0:
                return js[start + 1 : i]
    raise AssertionError("unbalanced braces in enums.ar block")


def _namespace_keys(ar_block, namespace):
    """The set of option keys defined under ``<namespace>: { ... }`` in enums.ar, or
    None if the namespace is absent. Keys are quoted ("On Hold") or bareword (Open)."""
    m = re.search(re.escape(namespace) + r"\s*:\s*\{([^}]*)\}", ar_block)
    if not m:
        return None
    keys = set()
    for line in m.group(1).splitlines():
        km = re.match(r'\s*(?:"([^"]+)"|([A-Za-z][\w ]*?))\s*:', line)
        if km:
            keys.add((km.group(1) or km.group(2)).strip())
    return keys


def _source_values(source):
    """Live option values for an ENUM_SOURCES entry: Select options for a
    (doctype, field) pair, or the seeded list itself for a master set."""
    if isinstance(source, (list, tuple)) and len(source) == 2 and isinstance(source[1], str):
        meta_field = frappe.get_meta(source[0]).get_field(source[1])
        assert meta_field is not None, f"{source[0]}.{source[1]} field missing"
        return [o.strip() for o in (meta_field.options or "").split("\n") if o.strip()]
    return list(source)


class TestDriverPortalEnumCoverage(FrappeTestCase):
    def test_enum_maps_cover_live_options(self):
        with open(I18N, encoding="utf-8") as fh:
            js = fh.read()
        ar = _ar_block(js)
        missing = []
        for ns, source in ENUM_SOURCES.items():
            keys = _namespace_keys(ar, ns)
            self.assertIsNotNone(keys, f"enum namespace '{ns}' not found in enums.ar")
            for opt in _source_values(source):
                if opt not in keys:
                    missing.append(f"{ns}: '{opt}'")
        self.assertEqual(
            sorted(missing),
            [],
            "driver-portal enum option(s) with no Arabic entry "
            f"(would render English in Arabic mode): {sorted(missing)}",
        )
