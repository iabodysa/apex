// Copyright (c) 2026, AFMCO and contributors

frappe.ui.form.on('SIM Custody Assignment', {
	setup(frm) {
		frm.set_query("project", () => ({
			filters: {
				...(frm.doc.company ? { company: frm.doc.company } : {}),
			},
		}));
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
