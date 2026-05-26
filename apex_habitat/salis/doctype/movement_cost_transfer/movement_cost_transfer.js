// Client-side script for Movement Cost Transfer

frappe.ui.form.on("Movement Cost Transfer", {
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
