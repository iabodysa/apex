// Copyright (c) 2026, AFMCO and contributors
frappe.ui.form.on("Goods Receipt", {
	intake_building(frm) {
		if (!frm.doc.intake_building) {
			return;
		}
		frappe.db.get_value(
			"Accommodation Building",
			frm.doc.intake_building,
			"is_procurement_store",
			(r) => {
				if (r && !r.is_procurement_store) {
					// Transient advisory on field change — the user may still proceed.
					frappe.show_alert({
						message: __("Building {0} is not flagged as a Procurement Intake Store.", [frm.doc.intake_building]),
						indicator: "orange",
					});
				}
			}
		);
	},
});
