// Copyright (c) 2026, AFMCO and contributors

frappe.listview_settings["Temporary Worker"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const palette = {
			"Active": "green",
			"Linked": "blue",
			"Expired": "orange",
		};
		const value = doc.status;
		if (!value) return;
		return [__(value, null, "Temporary Worker"), palette[value] || "gray", `status,=,${value}`];
	},
};
