// Client-side script for Accommodation Bed
frappe.ui.form.on("Accommodation Bed", {
	refresh(frm) {
		const colors = {
			"Available": "green",
			"Occupied": "red",
			"Out of Service": "grey",
		};
		const status = frm.doc.status;
		if (status) {
			frm.page.set_indicator(__(status), colors[status] || "blue");
		}
	},
});
