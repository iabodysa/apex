// Copyright (c) 2026, AFMCO and contributors
// [#3liu9f]
frappe.ui.form.on("Accommodation Bed", {
	refresh(frm) {
		frm.clear_custom_buttons();
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
					error: function () {
						frappe.show_alert({
							message: __("Could not update the bed. Please try again."),
							indicator: "red",
						});
					},
				});
			});
		}
	},
});
