// Copyright (c) 2026, afmcoltd

frappe.listview_settings["Housing Checkout"] = {
	add_fields: ["checkout_reason"],
	get_indicator(doc) {
		const palette = {
			"Final Exit": "darkgrey",
			"Internal Transfer": "blue",
			"Project Transfer": "cyan",
			"Absconding": "red",
			"End of Contract": "orange",
		};
		const value = doc.checkout_reason;
		if (!value) return;
		return [__(value, null, "Housing Checkout"), palette[value] || "gray", `checkout_reason,=,${value}`];
	},
};
