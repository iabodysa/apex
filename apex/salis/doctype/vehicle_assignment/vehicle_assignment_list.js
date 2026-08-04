// Copyright (c) 2026, AFMCO and contributors

frappe.listview_settings["Vehicle Assignment"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const palette = {
			"Active": "green",
			"Ended": "gray",
		};
		const value = doc.status;
		if (!value) return;
		return [__(value, null, "Vehicle Assignment"), palette[value] || "gray", `status,=,${value}`];
	},
};
