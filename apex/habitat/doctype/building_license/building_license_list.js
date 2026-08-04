// Copyright (c) 2026, AFMCO and contributors

frappe.listview_settings["Building License"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const palette = {
			"Active": "green",
			"Expiring Soon": "yellow",
			"Expired": "red",
			"Under Renewal": "blue",
			"Revoked": "darkgrey",
		};
		const value = doc.status;
		if (!value) return;
		return [__(value, null, "Building License"), palette[value] || "gray", `status,=,${value}`];
	},
};
