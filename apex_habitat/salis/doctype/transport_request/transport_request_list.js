frappe.listview_settings["Transport Request"] = {
	get_indicator(doc) {
		const colors = {
			"New": "blue",
			"Validated": "blue",
			"Approved": "blue",
			"Scheduled": "orange",
			"Fulfilled": "green",
			"Rejected": "red",
			"Cancelled": "red",
		};
		return [__(doc.status), colors[doc.status] || "grey", "status,=," + doc.status];
	},
};
