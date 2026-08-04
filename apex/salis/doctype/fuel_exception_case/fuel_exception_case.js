// Copyright (c) 2026, AFMCO and contributors
frappe.ui.form.on("Fuel Exception Case", {
	setup(frm) {
		frm.set_query("fuel_request", () => ({
			filters: {
				...(frm.doc.vehicle ? { vehicle: frm.doc.vehicle } : {}),
			},
		}));
		frm.set_query("fuel_quota", () => ({
			filters: {
				...(frm.doc.vehicle ? { vehicle: frm.doc.vehicle } : {}),
			},
		}));
	},
});
