// Copyright (c) 2026, afmcoltd
frappe.ui.form.on("Cleaning Log", {
	setup(frm) {
		frm.set_query("subcontractor_service_order", () => ({
			filters: {
				...(frm.doc.building ? { building: frm.doc.building } : {}),
			},
		}));
		frm.set_query("room", "room_details", () => ({
			filters: {
				...(frm.doc.building ? { building: frm.doc.building } : {}),
			},
		}));
	},
});
