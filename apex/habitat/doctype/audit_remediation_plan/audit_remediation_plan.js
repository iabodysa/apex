// Copyright (c) 2026, afmcoltd

const remediationTransitions = {
	Open: ["In Progress"],
	"In Progress": ["Evidence Submitted"],
	"Evidence Submitted": ["Verified by Client", "Rejected by Client"],
	"Rejected by Client": ["In Progress"],
	"Verified by Client": [],
};

frappe.ui.form.on("Audit Remediation Plan", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) {
			return;
		}
		frm.add_custom_button(__("Progress Selected Action"), () => {
			const selected = frm.fields_dict.remediation_items.grid.get_selected_children();
			if (selected.length !== 1) {
				frappe.msgprint(__("Select exactly one remediation action."));
				return;
			}

			const item = selected[0];
			const targets = remediationTransitions[item.status || "Open"] || [];
			if (!targets.length) {
				frappe.msgprint(__("The selected remediation action has no available transition."));
				return;
			}

			const dialog = new frappe.ui.Dialog({
				title: __("Progress Remediation Action"),
				fields: [
					{
						fieldname: "target_status",
						fieldtype: "Select",
						label: __("Next Status"),
						options: targets,
						reqd: 1,
					},
					{
						fieldname: "evidence_attached",
						fieldtype: "Attach",
						label: __("Evidence"),
						default: item.evidence_attached,
						depends_on: "eval:doc.target_status=='Evidence Submitted'",
						mandatory_depends_on: "eval:doc.target_status=='Evidence Submitted'",
					},
				],
				primary_action_label: __("Apply"),
				primary_action(values) {
					frappe.call({
						method:
							"apex.habitat.doctype.audit_remediation_plan.audit_remediation_plan.transition_item",
						args: {
							name: frm.doc.name,
							item_name: item.name,
							target_status: values.target_status,
							evidence_attached: values.evidence_attached,
						},
						freeze: true,
						callback: () => {
							dialog.hide();
							frm.reload_doc();
						},
					});
				},
			});
			dialog.show();
		});
	},
});
