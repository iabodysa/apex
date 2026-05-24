// Client-side script for Maintenance Request
frappe.ui.form.on("Maintenance Request", {
	refresh(frm) {
		_update_priority_indicator(frm);

		if (frm.doc.docstatus === 1 && frm.doc.status === "Open") {
			frm.add_custom_button(__("Create Work Order"), function() {
				frappe.model.open_mapped_doc({
					method: "apex_habitat.habitat.doctype.maintenance_request.maintenance_request.make_work_order",
					frm: frm
				});
			}, __("Actions"));
		}

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
					},
					error: function() {
						frappe.show_alert({message: __("Could not load the material template. Please try again."), indicator: "red"});
					}
				});
			}, __("Actions"));
		}
	},
	priority(frm) {
		_update_priority_indicator(frm);
	}
});

function _update_priority_indicator(frm) {
	frm.page.clear_indicator();

	if (frm.doc.priority === "Critical") {
		frm.page.set_indicator(__("Critical"), "red");
	} else if (frm.doc.priority === "High") {
		frm.page.set_indicator(__("High Priority"), "orange");
	}

	if (
		frm.doc.sla_breach_date &&
		frappe.datetime.get_diff(frm.doc.sla_breach_date, frappe.datetime.now_datetime()) < 0 &&
		frm.doc.status === "Open"
	) {
		frm.dashboard.add_comment(
			__("SLA Breached — this request requires immediate attention."),
			"red",
			true
		);
	}
}
