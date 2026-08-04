// Copyright (c) 2026, AFMCO and contributors

frappe.listview_settings["Idle Resident Report"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const palette = {
			"Open": "red",
			"Acknowledged": "orange",
			"Resolved": "green",
		};
		const value = doc.status;
		if (!value) return;
		return [__(value, null, "Idle Resident Report"), palette[value] || "gray", `status,=,${value}`];
	},
};
