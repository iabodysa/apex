// Client-side script for Accommodation Room
frappe.ui.form.on("Accommodation Room", {
	refresh(frm) {
		const colors = {
			"Available": "green",
			"Partially Occupied": "orange",
			"Full": "red",
			"Under Maintenance": "grey",
		};
		const status = frm.doc.status;
		if (status) {
			frm.page.set_indicator(__(status), colors[status] || "blue");
		}
	},
});
