# ONE-TIME structural merge — safe to PRUNE once every deployed site has run it.
#
# Merges the two near-duplicate submittable DocTypes "Fuel Topup Request" (FT-)
# and "Fuel Chip Request" (FC-) into the unified "Fuel Request", which now carries
# a request_type Select (Standard / Top-up / Chip). The behaviour of all three was
# consolidated into the single Fuel Request controller; this patch migrates the
# stored rows, then drops the two obsolete DocTypes and their backing tables.
#
# Migration contract:
#   * Each source row is INSERTed as a Fuel Request row, PRESERVING its original
#     name (FT-… / FC-…), owner, creation, modified, modified_by and docstatus, so
#     submitted/cancelled state and any inbound references survive unchanged. Only
#     request_type is stamped (Top-up / Chip) and the type-specific fields are
#     copied across; status is mapped into the unified set.
#   * Idempotent / guarded: a row is skipped if a Fuel Request with that name
#     already exists (the marker is the preserved name + the migrated_from stamp),
#     so re-running the patch never double-inserts. No-op on a fresh install (the
#     source tables do not exist) or once the DocTypes are already dropped.
#   * The unified status set is Pending/Approved/Done/Failed/Reverted/Cancelled.
#     FT statuses (Pending/Approved/Done/Reverted/Cancelled) and FC statuses
#     (Pending/Approved/Done/Cancelled) are already a subset, so the map is the
#     identity; any unexpected value falls back to "Pending".
#
# Errors during migrate are handled IN this patch (rollback + log), never left for
# a manual fix (see memory feedback_patches).

import frappe

UNIFIED_STATUSES = {"Pending", "Approved", "Done", "Failed", "Reverted", "Cancelled"}

# Columns the unified Fuel Request table owns that we write for a migrated row.
# Source-specific columns are added per source below.
_BASE_COLUMNS = (
	"name",
	"creation",
	"modified",
	"modified_by",
	"owner",
	"docstatus",
	"idx",
	"naming_series",
	"request_type",
	"vehicle",
	"driver",
	"project",
	"status",
	"migrated_from",
	"amended_from",
)


def _map_status(value):
	"""Map a source status into the unified set; default to Pending."""
	return value if value in UNIFIED_STATUSES else "Pending"


def _table_exists(doctype):
	return f"tab{doctype}" in frappe.db.get_tables()


def _source_columns(doctype):
	"""Return the set of column names that actually exist on a source table, so a
	schema variant (a column added/removed across versions) never breaks the read."""
	return {
		c["Field"]
		for c in frappe.db.sql(f"SHOW COLUMNS FROM `tab{doctype}`", as_dict=True)
	}


def _migrate_topups():
	"""Copy every Fuel Topup Request row into Fuel Request as request_type=Top-up."""
	if not _table_exists("Fuel Topup Request"):
		return 0

	cols = _source_columns("Fuel Topup Request")
	# Only select columns that exist (schema-variant safe).
	select = [c for c in (
		"name", "creation", "modified", "modified_by", "owner", "docstatus", "idx",
		"vehicle", "driver", "project", "topup_litres", "status",
		"is_temporary", "reverted", "revert_due_date",
	) if c in cols]
	rows = frappe.db.sql(
		"SELECT {fields} FROM `tabFuel Topup Request`".format(fields=", ".join(f"`{c}`" for c in select)),
		as_dict=True,
	)

	migrated = 0
	for r in rows:
		if frappe.db.exists("Fuel Request", r["name"]):
			continue  # idempotent: already migrated (name preserved)
		values = {
			"name": r["name"],
			"creation": r.get("creation"),
			"modified": r.get("modified"),
			"modified_by": r.get("modified_by"),
			"owner": r.get("owner"),
			"docstatus": r.get("docstatus") or 0,
			"idx": r.get("idx") or 0,
			"naming_series": "FR-.######",
			"request_type": "Top-up",
			"vehicle": r.get("vehicle"),
			"driver": r.get("driver"),
			"project": r.get("project"),
			"status": _map_status(r.get("status")),
			"migrated_from": "Fuel Topup Request:" + r["name"],
			"amended_from": None,
			"topup_litres": r.get("topup_litres") or 0,
			"is_temporary": r.get("is_temporary") or 0,
			"reverted": r.get("reverted") or 0,
			"revert_due_date": r.get("revert_due_date"),
		}
		columns = _BASE_COLUMNS + ("topup_litres", "is_temporary", "reverted", "revert_due_date")
		_insert_row(columns, values)
		migrated += 1
	return migrated


