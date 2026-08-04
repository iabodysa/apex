// Copyright (c) 2026, AFMCO and contributors

frappe.listview_settings["Custody Issue"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const palette = {
			"Draft": "gray",
			"Issued": "blue",
			"Returned": "green",
			"Partially Returned": "orange",
			"Cancelled": "darkgrey",
		};
		const value = doc.status;
		if (!value) return;
		return [__(value, null, "Custody Issue"), palette[value] || "gray", `status,=,${value}`];
	},
};
