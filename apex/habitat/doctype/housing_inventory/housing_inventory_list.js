// Copyright (c) 2026, afmcoltd

frappe.listview_settings["Housing Inventory"] = {
	add_fields: ["condition"],
	get_indicator(doc) {
		const palette = {
			"New": "cyan",
			"Good": "green",
			"Fair": "yellow",
			"Needs Maintenance": "orange",
			"Damaged": "red",
			"Missing": "darkgrey",
		};
		const value = doc.condition;
		if (!value) return;
		return [__(value, null, "Housing Inventory"), palette[value] || "gray", `condition,=,${value}`];
	},
};
