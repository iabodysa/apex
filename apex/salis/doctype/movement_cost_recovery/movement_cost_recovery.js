// Copyright (c) 2026, afmcoltd
frappe.ui.form.on("Movement Cost Recovery", {
	setup(frm) {
		frm.set_query("vehicle", () => ({
			filters: {
				...(frm.doc.company ? { company: frm.doc.company } : {}),
			},
		}));
		frm.set_query("employee", () => ({
			filters: {
				...(frm.doc.company ? { company: frm.doc.company } : {}),
			},
		}));
		frm.set_query("cost_center", () => ({
			filters: {
				...(frm.doc.company ? { company: frm.doc.company } : {}),
			},
		}));
	},
});
