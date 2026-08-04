// Copyright (c) 2026, AFMCO and contributors
frappe.ui.form.on("Facility Asset Movement", {
	setup(frm) {
		frm.set_query("facility_asset", () => ({
			filters: {
				...(frm.doc.from_building ? { building: frm.doc.from_building } : {}),
			},
		}));
		frm.set_query("from_room", () => ({
			filters: {
				...(frm.doc.from_building ? { building: frm.doc.from_building } : {}),
			},
		}));
		frm.set_query("to_room", () => ({
			filters: {
				...(frm.doc.to_building ? { building: frm.doc.to_building } : {}),
			},
		}));
	},
});
