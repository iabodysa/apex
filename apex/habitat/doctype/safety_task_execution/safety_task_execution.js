// Copyright (c) 2026, afmcoltd
frappe.ui.form.on("Safety Task Execution", {
	setup(frm) {
		frm.set_query("safety_round", () => ({
			filters: {
				...(frm.doc.building ? { building: frm.doc.building } : {}),
			},
		}));
		frm.set_query("linked_maintenance_request", () => ({
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
