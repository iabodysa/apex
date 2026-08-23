# Copyright (c) 2026, afmcoltd
"""Give an upgraded site the Module Def rows a fresh install would have.

``add_module_defs`` (frappe/installer.py:686) has exactly one call site — ``install_app``
at :316 — and appears nowhere in ``migrate.py``. So the rows are created when an app is
INSTALLED and never afterwards: a site that installed Apex before a module shipped never
receives that module's Module Def, and nothing reports the gap.

What a missing Module Def costs: the module does not appear in the module list a
Workspace, a Role Profile or a Module Profile selects from, so a workspace pointing at it
is unreachable and a profile cannot grant it.

``ignore_if_duplicate`` is what makes this safe to re-run — the framework's own flag for
exactly this insert, so a site that already holds every row does nothing and reports
nothing.

CONTRACT: this reads ``apex/modules.txt`` rather than a list written here, so a module
added to the app is covered on the day it ships without this file changing.
"""

import frappe
from frappe.installer import add_module_defs


def execute():
    """Insert every Apex Module Def the site is missing."""
    add_module_defs("apex", ignore_if_duplicate=True)
    frappe.clear_cache()
