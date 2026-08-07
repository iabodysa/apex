// Copyright (c) 2026, afmcoltd

frappe.listview_settings["Safety Task Execution"] = {
	add_fields: ["execution_status"],
	get_indicator(doc) {
		const palette = {
			"Excellent": "green",
			"Good": "cyan",
			"Average": "yellow",
			"Poor": "orange",
			"Not Done": "red",
		};
		const value = doc.execution_status;
		if (!value) return;
		return [__(value, null, "Safety Task Execution"), palette[value] || "gray", `execution_status,=,${value}`];
	},
};
