// Client-side script for Maintenance Request
frappe.ui.form.on("Maintenance Request", {
	refresh(frm) {
		_update_priority_indicator(frm);
	},
	priority(frm) {
		_update_priority_indicator(frm);
	}
});

function _update_priority_indicator(frm) {
	// Remove existing custom indicators
	frm.page.clear_indicator();

	if (frm.doc.priority === "Critical") {
		frm.page.set_indicator(__("Critical"), "red");
	} else if (frm.doc.priority === "High") {
		frm.page.set_indicator(__("High Priority"), "orange");
	}

	// SLA breach warning — only when the field exists and is populated
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
