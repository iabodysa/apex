// Copyright (c) 2026, AFMCO and contributors

frappe.listview_settings["Route Template"] = {
	add_fields: ["route_type"],
	get_indicator(doc) {
		const palette = {
			"Pickup": "blue",
			"Drop-off": "cyan",
			"Mixed": "purple",
		};
		const value = doc.route_type;
		if (!value) return;
		return [__(value, null, "Route Template"), palette[value] || "gray", `route_type,=,${value}`];
	},
};
