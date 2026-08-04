// Copyright (c) 2026, AFMCO and contributors

frappe.listview_settings["Rental Vehicle Movement"] = {
	add_fields: ["fuel_level"],
	get_indicator(doc) {
		const palette = {
			"Empty": "red",
			"Quarter": "orange",
			"Half": "yellow",
			"ThreeQuarter": "light-blue",
			"Full": "green",
		};
		const value = doc.fuel_level;
		if (!value) return;
		return [__(value, null, "Rental Vehicle Movement"), palette[value] || "gray", `fuel_level,=,${value}`];
	},
};
