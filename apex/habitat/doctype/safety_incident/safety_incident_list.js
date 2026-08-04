// Copyright (c) 2026, AFMCO and contributors

frappe.listview_settings["Safety Incident"] = {
	add_fields: ["severity"],
	get_indicator(doc) {
		const palette = {
			"Low": "blue",
			"Medium": "yellow",
			"High": "orange",
			"Severe": "red",
			"Critical": "red",
		};
		const value = doc.severity;
		if (!value) return;
		return [__(value, null, "Safety Incident"), palette[value] || "gray", `severity,=,${value}`];
	},
};