def _migrate_chips():
	"""Copy every Fuel Chip Request row into Fuel Request as request_type=Chip."""
	if not _table_exists("Fuel Chip Request"):
		return 0

	cols = _source_columns("Fuel Chip Request")
	select = [c for c in (
		"name", "creation", "modified", "modified_by", "owner", "docstatus", "idx",
		"vehicle", "driver", "project", "chip_number", "action", "status",
		"inactivity_evidence", "estimated_monthly_saving", "owner_acknowledged",
	) if c in cols]
	rows = frappe.db.sql(
		"SELECT {fields} FROM `tabFuel Chip Request`".format(fields=", ".join(f"`{c}`" for c in select)),
		as_dict=True,
	)

	migrated = 0
	for r in rows:
		if frappe.db.exists("Fuel Request", r["name"]):
			continue
		values = {
			"name": r["name"],
			"creation": r.get("creation"),
			"modified": r.get("modified"),
			"modified_by": r.get("modified_by"),
			"owner": r.get("owner"),
			"docstatus": r.get("docstatus") or 0,
			"idx": r.get("idx") or 0,
			"naming_series": "FR-.######",
			"request_type": "Chip",
			"vehicle": r.get("vehicle"),
			"driver": r.get("driver"),
			"project": r.get("project"),
			"status": _map_status(r.get("status")),
			"migrated_from": "Fuel Chip Request:" + r["name"],
			"amended_from": None,
			"chip_number": r.get("chip_number"),
			"action": r.get("action") or "Issue",
			"inactivity_evidence": r.get("inactivity_evidence"),
			"estimated_monthly_saving": r.get("estimated_monthly_saving") or 0,
			"owner_acknowledged": r.get("owner_acknowledged") or 0,
		}
		columns = _BASE_COLUMNS + (
			"chip_number", "action", "inactivity_evidence",
			"estimated_monthly_saving", "owner_acknowledged",
		)
		_insert_row(columns, values)
		migrated += 1
	return migrated


def _insert_row(columns, values):
	"""Raw INSERT into tabFuel Request, writing only existing columns.

	Uses raw SQL (not frappe.get_doc(...).insert) deliberately: the source rows
	may be submitted/cancelled (docstatus 1/2) and we must preserve the original
	name, owner and timestamps exactly, which the ORM insert path would override
	(it stamps a fresh name from the series, owner = session user, creation = now).
	"""
	fr_cols = {
		c["Field"] for c in frappe.db.sql("SHOW COLUMNS FROM `tabFuel Request`", as_dict=True)
	}
	use = [c for c in columns if c in fr_cols]
	placeholders = ", ".join(["%s"] * len(use))
	frappe.db.sql(
		"INSERT INTO `tabFuel Request` ({cols}) VALUES ({ph})".format(
			cols=", ".join(f"`{c}`" for c in use), ph=placeholders
		),
		tuple(values.get(c) for c in use),
	)


def _drop_doctype(doctype):
	"""Drop an obsolete DocType and its backing table (guarded, idempotent)."""
	has_doctype = frappe.db.exists("DocType", doctype)
	has_table = _table_exists(doctype)
	if not (has_doctype or has_table):
		return

	# force=1 drops the table too; ignore_missing keeps this idempotent.
	frappe.delete_doc(
		"DocType",
		doctype,
		force=1,
		ignore_missing=True,
		ignore_permissions=True,  # audit-ok: system-managed schema cleanup patch
	)
	# Drop a stray table left behind if the DocType record was already gone.
	if _table_exists(doctype):
		frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `tab{doctype}`")


def execute():
	# Fresh install (or already merged): neither source table is present and the
	# unified field already exists — nothing to migrate or drop.
	if not (_table_exists("Fuel Topup Request") or _table_exists("Fuel Chip Request")):
		return

	if not frappe.db.exists("DocType", "Fuel Request"):
		return

	# This patch is registered in the (header-less) patches.txt, so it runs in the
	# PRE-model-sync phase — before bench migrate syncs the DocType JSONs. The
	# unified Fuel Request schema (request_type + the type-specific columns +
	# migrated_from) therefore may not exist yet, and we INSERT into those columns
	# below. Reload the DocType from its shipped JSON now (the standard Frappe idiom
	# for a pre-sync patch that needs a specific DocType's latest schema) so the
	# columns are present regardless of phase. Idempotent: a no-op if already synced.
	frappe.reload_doc("salis", "doctype", "fuel_request", force=True)

	fr_cols = {
		c["Field"] for c in frappe.db.sql("SHOW COLUMNS FROM `tabFuel Request`", as_dict=True)
	}
	if "request_type" not in fr_cols or "migrated_from" not in fr_cols:
		# Reload did not bring the columns in (unexpected) — skip rather than
		# corrupt; the next migrate retries once the schema is in place.
		frappe.log_error(
			title="merge_fuel_request_doctypes: unified schema not ready",
			message=(
				"tabFuel Request is still missing request_type/migrated_from after "
				"reload_doc; skipping migration this pass."
			),
		)
		return

	try:
		topups = _migrate_topups()
		chips = _migrate_chips()
		frappe.db.commit()
		frappe.logger().info(
			f"merge_fuel_request_doctypes: migrated {topups} top-up + {chips} chip "
			f"row(s) into Fuel Request."
		)
	except Exception:
		frappe.db.rollback()
		frappe.log_error(
			title="merge_fuel_request_doctypes: row migration failed",
			message=frappe.get_traceback(),
		)
		# Do not drop the source DocTypes if migration did not complete — leaving
		# them in place keeps the data recoverable on the next run.
		return

	try:
		_drop_doctype("Fuel Topup Request")
		_drop_doctype("Fuel Chip Request")
		frappe.db.commit()
		frappe.logger().info(
			"merge_fuel_request_doctypes: dropped obsolete DocTypes "
			"'Fuel Topup Request' and 'Fuel Chip Request'."
		)
	except Exception:
		frappe.db.rollback()
		frappe.log_error(
			title="merge_fuel_request_doctypes: failed to drop source DocTypes",
			message=frappe.get_traceback(),
		)
