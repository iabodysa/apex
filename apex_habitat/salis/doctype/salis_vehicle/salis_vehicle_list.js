frappe.listview_settings["Salis Vehicle"] = {
	get_indicator(doc) {
		const colors = {
			"Active": "green",
			"Stopped": "orange",
			"Under Maintenance": "red",
			"Released": "grey",
		};
		return [__(doc.status), colors[doc.status] || "grey", "status,=," + doc.status];
	},
};
