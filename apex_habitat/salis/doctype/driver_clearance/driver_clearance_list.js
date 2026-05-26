frappe.listview_settings["Driver Clearance"] = {
	get_indicator(doc) {
		const colors = {
			"Open": "blue",
			"In Progress": "orange",
			"Cleared": "green",
			"Blocked": "red",
		};
		return [__(doc.status), colors[doc.status] || "grey", "status,=," + doc.status];
	},
};
