// Copyright (c) 2026, afmcoltd

frappe.listview_settings["Route Plan"] = {
	add_fields: ["shift"],
	get_indicator(doc) {
		const palette = {
			"Morning": "yellow",
			"Evening": "orange",
			"Night": "purple",
		};
		const value = doc.shift;
		if (!value) return;
		return [__(value, null, "Route Plan"), palette[value] || "gray", `shift,=,${value}`];
	},
};
