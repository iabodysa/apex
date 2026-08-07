// Copyright (c) 2026, afmcoltd

frappe.listview_settings["Driver Clearance"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const colors = {
			"Open": "orange",
			"In Progress": "blue",
			"Cleared": "green",
			"Blocked": "red",
		};
		return [__(doc.status), colors[doc.status] || "blue", "status,=," + doc.status];
	},
};
