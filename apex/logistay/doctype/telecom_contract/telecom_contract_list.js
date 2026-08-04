// Copyright (c) 2026, AFMCO and contributors

frappe.listview_settings["Telecom Contract"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const palette = {
			"Draft": "gray",
			"Active": "green",
			"Expired": "orange",
			"Terminated": "red",
		};
		const value = doc.status;
		if (!value) return;
		return [__(value, null, "Telecom Contract"), palette[value] || "gray", `status,=,${value}`];
	},
};
