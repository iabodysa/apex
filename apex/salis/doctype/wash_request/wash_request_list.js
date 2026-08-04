// Copyright (c) 2026, AFMCO and contributors

frappe.listview_settings["Wash Request"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const palette = {
			"Pending": "orange",
			"Approved": "blue",
			"Done": "green",
			"Cancelled": "darkgrey",
		};
		const value = doc.status;
		if (!value) return;
		return [__(value, null, "Wash Request"), palette[value] || "gray", `status,=,${value}`];
	},
};
