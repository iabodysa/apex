// Copyright (c) 2026, AFMCO and contributors

frappe.listview_settings["Facility Asset Delivery"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const palette = {
			"Draft": "gray",
			"Pending Exits": "orange",
			"Released": "blue",
			"Delivered": "green",
			"Cancelled": "darkgrey",
		};
		const value = doc.status;
		if (!value) return;
		return [__(value, null, "Facility Asset Delivery"), palette[value] || "gray", `status,=,${value}`];
	},
};
