# Copyright (c) 2026, AFMCO and contributors
"""RETIRED — Habitat Dashboards now ship as native is_standard=1 module JSON.

The Habitat operations dashboard and the four role dashboards (Accommodation
Manager, Resident Supervisor, Finance Manager, Internal Auditor) are now shipped
as standard Dashboard records under

    habitat/habitat_dashboard/<slug>/<slug>.json   (is_standard=1, module=Habitat)

which Frappe's ``sync_dashboards()`` imports automatically on install + migrate —
exactly like ERPNext ships its module dashboards. The runtime seeders that used to
hand-build these Dashboards as is_standard=0 records were the source of the deep-
audit findings (native-first violation + double-provisioning) and are retired.

The public entrypoints below are kept as NO-OP stubs because they are still
imported by ``apex/setup.py`` (after_install) and by the legacy
``patches/v0_9/seed_habitat_dashboard.py`` / ``seed_role_dashboards.py`` patches.
Keeping the names importable avoids an ImportError on those call sites while the
actual provisioning is owned entirely by the shipped JSON. A run-once patch
deleted the old is_standard=0 Dashboard rows on upgrading sites so migrate
re-imported them from the new JSON as is_standard=1; that patch has since been
pruned as spent.

Do not re-add record-building logic here: an is_standard Dashboard must be edited
through its JSON, and Dashboard.validate forbids an is_standard Dashboard from
referencing a non-standard chart/card.
"""


def seed_habitat_dashboard(*args, **kwargs):
    """No-op. Habitat Dashboard now ships as is_standard JSON (see module docstring)."""


def seed_role_dashboards(*args, **kwargs):
    """No-op. Role dashboards now ship as is_standard JSON (see module docstring)."""


def seed_all_dashboards(*args, **kwargs):
    """No-op after_migrate/after_install entrypoint (retired — see module docstring)."""
