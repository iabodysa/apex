// Copyright (c) 2026, AFMCO and contributors
// Decision: option (b) adopted — company populated via frappe.defaults.get_global_default
// on onload for new documents. Rationale: better UX; the validate()-time fallback in
// accommodation_lease.py remains as a safety net for programmatic document creation.
frappe.ui.form.on("Lease", {
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
				// [#37puzh] Pick an OUTSTANDING (non-Paid) row: a manually checked
				// row only if it is still unpaid, else the first non-Paid due row.
				// Never re-pay a row already marked Paid.
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

				// The target payment DocType comes from the Payment Routing Settings
				// router (replacing the retired Apex Settings default_payment_method).
				// An unconfigured router answers "Payment Request"; this lease button
				// has no Payment Request branch, so it keeps its prior default of
				// Payment Entry in that case.
				frappe.call({
					method: "apex.apex_core.payment_router.get_target_payment_doctype",
				}).then(r => {
					const method = r && r.message;
					if (method === "Expense Request Afmco") {
						frappe.db.exists("DocType", "Expense Request Afmco").then(exists => {
							if (!exists) {
								frappe.msgprint({message: __("Expense Request Afmco DocType is not installed."), indicator: "red"});
								return;
							}
							// [#ofbr6f]
							frappe.db.get_value("Building", frm.doc.building, "default_cost_center").then(res => {
								const doc = frappe.model.get_new_doc("Expense Request Afmco");
								doc.tax_invoice_number = frm.doc.name;
								doc.beneficiary_name = frm.doc.landlord;
								doc.amount = selected.amount || frm.doc.rent_amount;
								doc.project = "";
								doc.cost_center = (res && res.message && res.message.default_cost_center) || "";
								doc.jv_status = "JV Not Created";
								doc.naming_series = "PR-.YYYY.-";
								doc.date = frappe.datetime.nowdate();
								doc.bank_payment_date = frappe.datetime.nowdate();
								doc.payment_type = "Rent";
								doc.remark = __("Rent payment generated for building: {0} under lease {1}", [frm.doc.building, frm.doc.name]);
								frappe.set_route("Form", "Expense Request Afmco", doc.name);
							});
						}).catch(() => {
							frappe.msgprint({message: __("Could not verify the Expense Request Afmco DocType. Please try again."), indicator: "red"});
						});
					} else if (method === "Payment Order") {
						const doc = frappe.model.get_new_doc("Payment Order");
						doc.payment_order_date = frappe.datetime.nowdate();
						doc.company = frm.doc.company;
						const ref = frappe.model.add_child(doc, "references");
						ref.reference_doctype = "Lease";
						ref.reference_name = frm.doc.name;
						ref.amount = selected.amount || frm.doc.rent_amount;
						ref.supplier = frm.doc.landlord;
						frappe.set_route("Form", "Payment Order", doc.name);
					} else {
						// [#mrbtun] A Payment Entry is raised SERVER-side from the landlord's
						// invoice, never built here from the rent schedule: a browser-built one
						// carried no references row, so it settled no invoice at all.
						raise_rent_payment(frm, selected);
					}
				}).catch(() => {
					frappe.msgprint({message: __("Could not read the payment settings. Please try again."), indicator: "red"});
				});
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

// A rent payment needs a payable behind it. With no submitted landlord invoice
// outstanding there is nothing to allocate against, so the dialog never opens and the
// operator is told what finance must raise first — instead of being handed a payment
// that looks like the rent and settles nothing. The server repeats every check.
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

// The settlement line is READ from the live Payment Entry each time the instalment
// changes — derived server-side, never stored — so a payment cancelled in Accounts
// shows here as reversed without anything writing a status back onto the lease.
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
				`<span class="indicator-pill no-indicator-dot ${colour}">${__(status.settlement)}</span> ` +
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
