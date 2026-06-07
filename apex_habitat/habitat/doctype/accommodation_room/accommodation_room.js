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

		if (!frm.is_new()) {
			const deactivated = frm.doc.readiness_status === "Out of Service";
			frm.add_custom_button(deactivated ? __("Activate Room") : __("Deactivate Room"), function () {
				frappe.call({
					method: "apex_habitat.habitat.doctype.accommodation_room.accommodation_room.toggle_service",
					args: { room: frm.doc.name },
					freeze: true,
					callback: function (r) {
						if (!r.exc) frm.reload_doc();
					},
				});
			});
		}
	},
});
