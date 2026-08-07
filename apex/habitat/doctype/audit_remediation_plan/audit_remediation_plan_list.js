// Copyright (c) 2026, afmcoltd

frappe.listview_settings["Audit Remediation Plan"] = {
	add_fields: ["overall_status"],
	get_indicator(doc) {
		const palette = {
			"Open": "orange",
			"In Progress": "blue",
			"Evidence Submitted": "cyan",
			"Closed by Client": "green",
			"Overdue": "red",
		};
		const value = doc.overall_status;
		if (!value) return;
		return [__(value, null, "Audit Remediation Plan"), palette[value] || "gray", `overall_status,=,${value}`];
	},
};
