// Copyright (c) 2026, afmcoltd

frappe.listview_settings["Maintenance Material Template"] = {
	add_fields: ["issue_type"],
	get_indicator(doc) {
		const palette = {
			"Electrical": "yellow",
			"Plumbing": "blue",
			"Furniture": "purple",
			"Air Conditioning": "cyan",
			"Fire Safety": "red",
			"Pest Control": "green",
			"Structural": "orange",
			"Other": "gray",
		};
		const value = doc.issue_type;
		if (!value) return;
		return [__(value, null, "Maintenance Material Template"), palette[value] || "gray", `issue_type,=,${value}`];
	},
};
