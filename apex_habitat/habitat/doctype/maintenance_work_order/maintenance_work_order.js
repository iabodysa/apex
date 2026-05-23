// Client-side script for Maintenance Work Order
frappe.ui.form.on("Maintenance Work Order", {
	refresh(frm) {
		// Load material template button
		if (frm.doc.docstatus === 0 && frm.doc.issue_type) {
			frm.add_custom_button(__("Load Material Template"), function() {
				frappe.call({
					method: "apex_habitat.habitat.doctype.maintenance_material_template.maintenance_material_template.load_template_into_doc",
					args: {
						doctype: frm.doctype,
						docname: frm.docname,
						issue_type: frm.doc.issue_type,
					},
					callback: function(r) {
						if (r.message) {
							frm.reload_doc();
							let msg = r.message.rows_added
								? __("{0} material(s) loaded from template {1}", [r.message.rows_added, r.message.template])
								: __("No active template found for issue type: {0}", [frm.doc.issue_type]);
							frappe.show_alert({message: msg, indicator: r.message.rows_added ? "green" : "orange"});
						}
					}
				});
			}, __("Actions"));
		}

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
