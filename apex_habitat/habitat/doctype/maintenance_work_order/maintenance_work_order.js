// Client-side script for Maintenance Work Order
frappe.ui.form.on("Maintenance Work Order", {
	refresh(frm) {
		// Show orange banner if status is Completed/Closed but no photo attached
		if (
			(frm.doc.status === "Completed" || frm.doc.status === "Closed") &&
			!frm.doc.completion_photo
		) {
			frm.dashboard.add_comment(
				__("Completion photo required to close this work order."),
				"orange",
				true
			);
		}

		if (frm.doc.docstatus === 1) {
			if (frm.doc.status === "Planned") {
				frm.add_custom_button(__("Start Work"), function () {
					frappe.confirm(
						__("Mark this Work Order as In Progress?"),
						function () {
							frappe.call({
								method: "apex_habitat.habitat.doctype.maintenance_work_order.maintenance_work_order.start_work",
								args: { work_order: frm.doc.name },
								freeze: true,
								freeze_message: __("Updating status..."),
								callback: function (r) {
									if (!r.exc) {
										frappe.show_alert({
											message: __("Work Order marked In Progress."),
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

			if (frm.doc.status !== "Completed" && frm.doc.status !== "Cancelled") {
				frm.add_custom_button(__("Mark as Completed"), function () {
					if (!frm.doc.completion_photo) {
						frappe.msgprint(__("Please attach a completion photo before marking as completed."));
						return;
					}
					frappe.confirm(
						__("Mark this Work Order as Completed? This will post an operational ledger row."),
						function () {
							frappe.call({
								method: "apex_habitat.habitat.doctype.maintenance_work_order.maintenance_work_order.mark_completed",
								args: { work_order: frm.doc.name },
								freeze: true,
								freeze_message: __("Marking Completed..."),
								callback: function (r) {
									if (!r.exc) {
										frappe.show_alert({
											message: __("Work Order marked Completed."),
											indicator: "green",
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
