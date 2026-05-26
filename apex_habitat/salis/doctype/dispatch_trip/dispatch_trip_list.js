frappe.listview_settings["Dispatch Trip"] = {
	get_indicator(doc) {
		const colors = {
			"Planned": "blue",
			"Dispatched": "orange",
			"Completed": "green",
			"Cancelled": "red",
		};
		return [__(doc.status), colors[doc.status] || "grey", "status,=," + doc.status];
	},
};
