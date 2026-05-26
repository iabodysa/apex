frappe.listview_settings["Fuel Claim"] = {
	get_indicator(doc) {
		const colors = {
			"Draft": "grey",
			"Submitted to Movement": "orange",
			"Reconciled": "blue",
			"Approved": "green",
			"Disputed": "red",
			"Closed": "green",
		};
		return [__(doc.status), colors[doc.status] || "grey", "status,=," + doc.status];
	},
};
