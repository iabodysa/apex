// Copyright (c) 2026, AFMCO and contributors

frappe.listview_settings["Operations Alert"] = {
	add_fields: ["severity"],
	get_indicator(doc) {
		const palette = {
			"Info": "blue",
			"Warning": "orange",
			"Critical": "red",
		};
		const value = doc.severity;
		if (!value) return;
		return [__(value, null, "Operations Alert"), palette[value] || "gray", `severity,=,${value}`];
	},
};
