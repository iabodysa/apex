// Copyright (c) 2026, AFMCO and contributors

frappe.listview_settings["Safety Round"] = {
	add_fields: ["overall_result"],
	get_indicator(doc) {
		const palette = {
			"Pass": "green",
			"Needs Attention": "orange",
			"Fail": "red",
		};
		const value = doc.overall_result;
		if (!value) return;
		return [__(value, null, "Safety Round"), palette[value] || "gray", `overall_result,=,${value}`];
	},
};
