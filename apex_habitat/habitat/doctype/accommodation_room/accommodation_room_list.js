frappe.listview_settings["Accommodation Room"] = {
	get_indicator(doc) {
		const colors = {
			"Available": "green",
			"Partially Occupied": "orange",
			"Full": "red",
			"Under Maintenance": "grey",
		};
		return [__(doc.status), colors[doc.status] || "blue", "status,=," + doc.status];
	},
};
