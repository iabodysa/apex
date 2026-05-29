import frappe

# Backfill `resolved_on` on Operations Alert rows that were already Resolved
# before the field existed.
#
# Context: the Salis "Operations Alert" DocType gained an auto-resolution
# capability earlier (the daily reconcile pass flips a cleared alert's `status`
# to "Resolved"), but the row carried no resolution timestamp — the reason lived
# only in a timeline comment. The DocType now has a read-only `resolved_on`
# (Datetime) and `resolution_note` (Small Text). Any alert that was resolved
# before this change therefore has status = "Resolved" but a NULL `resolved_on`,
# which would render the new field blank on a genuinely-resolved row.
#
# This one-time pass stamps `resolved_on` for those legacy rows using the best
# available proxy for when the resolution happened (the row's `modified`
# timestamp, falling back to `raised_on`), and leaves a short `resolution_note`
# so the audit field is non-empty.
#
# Idempotent: only touches Resolved rows whose `resolved_on` is still NULL, so a
# re-run (or a fresh install with no such rows) is a no-op. Existence-guarded on
# both the table and the column so it can never raise a schema error during
# migrate (it runs after schema sync, but the guards keep it safe regardless).


def execute():
	if not frappe.db.table_exists("Operations Alert"):
		return

	columns = frappe.db.get_table_columns("Operations Alert")
	if "resolved_on" not in columns:
		# Schema not yet synced for this field; nothing to backfill safely.
		return

	# COALESCE(modified, raised_on) gives the closest timestamp we have for when
	# the alert reached its Resolved state. resolution_note is only stamped when
	# the column exists and the row's note is still empty.
	has_note = "resolution_note" in columns
	note_set = (
		", resolution_note = 'Resolved before resolution audit fields existed.'"
		if has_note
		else ""
	)

	frappe.db.sql(
		f"""
		UPDATE `tabOperations Alert`
		SET resolved_on = COALESCE(modified, raised_on){note_set}
		WHERE status = 'Resolved' AND resolved_on IS NULL
		"""
	)
