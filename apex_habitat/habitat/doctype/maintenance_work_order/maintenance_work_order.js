// Client-side script for Maintenance Work Order
frappe.ui.form.on("Maintenance Work Order", {
	refresh(frm) {
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
