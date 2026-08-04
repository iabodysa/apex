// Copyright (c) 2026, AFMCO and contributors
frappe.ui.form.on("QR Location", {
	setup(frm) {
		frm.set_query("room", () => ({
			filters: {
				...(frm.doc.building ? { building: frm.doc.building } : {}),
			},
		}));
	},
});
