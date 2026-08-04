// Copyright (c) 2026, AFMCO and contributors

frappe.listview_settings["Subcontractor Service Order"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const palette = {
			"Scheduled": "blue",
			"In Progress": "orange",
			"Completed": "green",
			"Missed": "red",
			"Cancelled": "darkgrey",
		};
		const value = doc.status;
		if (!value) return;
		return [__(value, null, "Subcontractor Service Order"), palette[value] || "gray", `status,=,${value}`];
	},
};
