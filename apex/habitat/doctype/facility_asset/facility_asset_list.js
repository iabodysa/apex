// Copyright (c) 2026, AFMCO and contributors

frappe.listview_settings["Facility Asset"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const palette = {
			"Operational": "green",
			"Faulty": "red",
			"Under Repair": "orange",
			"Replaced": "blue",
			"Scrapped": "darkgrey",
			"In Storage": "gray",
		};
		const value = doc.status;
		if (!value) return;
		return [__(value, null, "Facility Asset"), palette[value] || "gray", `status,=,${value}`];
	},
};
