// Copyright (c) 2026, AFMCO and contributors

frappe.ui.form.on("Movement Cost Transfer", {
	setup(frm) {
		frm.set_query("from_project", () => ({
			filters: {
				...(frm.doc.company ? { company: frm.doc.company } : {}),
			},
		}));
		frm.set_query("to_project", () => ({
			filters: {
				...(frm.doc.company ? { company: frm.doc.company } : {}),
				...(frm.doc.from_project ? { name: ["!=", frm.doc.from_project] } : {}),
			},
		}));
		frm.set_query("from_cost_center", () => ({
			filters: {
				...(frm.doc.company ? { company: frm.doc.company } : {}),
			},
		}));
		frm.set_query("to_cost_center", () => ({
			filters: {
				...(frm.doc.company ? { company: frm.doc.company } : {}),
			},
		}));
	},
	refresh(frm) {
		_update_mct_indicator(frm);
	},
	status(frm) {
		_update_mct_indicator(frm);
	},
});

function _update_mct_indicator(frm) {
	frm.page.clear_indicator();
	const colors = {
		"Draft": "gray",
		"Pending Approval": "orange",
		"Approved": "blue",
		"Posted (memo)": "green",
		"Rejected": "red",
		"Cancelled": "red",
	};
	if (frm.doc.status) {
		frm.page.set_indicator(__(frm.doc.status), colors[frm.doc.status] || "blue");
	}
}

frappe.listview_settings["Movement Cost Transfer"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const colors = {
			"Draft": "gray",
			"Pending Approval": "orange",
			"Approved": "blue",
			"Posted (memo)": "green",
			"Rejected": "red",
			"Cancelled": "red",
		};
		return [__(doc.status), colors[doc.status] || "blue", "status,=," + doc.status];
	},
};
