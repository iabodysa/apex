# Copyright (c) 2026, AFMCO and contributors
"""Seed City with the main Saudi Arabian cities.

The city list now lives as a data-driven seed file
(``apex_core/setup/data/habitat/city.json``) applied by ``seed.seed_all``, which is
wired into BOTH ``after_install`` and ``after_migrate`` — so fresh installs (which mark
patches complete without running them) get the cities too. This patch delegates to the
same create-only loader so already-migrated sites seed identically. Safe to prune once
every deployed site has run the after_migrate seed path.
"""

import frappe


def execute():
    if not frappe.db.exists("DocType", "City"):
        return

    from apex_habitat.apex_core.setup.seed import seed

    seed("habitat", only=["City"])
    frappe.db.commit()
