// Copyright (c) 2026, afmcoltd
frappe.ui.form.on("Safety Inspection Report", {
	setup(frm) {
		frm.set_query("room", "safety_findings", () => ({
			filters: {
				...(frm.doc.building ? { building: frm.doc.building } : {}),
			},
		}));
		frm.set_query("room", "maintenance_findings", () => ({
			filters: {
				...(frm.doc.building ? { building: frm.doc.building } : {}),
			},
		}));
	},
});
