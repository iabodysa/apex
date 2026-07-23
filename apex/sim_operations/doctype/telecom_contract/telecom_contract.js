// Copyright (c) 2026, AFMCO and contributors
// Guarded billing actions on a submitted Telecom Contract. Each button prompts
// for the billing period and calls a POST-only whitelisted server method that
// re-checks permission and state and returns the (existing or new) draft link.

frappe.ui.form.on('Telecom Contract', {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) {
			return;
		}
		frm.add_custom_button(
			__('Raise Purchase Request'),
			() => raise_billing_document(frm, 'create_purchase_request', __('Purchase Request')),
			__('Billing'),
		);
		frm.add_custom_button(
			__('Raise Payment Order'),
			() => raise_billing_document(frm, 'create_payment_order', __('Payment Order')),
			__('Billing'),
		);
	},
});

function current_period() {
	const d = frappe.datetime.now_date(true);
	return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

function raise_billing_document(frm, method, label) {
	frappe.prompt(
		[
			{
				fieldname: 'billing_period',
				label: __('Billing Period'),
				fieldtype: 'Data',
				reqd: 1,
				default: current_period(),
				description: __('One document is created per contract and billing period (e.g. 2026-07).'),
			},
		],
		(values) => {
			frappe.call({
				method: `apex.sim_operations.api.contract_billing.${method}`,
				args: { contract: frm.doc.name, billing_period: values.billing_period },
				freeze: true,
				freeze_message: __('Creating {0}…', [label]),
			}).then((r) => {
				if (r && r.message) {
					frappe.show_alert({
						message: __('Draft {0} ready: {1}', [label, r.message.document_name]),
						indicator: 'green',
					});
					frm.reload_doc();
				}
			});
		},
		__('Raise {0}', [label]),
		__('Create'),
	);
}
