// Copyright (c) 2026, afmcoltd

frappe.listview_settings["Cleaning Log"] = {
	add_fields: ["cleaner_type"],
	get_indicator(doc) {
		const palette = {
			"Internal Employee": "blue",
			"Subcontractor": "purple",
			"External Worker": "cyan",
		};
		const value = doc.cleaner_type;
		if (!value) return;
		return [__(value, null, "Cleaning Log"), palette[value] || "gray", `cleaner_type,=,${value}`];
	},
};
