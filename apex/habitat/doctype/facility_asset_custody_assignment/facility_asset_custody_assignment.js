// Copyright (c) 2026, AFMCO and contributors
frappe.ui.form.on("Facility Asset Custody Assignment", {
	setup(frm) {
		frm.set_query("facility_asset", "assets_in_custody", () => ({
			filters: {
				...(frm.doc.building ? { building: frm.doc.building } : {}),
			},
		}));
	},
});
