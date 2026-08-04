// Copyright (c) 2026, AFMCO and contributors

frappe.listview_settings["Scheduled Task Instance"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const palette = {
			"Open": "blue",
			"In Progress": "orange",
			"Completed": "green",
			"Overdue": "red",
			"Cancelled": "darkgrey",
		};
		const value = doc.status;
		if (!value) return;
		return [__(value, null, "Scheduled Task Instance"), palette[value] || "gray", `status,=,${value}`];
	},
};
