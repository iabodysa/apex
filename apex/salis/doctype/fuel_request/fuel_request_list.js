// Copyright (c) 2026, afmcoltd

frappe.listview_settings["Fuel Request"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const colors = {
			"Pending": "orange",
			"Approved": "blue",
			"Done": "green",
			"Failed": "red",
			"Cancelled": "red",
		};
		return [__(doc.status), colors[doc.status] || "blue", "status,=," + doc.status];
	},
};
