// Copyright (c) 2026, afmcoltd

frappe.listview_settings["Vehicle Suspension"] = {
	add_fields: ["stop_reason"],
	get_indicator(doc) {
		const palette = {
			"Accident": "red",
			"Maintenance": "orange",
			"Violation": "purple",
			"Rental Return": "blue",
			"Other": "gray",
		};
		const value = doc.stop_reason;
		if (!value) return;
		return [__(value, null, "Vehicle Suspension"), palette[value] || "gray", `stop_reason,=,${value}`];
	},
};
