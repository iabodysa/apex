// Copyright (c) 2026, afmcoltd
frappe.ui.form.on("Maintenance Work Order", {
	setup(frm) {
		frm.set_query("subcontractor_service_order", () => ({
			filters: {
				...(frm.doc.building ? { building: frm.doc.building } : {}),
			},
		}));
	},
	refresh(frm) {
		frm.clear_custom_buttons();
		if (frm.doc.docstatus === 0 && frm.doc.issue_type) {
			frm.add_custom_button(__("Load Material Template"), function() {
				frappe.call({
					method: "apex.habitat.doctype.maintenance_material_template.maintenance_material_template.load_template_into_doc",
					args: {
						doctype: frm.doctype,
						docname: frm.docname,
						issue_type: frm.doc.issue_type,
					},
					callback: function(r) {
						if (r.exc || !r.message) {
							return;
						}
						frm.reload_doc();
						let msg = r.message.rows_added
							? __("{0} material(s) loaded from template {1}", [r.message.rows_added, r.message.template])
							: __("No active template found for issue type: {0}", [frm.doc.issue_type]);
						frappe.show_alert({message: msg, indicator: r.message.rows_added ? "green" : "orange"});
					},
					error: function() {
						frappe.show_alert({message: __("Could not load the material template. Please try again."), indicator: "red"});
					}
				});
			});
		}

		if (frm.doc.status === "In Progress" && !frm.doc.completion_photo) {
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
								method: "apex.habitat.doctype.maintenance_work_order.maintenance_work_order.start_work",
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
								error: function () {
									frappe.show_alert({
										message: __("Could not update the Work Order. Please try again."),
										indicator: "red",
									});
								},
							});
						}
					);
				});
			}

			if (frm.doc.status === "In Progress") {
				frm.add_custom_button(__("Mark as Completed"), function () {
					let dialog = new frappe.ui.Dialog({
						title: __("Complete Work Order"),
						fields: [
							{
								fieldname: "actual_end_date",
								fieldtype: "Date",
								label: __("Actual End Date"),
								reqd: 1,
								default: frm.doc.actual_end_date || frappe.datetime.get_today(),
							},
							{
								fieldname: "completion_photo",
								fieldtype: "Attach",
								label: __("Completion Photo"),
								reqd: frm.doc.completion_photo ? 0 : 1,
								default: frm.doc.completion_photo,
							},
							{
								fieldname: "completion_notes",
								fieldtype: "Small Text",
								label: __("Completion Notes"),
								default: frm.doc.completion_notes,
							},
						],
						primary_action_label: __("Mark as Completed"),
						primary_action: function (values) {
							dialog.hide();
							frappe.call({
								method: "apex.habitat.doctype.maintenance_work_order.maintenance_work_order.mark_completed",
								args: {
									work_order: frm.doc.name,
									actual_end_date: values.actual_end_date,
									completion_photo: values.completion_photo,
									completion_notes: values.completion_notes,
								},
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
								error: function () {
									frappe.show_alert({
										message: __("Could not mark the Work Order as Completed. Please try again."),
										indicator: "red",
									});
								},
							});
						},
					});
					dialog.show();
				});
			}
		}
	}
});
