// Copyright (c) 2026, afmcoltd

frappe.listview_settings["Movement Cost Transfer"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const colors = {
			"Draft": "gray",
			"Pending Approval": "orange",
			"Approved": "blue",
			"Posted (memo)": "green",
			"Rejected": "red",
			"Cancelled": "red",
		};
		return [__(doc.status), colors[doc.status] || "blue", "status,=," + doc.status];
	},
};
