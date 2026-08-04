// Copyright (c) 2026, AFMCO and contributors

frappe.listview_settings["Material Transfer"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const palette = {
			"Draft": "gray",
			"In Transit": "orange",
			"Received": "green",
			"Cancelled": "darkgrey",
		};
		const value = doc.status;
		if (!value) return;
		return [__(value, null, "Material Transfer"), palette[value] || "gray", `status,=,${value}`];
	},
};
