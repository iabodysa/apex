// Copyright (c) 2026, afmcoltd

frappe.listview_settings["Fuel Claim"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const colors = {
			"Draft": "gray",
			"Submitted to Movement": "orange",
			"Reconciled": "blue",
			"Approved": "green",
			"Disputed": "red",
			"Closed": "darkgrey",
		};
		return [__(doc.status), colors[doc.status] || "blue", "status,=," + doc.status];
	},
};
