// Copyright (c) 2026, AFMCO and contributors
frappe.ui.form.on("Maintenance Inspection Report", {
	setup(frm) {
		frm.set_query("facility_asset", () => ({
			filters: {
				...(frm.doc.building ? { building: frm.doc.building } : {}),
			},
		}));
		frm.set_query("maintenance_work_order", () => ({
			filters: {
				...(frm.doc.building ? { building: frm.doc.building } : {}),
			},
		}));
		frm.set_query("room", "findings", () => ({
			filters: {
				...(frm.doc.building ? { building: frm.doc.building } : {}),
			},
		}));
	},
});
