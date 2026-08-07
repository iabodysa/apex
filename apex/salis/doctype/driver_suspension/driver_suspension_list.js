// Copyright (c) 2026, afmcoltd

frappe.listview_settings["Driver Suspension"] = {
	add_fields: ["stop_reason"],
	get_indicator(doc) {
		const palette = {
			"Violation": "red",
			"Leave": "blue",
			"Termination": "darkgrey",
			"Transfer": "cyan",
			"Other": "gray",
		};
		const value = doc.stop_reason;
		if (!value) return;
		return [__(value, null, "Driver Suspension"), palette[value] || "gray", `stop_reason,=,${value}`];
	},
};
