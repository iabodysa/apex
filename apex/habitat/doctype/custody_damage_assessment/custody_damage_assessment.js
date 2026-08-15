// Copyright (c) 2026, afmcoltd
frappe.ui.form.on("Custody Damage Assessment", {
	setup(frm) {
		frm.set_query("custody_return", () => ({
			filters: {
				...(frm.doc.building ? { building: frm.doc.building } : {}),
			},
		}));
	},
});
