// Copyright (c) 2026, AFMCO and contributors
frappe.ui.form.on("Vehicle Damage Write-Off", {
	setup(frm) {
		frm.set_query("source_handover", () => ({
			filters: {
				...(frm.doc.vehicle ? { vehicle: frm.doc.vehicle } : {}),
			},
		}));
		frm.set_query("source_incident", () => ({
			filters: {
				...(frm.doc.vehicle ? { vehicle: frm.doc.vehicle } : {}),
			},
		}));
	},
});
