// Client-side script for Accommodation Building
frappe.ui.form.on("Accommodation Building", {
	refresh(frm) {
		const colors = {
			"Active": "green",
			"Inactive": "grey",
			"Under Renovation": "orange",
		};
		const status = frm.doc.status;
		if (status) {
			frm.page.set_indicator(__(status), colors[status] || "blue");
		}
	},
});
