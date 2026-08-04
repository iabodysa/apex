// Copyright (c) 2026, AFMCO and contributors

frappe.listview_settings["Custody Handover"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const palette = {
			"Draft": "gray",
			"Pending Receipt": "orange",
			"Under Review": "yellow",
			"Approved": "blue",
			"Confirmed": "green",
			"Rejected": "red",
			"Cancelled": "darkgrey",
		};
		const value = doc.status;
		if (!value) return;
		return [__(value, null, "Custody Handover"), palette[value] || "gray", `status,=,${value}`];
	},
};
