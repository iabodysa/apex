// Copyright (c) 2026, AFMCO and contributors

frappe.listview_settings["SIM Custody Assignment"] = {
	add_fields: ["action"],
	get_indicator(doc) {
		const palette = {
			"Assign": "blue",
			"Transfer": "cyan",
			"Return": "green",
			"Suspend": "orange",
			"Reactivate": "light-blue",
			"Lost": "red",
			"Terminated": "darkgrey",
		};
		const value = doc.action;
		if (!value) return;
		return [__(value, null, "SIM Custody Assignment"), palette[value] || "gray", `action,=,${value}`];
	},
};
