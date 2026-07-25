// Copyright (c) 2026, AFMCO and contributors
// Scope the SIM, employee and project pickers to the acting company so a custody
// event cannot be built across companies.

frappe.ui.form.on('SIM Custody Assignment', {
	setup(frm) {
		frm.set_query('sim_card', () => ({
			filters: frm.doc.company ? { company: frm.doc.company } : {},
		}));
		frm.set_query('employee', () => ({
			filters: {
				status: 'Active',
				...(frm.doc.company ? { company: frm.doc.company } : {}),
			},
		}));
	},
});
