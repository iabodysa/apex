// Copyright (c) 2026, AFMCO and contributors

frappe.listview_settings["Maintenance Material"] = {
	add_fields: ["material_category"],
	get_indicator(doc) {
		const palette = {
			"Electrical": "yellow",
			"Air Conditioning": "cyan",
			"Plumbing": "blue",
			"Sanitary Fixtures": "light-blue",
			"Furniture": "purple",
			"General": "gray",
		};
		const value = doc.material_category;
		if (!value) return;
		return [__(value, null, "Maintenance Material"), palette[value] || "gray", `material_category,=,${value}`];
	},
};
