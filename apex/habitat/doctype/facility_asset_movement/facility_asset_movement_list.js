// Copyright (c) 2026, AFMCO and contributors

frappe.listview_settings["Facility Asset Movement"] = {
	add_fields: ["movement_category"],
	get_indicator(doc) {
		const palette = {
			"Same-Company Relocation": "blue",
			"Intercompany Temporary": "cyan",
			"Intercompany Permanent": "purple",
			"Maintenance Dispatch": "orange",
			"Return from Repair": "green",
			"Disposal/Scrap": "darkgrey",
		};
		const value = doc.movement_category;
		if (!value) return;
		return [__(value, null, "Facility Asset Movement"), palette[value] || "gray", `movement_category,=,${value}`];
	},
};
