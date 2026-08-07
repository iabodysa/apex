// Copyright (c) 2026, afmcoltd
frappe.ui.form.on("Room", {
	refresh(frm) {
		frm.clear_custom_buttons();
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

		if (!frm.is_new()) {
			const deactivated = frm.doc.readiness_status === "Out of Service";
			frm.add_custom_button(deactivated ? __("Activate Room") : __("Deactivate Room"), function () {
				frappe.call({
					method: "apex.habitat.doctype.room.room.toggle_service",
					args: { room: frm.doc.name },
					freeze: true,
					callback: function (r) {
						if (!r.exc) frm.reload_doc();
					},
					error: function () {
						frappe.show_alert({
							message: __("Could not update the room. Please try again."),
							indicator: "red",
						});
					},
				});
			});
		}
	},
});
