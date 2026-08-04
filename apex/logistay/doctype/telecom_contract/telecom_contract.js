// Copyright (c) 2026, AFMCO and contributors

frappe.ui.form.on('Telecom Contract', {
	setup(frm) {
		frm.set_query("cost_center", () => ({
			filters: {
				...(frm.doc.company ? { company: frm.doc.company } : {}),
			},
		}));
		frm.set_query("project", () => ({
			filters: {
				...(frm.doc.company ? { company: frm.doc.company } : {}),
			},
		}));
	},
	refresh(frm) {
		if (frm.doc.docstatus !== 1) {
			return;
		}
		frm.add_custom_button(
			__('Raise Purchase Request'),
			() => raise_billing_document(frm, 'create_purchase_request', __('Material Request')),
			__('Billing'),
		);
		frm.add_custom_button(
			__('Raise Payment Entry'),
			() => raise_payment_entry(frm),
			__('Billing'),
		);
	},
});

function current_period() {
	const d = frappe.datetime.now_date(true);
	return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

function period_field() {
	return {
		fieldname: 'billing_period',
		label: __('Billing Period'),
		fieldtype: 'Data',
		reqd: 1,
		default: current_period(),
		description: __('One document is created per contract and billing period (e.g. 2026-07).'),
	};
}

function raise_billing_document(frm, method, label) {
	frappe.prompt(
		[period_field()],
		(values) => {
			frappe.call({
				method: `apex.logistay.api.contract_billing.${method}`,
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

function raise_payment_entry(frm) {
	frappe.call({
		method: 'apex.logistay.api.contract_billing.list_payable_invoices',
		args: { contract: frm.doc.name },
		freeze: true,
		freeze_message: __('Checking outstanding invoices…'),
	}).then((r) => {
		const invoices = (r && r.message) || [];
		if (!invoices.length) {
			frappe.msgprint({
				title: __('No Outstanding Invoice'),
				message: __(
					'There is no submitted Purchase Invoice outstanding for {0} under this company. Raise and submit the supplier invoice first — a payment with no invoice behind it settles nothing.',
					[frm.doc.supplier],
				),
				indicator: 'orange',
			});
			return;
		}
		payment_dialog(frm, invoices);
	});
}

function render_settlement(dialog, frm, period) {
	const $wrapper = dialog.fields_dict.settlement_html.$wrapper;
	if (!period) {
		$wrapper.empty();
		return;
	}
	frappe
		.call({
			method: 'apex.logistay.api.contract_billing.get_billing_status',
			args: { contract: frm.doc.name, billing_period: period },
		})
		.then((r) => {
			const status = r && r.message;
			if (!status) {
				$wrapper.empty();
				return;
			}
			const colour = { Settled: 'green', 'Payment Cancelled': 'red' }[status.settlement] || 'orange';
			const detail = status.payment_entry
				? `${frappe.utils.escape_html(status.payment_entry)} · ${format_currency(status.allocated_amount)}`
				: __('No payment raised for this period yet.');
			$wrapper.html(
				`<div class="text-muted" style="margin-block-end:8px;">` +
					`<span class="indicator-pill no-indicator-dot ${colour}">${__(status.settlement)}</span> ` +
					`<span>${detail}</span></div>`,
			);
		})
		.catch(() => $wrapper.empty());
}

function payment_dialog(frm, invoices) {
	const period = period_field();
	period.onchange = () => render_settlement(dialog, frm, dialog.get_value('billing_period'));
	const dialog = new frappe.ui.Dialog({
		title: __('Raise Payment Entry'),
		fields: [
			period,
			{ fieldname: 'settlement_html', fieldtype: 'HTML' },
			{
				fieldname: 'purchase_invoice',
				label: __('Purchase Invoice'),
				fieldtype: 'Select',
				reqd: 1,
				default: invoices[0].name,
				options: invoices.map((inv) => inv.name).join('\n'),
				description: __('The submitted supplier invoice this payment settles.'),
			},
			{
				fieldname: 'outstanding_html',
				fieldtype: 'HTML',
				options: outstanding_table(invoices),
			},
		],
		primary_action_label: __('Create'),
		primary_action: (values) => {
			dialog.hide();
			frappe.call({
				method: 'apex.logistay.api.contract_billing.create_payment_entry',
				args: {
					contract: frm.doc.name,
					billing_period: values.billing_period,
					purchase_invoice: values.purchase_invoice,
				},
				freeze: true,
				freeze_message: __('Creating {0}…', [__('Payment Entry')]),
			}).then((r) => {
				if (r && r.message) {
					frappe.show_alert({
						message: __('Draft {0} ready: {1}', [__('Payment Entry'), r.message.document_name]),
						indicator: 'green',
					});
					frm.reload_doc();
				}
			});
		},
	});
	dialog.show();
	render_settlement(dialog, frm, dialog.get_value('billing_period'));
}

function outstanding_table(invoices) {
	const rows = invoices
		.map(
			(inv) =>
				`<tr><td>${frappe.utils.escape_html(inv.name)}</td>` +
				`<td>${frappe.utils.escape_html(inv.posting_date || '')}</td>` +
				`<td class="text-right">${format_currency(inv.outstanding_amount, inv.currency)}</td></tr>`,
		)
		.join('');
	return (
		`<div style="overflow-x:auto;"><table class="table table-bordered" style="margin:0;"><thead><tr>` +
		`<th>${__('Invoice')}</th><th>${__('Date')}</th><th class="text-right">${__('Outstanding')}</th>` +
		`</tr></thead><tbody>${rows}</tbody></table></div>`
	);
}
