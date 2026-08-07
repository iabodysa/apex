// Copyright (c) 2026, afmcoltd

frappe.listview_settings["Utility Account"] = {
	add_fields: ["utility_type"],
	get_indicator(doc) {
		const palette = {
			"Electricity": "yellow",
			"Water": "blue",
			"Gas": "orange",
			"Internet": "purple",
			"Telecom": "cyan",
		};
		const value = doc.utility_type;
		if (!value) return;
		return [__(value, null, "Utility Account"), palette[value] || "gray", `utility_type,=,${value}`];
	},
};
