// Copyright (c) 2026, AFMCO and contributors

frappe.listview_settings["Camera Access Grant"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const palette = {
			"Pending Approval": "orange",
			"Approved": "blue",
			"Active": "green",
			"Expired": "gray",
			"Revoked": "red",
		};
		const value = doc.status;
		if (!value) return;
		return [__(value, null, "Camera Access Grant"), palette[value] || "gray", `status,=,${value}`];
	},
};
