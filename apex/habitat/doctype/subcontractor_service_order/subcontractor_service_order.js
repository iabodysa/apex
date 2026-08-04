// Copyright (c) 2026, AFMCO and contributors
frappe.ui.form.on("Subcontractor Service Order", {
	setup(frm) {
		frm.set_query("building", () => ({
			filters: {
				...(frm.doc.company ? { company: frm.doc.company } : {}),
			},
		}));
		frm.set_query("linked_purchase_invoice", () => ({
			filters: {
				...(frm.doc.company ? { company: frm.doc.company } : {}),
				...(frm.doc.supplier ? { supplier: frm.doc.supplier } : {}),
			},
		}));
	},
	refresh(frm) {
		frm.clear_custom_buttons();
		if (frm.doc.docstatus === 1) {
			if (frm.doc.status === "Scheduled") {
				frm.add_custom_button(__("Start Work"), function () {
					frappe.confirm(
						__("Mark this Service Order as In Progress?"),
						function () {
							frappe.call({
								method: "apex.habitat.doctype.subcontractor_service_order.subcontractor_service_order.start_work",
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
								error: function () {
									frappe.show_alert({
										message: __("Could not update the Service Order. Please try again."),
										indicator: "red",
									});
								},
							});
						}
					);
				});
			}

			if (frm.doc.status === "In Progress") {
				frm.add_custom_button(__("Mark Completed"), function () {
					frappe.confirm(
						__("Mark this Service Order as Completed? Confirm the work was carried out."),
						function () {
							frappe.call({
								method: "apex.habitat.doctype.subcontractor_service_order.subcontractor_service_order.mark_completed",
								args: { service_order: frm.doc.name },
								freeze: true,
								freeze_message: __("Updating status..."),
								callback: function (r) {
									if (!r.exc) {
										frappe.show_alert({
											message: __("Service Order marked Completed."),
											indicator: "green",
										});
										frm.reload_doc();
									}
								},
								error: function () {
									frappe.show_alert({
										message: __("Could not update the Service Order. Please try again."),
										indicator: "red",
									});
								},
							});
						}
					);
				}).addClass("btn-primary");

				frm.add_custom_button(__("Mark Missed"), function () {
					frappe.confirm(
						__("Mark this Service Order as Missed? This indicates the scheduled work was not completed on time."),
						function () {
							frappe.call({
								method: "apex.habitat.doctype.subcontractor_service_order.subcontractor_service_order.mark_missed",
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
								error: function () {
									frappe.show_alert({
										message: __("Could not update the Service Order. Please try again."),
										indicator: "red",
									});
								},
							});
						}
					);
				});
			}
		}
	}
});
