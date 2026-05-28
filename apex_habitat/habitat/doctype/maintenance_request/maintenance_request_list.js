frappe.listview_settings["Maintenance Request"] = {
	get_indicator(doc) {
		const colors = {
			"Open": "red",
			"Assigned": "blue",
			"In Progress": "orange",
			"Resolved": "green",
			"Closed": "grey",
			"Reopened": "red",
		};
		return [__(doc.status), colors[doc.status] || "grey", "status,=," + doc.status];
	},
};
