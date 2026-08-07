// Copyright (c) 2026, afmcoltd

frappe.listview_settings["Vehicle Assignment"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const colors = {
			"Active": "green",
			"Ended": "grey",
		};
		return [__(doc.status), colors[doc.status] || "blue", "status,=," + doc.status];
	},
};
