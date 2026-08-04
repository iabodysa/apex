// Copyright (c) 2026, AFMCO and contributors

frappe.listview_settings["Fuel Quota"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const palette = {
			"Active": "green",
			"Exhausted": "orange",
			"Closed": "gray",
		};
		const value = doc.status;
		if (!value) return;
		return [__(value, null, "Fuel Quota"), palette[value] || "gray", `status,=,${value}`];
	},
};
