// Copyright (c) 2026, AFMCO and contributors

frappe.listview_settings["SIM Card"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const palette = {
			"Available": "green",
			"Assigned": "blue",
			"Suspended": "orange",
			"Lost": "red",
			"Terminated": "darkgrey",
		};
		const value = doc.status;
		if (!value) return;
		return [__(value, null, "SIM Card"), palette[value] || "gray", `status,=,${value}`];
	},
};
