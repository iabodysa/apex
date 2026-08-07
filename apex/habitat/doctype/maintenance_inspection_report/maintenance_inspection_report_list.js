// Copyright (c) 2026, afmcoltd

frappe.listview_settings["Maintenance Inspection Report"] = {
	add_fields: ["overall_result"],
	get_indicator(doc) {
		const palette = {
			"Pass": "green",
			"Pass with Observations": "yellow",
			"Fail": "red",
		};
		const value = doc.overall_result;
		if (!value) return;
		return [__(value, null, "Maintenance Inspection Report"), palette[value] || "gray", `overall_result,=,${value}`];
	},
};
