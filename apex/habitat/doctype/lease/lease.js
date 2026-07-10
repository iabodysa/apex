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
						// [#mrbtun]
						const doc = frappe.model.get_new_doc("Payment Entry");
						doc.payment_type = "Pay";
						doc.party_type = "Supplier";
						doc.party = frm.doc.landlord;
						doc.paid_amount = selected.amount || frm.doc.rent_amount;
						doc.received_amount = selected.amount || frm.doc.rent_amount;
						doc.reference_no = frm.doc.name;
						doc.reference_date = frappe.datetime.nowdate();
						doc.remarks = __("Lease payment reference: {0}", [frm.doc.name]);
						frappe.set_route("Form", "Payment Entry", doc.name);
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

function _hint_schedule(frm) {
	if (frm.is_new() && frm.doc.first_payment_date && frm.doc.billing_cycle) {
		frappe.show_alert({
			message: __("Payment schedule will be generated automatically on first save."),
			indicator: "blue",
		});
	}
}
