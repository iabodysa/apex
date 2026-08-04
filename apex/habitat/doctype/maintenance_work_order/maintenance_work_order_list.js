// Copyright (c) 2026, AFMCO and contributors

frappe.listview_settings["Maintenance Work Order"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const palette = {
			"Draft": "gray",
			"Planned": "blue",
			"In Progress": "orange",
			"Completed": "green",
			"Cancelled": "darkgrey",
		};
		const value = doc.status;
		if (!value) return;
		return [__(value, null, "Maintenance Work Order"), palette[value] || "gray", `status,=,${value}`];
	},
};
