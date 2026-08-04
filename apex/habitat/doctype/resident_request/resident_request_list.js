// Copyright (c) 2026, AFMCO and contributors

frappe.listview_settings["Resident Request"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const palette = {
			"New": "blue",
			"Triaged": "cyan",
			"Assigned": "light-blue",
			"In Progress": "orange",
			"Waiting Evidence": "yellow",
			"Resolved": "green",
			"Rejected": "red",
			"Closed": "gray",
		};
		const value = doc.status;
		if (!value) return;
		return [__(value, null, "Resident Request"), palette[value] || "gray", `status,=,${value}`];
	},
};
