# Copyright (c) 2026, AFMCO and contributors
import frappe


def execute():
	"""Rename the worker-transport Workspace from 'Movement' to 'Masar'.

	The workspace was named 'Movement' but labelled 'Masar', so its desk route was
	/app/movement while everyone refers to it as Masar — navigating to /app/masar
	returned a 404 (owner-reported). The workspace is now shipped as name 'Masar'
	(route /app/masar); this patch carries existing sites across.

	Idempotent and order-safe: a fresh install only has 'Masar' (no-op); on an
	already-migrated site neither name needs touching; if the JSON sync already
	created 'Masar' alongside the stale 'Movement', the stale one is dropped,
	otherwise 'Movement' is renamed in place.
	"""
	if not frappe.db.exists("Workspace", "Movement"):
		return
	if frappe.db.exists("Workspace", "Masar"):
		frappe.delete_doc("Workspace", "Movement", ignore_permissions=True, force=True)
	else:
		frappe.rename_doc("Workspace", "Movement", "Masar", force=True, ignore_permissions=True)
	frappe.clear_cache()
