frappe.listview_settings["Movement Cost Recovery"] = {
	get_indicator(doc) {
		const colors = {
			"Open": "blue",
			"Acknowledged": "orange",
			"Approved": "blue",
			"Recovered": "green",
			"Waived": "grey",
			"Rejected": "red",
		};
		return [__(doc.status), colors[doc.status] || "grey", "status,=," + doc.status];
	},
};
