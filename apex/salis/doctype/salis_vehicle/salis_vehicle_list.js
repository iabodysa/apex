// Copyright (c) 2026, afmcoltd

frappe.listview_settings["Salis Vehicle"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const colors = {
			"Active": "green",
			"Stopped": "red",
			"Under Maintenance": "orange",
			"Released": "grey",
		};
		return [__(doc.status), colors[doc.status] || "blue", "status,=," + doc.status];
	},
};
