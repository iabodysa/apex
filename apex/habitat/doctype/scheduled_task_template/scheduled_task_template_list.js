// Copyright (c) 2026, afmcoltd

frappe.listview_settings["Scheduled Task Template"] = {
	add_fields: ["task_type"],
	get_indicator(doc) {
		const palette = {
			"Safety": "red",
			"Maintenance": "orange",
			"Inspection": "blue",
			"Cleaning": "cyan",
			"Other": "gray",
		};
		const value = doc.task_type;
		if (!value) return;
		return [__(value, null, "Scheduled Task Template"), palette[value] || "gray", `task_type,=,${value}`];
	},
};
