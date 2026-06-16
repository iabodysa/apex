// [#3liu9f]
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

		if (!frm.is_new()) {
			const deactivated = frm.doc.status === "Out of Service";
			frm.add_custom_button(deactivated ? __("Activate Bed") : __("Deactivate Bed"), function () {
				frappe.call({
					method: "apex_habitat.habitat.doctype.accommodation_bed.accommodation_bed.toggle_service",
					args: { bed: frm.doc.name },
					freeze: true,
					callback: function (r) {
						if (!r.exc) frm.reload_doc();
					},
				});
			});
		}
	},
});
