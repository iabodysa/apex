// Client-side script for Driver Clearance

frappe.ui.form.on("Driver Clearance", {
	refresh(frm) {
		_update_clearance_indicator(frm);
	},
	status(frm) {
		_update_clearance_indicator(frm);
	},
});

function _update_clearance_indicator(frm) {
	frm.page.clear_indicator();
	const colors = {
		"Open": "orange",
		"In Progress": "blue",
		"Cleared": "green",
		"Blocked": "red",
	};
	if (frm.doc.status) {
		frm.page.set_indicator(__(frm.doc.status), colors[frm.doc.status] || "blue");
	}
}

frappe.listview_settings["Driver Clearance"] = {
	get_indicator(doc) {
		const colors = {
			"Open": "orange",
			"In Progress": "blue",
			"Cleared": "green",
			"Blocked": "red",
		};
		return [__(doc.status), colors[doc.status] || "blue", "status,=," + doc.status];
	},
};
