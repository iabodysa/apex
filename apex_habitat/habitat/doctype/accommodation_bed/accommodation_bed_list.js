frappe.listview_settings["Accommodation Bed"] = {
	get_indicator(doc) {
		const colors = {
			"Available": "green",
			"Occupied": "red",
			"Out of Service": "grey",
		};
		return [__(doc.status), colors[doc.status] || "blue", "status,=," + doc.status];
	},
};
