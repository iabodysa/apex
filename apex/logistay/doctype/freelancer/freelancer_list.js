// Copyright (c) 2026, AFMCO and contributors

frappe.listview_settings["Freelancer"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const palette = {
			"Active": "green",
			"Expired": "orange",
			"Terminated": "red",
		};
		const value = doc.status;
		if (!value) return;
		return [__(value, null, "Freelancer"), palette[value] || "gray", `status,=,${value}`];
	},
};
