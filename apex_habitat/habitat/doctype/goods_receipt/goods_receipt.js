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
					frappe.msgprint({
						title: __("Not a Procurement Intake Store"),
						message: __("Building {0} is not flagged as a Procurement Intake Store.", [frm.doc.intake_building]),
						indicator: "orange",
					});
				}
			}
		);
	},
});
