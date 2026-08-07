// Copyright (c) 2026, afmcoltd

frappe.listview_settings["Vehicle Handover"] = {
	add_fields: ["discrepancy_status"],
	get_indicator(doc) {
		const palette = {
			"Clean": "green",
			"Discrepancy": "red",
			"Resolved": "blue",
		};
		const value = doc.discrepancy_status;
		if (!value) return;
		return [__(value, null, "Vehicle Handover"), palette[value] || "gray", `discrepancy_status,=,${value}`];
	},
};
