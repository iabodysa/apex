// Copyright (c) 2026, afmcoltd
frappe.ui.form.on("Lease", {
	setup(frm) {
		frm.set_query("building", () => ({
			filters: {
				...(frm.doc.company ? { company: frm.doc.company } : {}),
			},
		}));
	},
	onload(frm) {
		if (frm.is_new() && !frm.doc.company) {
			frm.set_value("company", frappe.defaults.get_global_default("company"));
		}
	},

	refresh(frm) {
		frm.clear_custom_buttons();
		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			frm.add_custom_button(__("Regenerate Payment Schedule"), () => {
				frappe.confirm(
					__("This will clear and rebuild the entire payment schedule. Continue?"),
					() => {
						frappe.call({
							method: "apex.habitat.doctype.lease.lease.regenerate_schedule",
							args: { name: frm.doc.name },
							callback(r) {
								if (r.exc) {
									return;
								}
								frappe.show_alert({
									message: __("{0} payment rows generated.", [r.message]),
									indicator: "green",
								});
								frm.reload_doc();
							},
							error() {
								frappe.show_alert({
									message: __("Could not regenerate the payment schedule. Please try again."),
									indicator: "red",
								});
							},
						});
					}
				);
			});
		}

		if (frm.doc.docstatus === 1 && frm.doc.status !== "Expired" && frm.doc.status !== "Terminated") {
			frm.add_custom_button(__("Generate Payment"), function() {
				const schedule = frm.doc.payment_schedule || [];
				const checked = schedule.find(r => r.__checked);
				const selected = (checked && checked.status !== "Paid")
					? checked
					: schedule.find(r => r.status !== "Paid");
				if (!selected) {
					frappe.msgprint({
						message: __("Select a row from the Rent Payment Schedule to generate a payment."),
						indicator: "orange"
					});
					return;
				}

				raise_rent_payment(frm, selected);
			});
		}
	},

	first_payment_date(frm) {
		_hint_schedule(frm);
	},

	billing_cycle(frm) {
		_hint_schedule(frm);
	},
});

function raise_rent_payment(frm, selected) {
	frappe.call({
		method: "apex.habitat.doctype.lease.lease_payment.list_rent_payables",
		args: { lease: frm.doc.name },
		freeze: true,
		freeze_message: __("Checking outstanding invoices…"),
	}).then((r) => {
		const invoices = (r && r.message) || [];
		if (!invoices.length) {
			frappe.msgprint({
				title: __("No Outstanding Invoice"),
				message: __(
					"There is no submitted Purchase Invoice outstanding for {0} under this company. Raise and submit the landlord invoice first — a payment with no invoice behind it settles nothing.",
					[frm.doc.landlord]
				),
				indicator: "orange",
			});
			return;
		}
		_rent_payment_dialog(frm, selected, invoices);
	});
}

function _render_rent_settlement(dialog, frm, due_date) {
	const $wrapper = dialog.fields_dict.settlement_html.$wrapper;
	if (!due_date) {
		$wrapper.empty();
		return;
	}
	frappe.call({
		method: "apex.habitat.doctype.lease.lease_payment.get_rent_payment_status",
		args: { lease: frm.doc.name, due_date: due_date },
	}).then((r) => {
		const status = r && r.message;
		if (!status) {
			$wrapper.empty();
			return;
		}
		const colour = { Settled: "green", "Payment Cancelled": "red" }[status.settlement] || "orange";
		const detail = status.payment_entry
			? `${frappe.utils.escape_html(status.payment_entry)} · ${format_currency(status.allocated_amount)}`
			: __("No payment raised for this instalment yet.");
		$wrapper.html(
			`<div class="text-muted" style="margin-block-end:8px;">` +
				`<span class="indicator-pill no-indicator-dot ${colour}">${frappe.utils.escape_html(
					__(status.settlement)
				)}</span> ` +
				`<span>${detail}</span></div>`
		);
	}).catch(() => $wrapper.empty());
}

function _rent_payment_dialog(frm, selected, invoices) {
	const due_dates = (frm.doc.payment_schedule || []).map((row) => row.due_date).filter(Boolean);
	const dialog = new frappe.ui.Dialog({
		title: __("Raise Rent Payment"),
		fields: [
			{
				fieldname: "due_date",
				label: __("Instalment Due Date"),
				fieldtype: "Select",
				reqd: 1,
				default: selected.due_date,
				options: due_dates.join("\n"),
				onchange: () => _render_rent_settlement(dialog, frm, dialog.get_value("due_date")),
			},
			{ fieldname: "settlement_html", fieldtype: "HTML" },
			{
				fieldname: "purchase_invoice",
				label: __("Purchase Invoice"),
				fieldtype: "Select",
				reqd: 1,
				default: invoices[0].name,
				options: invoices.map((inv) => inv.name).join("\n"),
				description: __("The submitted landlord invoice this payment settles."),
			},
			{ fieldname: "outstanding_html", fieldtype: "HTML", options: _rent_outstanding_table(invoices) },
		],
		primary_action_label: __("Create"),
		primary_action: (values) => {
			dialog.hide();
			frappe.call({
				method: "apex.habitat.doctype.lease.lease_payment.create_rent_payment",
				args: {
					lease: frm.doc.name,
					due_date: values.due_date,
					purchase_invoice: values.purchase_invoice,
				},
				freeze: true,
				freeze_message: __("Creating {0}…", [__("Payment Entry")]),
			}).then((r) => {
				if (r && r.message) {
					frappe.show_alert({
						message: __("Draft {0} ready: {1}", [__("Payment Entry"), r.message.document_name]),
						indicator: "green",
					});
					frappe.set_route("Form", "Payment Entry", r.message.document_name);
				}
			});
		},
	});
	dialog.show();
	_render_rent_settlement(dialog, frm, dialog.get_value("due_date"));
}

function _rent_outstanding_table(invoices) {
	const rows = invoices
		.map(
			(inv) =>
				`<tr><td>${frappe.utils.escape_html(inv.name)}</td>` +
				`<td>${frappe.utils.escape_html(inv.posting_date || "")}</td>` +
				`<td class="text-right">${format_currency(inv.outstanding_amount, inv.currency)}</td></tr>`
		)
		.join("");
	return (
		`<div style="overflow-x:auto;"><table class="table table-bordered" style="margin:0;"><thead><tr>` +
		`<th>${__("Invoice")}</th><th>${__("Date")}</th><th class="text-right">${__("Outstanding")}</th>` +
		`</tr></thead><tbody>${rows}</tbody></table></div>`
	);
}

function _hint_schedule(frm) {
	if (frm.is_new() && frm.doc.first_payment_date && frm.doc.billing_cycle) {
		frappe.show_alert({
			message: __("Payment schedule will be generated automatically on first save."),
			indicator: "blue",
		});
	}
}
