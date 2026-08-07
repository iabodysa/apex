// Copyright (c) 2026, afmcoltd
frappe.ui.form.on("Idle Resident Report", {
	setup(frm) {
		frm.set_query("assignment", () => ({
			filters: {
				...(frm.doc.building ? { building: frm.doc.building } : {}),
			},
		}));
	},
});
