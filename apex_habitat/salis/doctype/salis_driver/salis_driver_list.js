frappe.listview_settings["Salis Driver"] = {
	get_indicator(doc) {
		const colors = {
			"Active": "green",
			"Stopped": "orange",
			"On Leave": "blue",
			"Released": "grey",
		};
		return [__(doc.status), colors[doc.status] || "grey", "status,=," + doc.status];
	},
};
