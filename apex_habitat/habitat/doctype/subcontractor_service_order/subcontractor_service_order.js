// Client-side script for Subcontractor Service Order
frappe.ui.form.on("Subcontractor Service Order", {
	refresh(frm) {
		if (frm.doc.docstatus === 1) {
			if (frm.doc.status === "Scheduled") {
				frm.add_custom_button(__("Start Work"), function () {
					frappe.confirm(
						__("Mark this Service Order as In Progress?"),
						function () {
							frappe.call({
								method: "apex_habitat.habitat.doctype.subcontractor_service_order.subcontractor_service_order.start_work",
								args: { service_order: frm.doc.name },
								freeze: true,
								freeze_message: __("Updating status..."),
								callback: function (r) {
									if (!r.exc) {
										frappe.show_alert({
											message: __("Service Order marked In Progress."),
											indicator: "blue",
										});
										frm.reload_doc();
									}
								},
							});
						}
					);
				}, __("Status"));
			}

			if (frm.doc.status === "In Progress") {
				frm.add_custom_button(__("Mark Missed"), function () {
					frappe.confirm(
						__("Mark this Service Order as Missed? This indicates the scheduled work was not completed on time."),
						function () {
							frappe.call({
								method: "apex_habitat.habitat.doctype.subcontractor_service_order.subcontractor_service_order.mark_missed",
								args: { service_order: frm.doc.name },
								freeze: true,
								freeze_message: __("Updating status..."),
								callback: function (r) {
									if (!r.exc) {
										frappe.show_alert({
											message: __("Service Order marked Missed."),
											indicator: "orange",
										});
										frm.reload_doc();
									}
								},
							});
						}
					);
				}, __("Status"));
			}
		}
	}
});
