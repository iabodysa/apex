// Copyright (c) 2026, afmcoltd

frappe.listview_settings["Dispatch Trip"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const colors = {
			"Planned": "blue",
			"Dispatched": "orange",
			"Completed": "green",
			"Cancelled": "red",
		};
		return [__(doc.status), colors[doc.status] || "blue", "status,=," + doc.status];
	},
};
