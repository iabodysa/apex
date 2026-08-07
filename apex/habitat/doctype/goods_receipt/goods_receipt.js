// Copyright (c) 2026, afmcoltd
frappe.ui.form.on("Goods Receipt", {
	intake_building(frm) {
		if (!frm.doc.intake_building) {
			return;
		}
		frappe.db.get_value(
			"Building",
			frm.doc.intake_building,
			"is_procurement_store",
			(r) => {
				if (r && !r.is_procurement_store) {
					frappe.show_alert({
						message: __("Building {0} is not flagged as a Procurement Intake Store.", [frm.doc.intake_building]),
						indicator: "orange",
					});
				}
			}
		);
	},
});
