// Copyright (c) 2026, AFMCO and contributors

frappe.listview_settings["Vehicle Incident"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const palette = {
			"Open": "red",
			"Under Review": "orange",
			"Closed": "green",
			"Cancelled": "darkgrey",
		};
		const value = doc.status;
		if (!value) return;
		return [__(value, null, "Vehicle Incident"), palette[value] || "gray", `status,=,${value}`];
	},
};
