// Copyright (c) 2026, AFMCO and contributors

frappe.listview_settings["Housing Assignment"] = {
	add_fields: ["assignment_type"],
	get_indicator(doc) {
		const palette = {
			"New Assignment": "green",
			"Transfer": "blue",
			"Return from Leave": "cyan",
		};
		const value = doc.assignment_type;
		if (!value) return;
		return [__(value, null, "Housing Assignment"), palette[value] || "gray", `assignment_type,=,${value}`];
	},
};
