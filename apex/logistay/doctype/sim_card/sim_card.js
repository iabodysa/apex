// Copyright (c) 2026, AFMCO and contributors

frappe.ui.form.on('SIM Card', {
	setup(frm) {
		frm.set_query('telecom_contract', () => ({
			filters: {
				docstatus: 1,
				...(frm.doc.company ? { company: frm.doc.company } : {}),
			},
		}));
	},
});
