// Copyright (c) 2026, AFMCO and contributors
// Custody transitions run from the Telecom Control page, not the SIM form, so the
// form only constrains the contract picker to submitted contracts in scope.

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
