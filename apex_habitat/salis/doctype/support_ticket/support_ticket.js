// Client-side script for Support Ticket
frappe.ui.form.on("Support Ticket", {
	refresh(frm) {
		_update_ticket_indicator(frm);
	},
	status(frm) {
		_update_ticket_indicator(frm);
	},
	priority(frm) {
		_update_ticket_indicator(frm);
	},
});

function _update_ticket_indicator(frm) {
	frm.page.clear_indicator();

	const status_colors = {
		"New": "orange",
		"In Progress": "orange",
		"Waiting": "yellow",
		"Resolved": "green",
		"Closed": "grey",
	};
	if (frm.doc.status) {
		frm.page.set_indicator(__(frm.doc.status), status_colors[frm.doc.status] || "blue");
	}

	if (frm.doc.priority === "Urgent" || frm.doc.priority === "High") {
		const priority_colors = { "Urgent": "red", "High": "orange" };
		frm.page.set_indicator(
			__("{0} Priority", [__(frm.doc.priority)]),
			priority_colors[frm.doc.priority]
		);
	}
}

frappe.listview_settings["Support Ticket"] = {
	get_indicator(doc) {
		const colors = {
			"New": "orange",
			"In Progress": "orange",
			"Waiting": "yellow",
			"Resolved": "green",
			"Closed": "grey",
		};
		return [__(doc.status), colors[doc.status] || "blue", "status,=," + doc.status];
	},
};
