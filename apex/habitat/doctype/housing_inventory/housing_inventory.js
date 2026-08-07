// Copyright (c) 2026, afmcoltd
frappe.ui.form.on("Housing Inventory", {
	setup(frm) {
		frm.set_query("room", () => ({
			filters: {
				...(frm.doc.building ? { building: frm.doc.building } : {}),
			},
		}));
		frm.set_query("facility_asset", () => ({
			filters: {
				...(frm.doc.building ? { building: frm.doc.building } : {}),
			},
		}));
	},
});
