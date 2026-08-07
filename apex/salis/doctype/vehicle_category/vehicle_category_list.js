// Copyright (c) 2026, afmcoltd

frappe.listview_settings["Vehicle Category"] = {
	add_fields: ["default_fuel_type"],
	get_indicator(doc) {
		const palette = {
			"Petrol": "orange",
			"Diesel": "darkgrey",
			"Electric": "green",
		};
		const value = doc.default_fuel_type;
		if (!value) return;
		return [__(value, null, "Vehicle Category"), palette[value] || "gray", `default_fuel_type,=,${value}`];
	},
};
