"""Salis module install-time bootstrap.

Wired into the app's ``after_install`` hook (as a list alongside the Habitat
bootstrap). This is the canonical first-install path for Salis default records:
roles, authority/operations approval roles, and Salis Settings defaults.

The seed logic lives in the idempotent, existence-guarded ``patches/v1_0/seed_*``
modules (single source of truth). after_install reuses them so a fresh install
gets the defaults immediately, while the same patches in ``patches.txt`` keep
already-installed sites in sync on migrate. Every seed is existence-guarded and
skip-missing, so running them twice (install + migrate) is safe.
"""

import frappe

from apex_habitat.patches.v1_0 import (
	seed_salis_roles,
	seed_salis_authority_roles,
	seed_salis_operations_roles,
	seed_salis_settings,
)


def after_install():
	"""Seed Salis roles + settings on first install (idempotent)."""
	for step in (
		seed_salis_roles.execute,
		seed_salis_authority_roles.execute,
		seed_salis_operations_roles.execute,
		seed_salis_settings.execute,
	):
		try:
			step()
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Salis after_install seed failed")
