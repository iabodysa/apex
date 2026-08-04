// Copyright (c) 2026, AFMCO and contributors

frappe.listview_settings["Goods Receipt"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const palette = {
			"Draft": "gray",
			"Received": "blue",
			"Handed Over": "green",
			"Cancelled": "darkgrey",
		};
		const value = doc.status;
		if (!value) return;
		return [__(value, null, "Goods Receipt"), palette[value] || "gray", `status,=,${value}`];
	},
};
