frappe.ui.form.on("Accommodation Lease", {
	refresh(frm) {
		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			frm.add_custom_button(__("Regenerate Payment Schedule"), () => {
				frappe.confirm(
					__("This will clear and rebuild the entire payment schedule. Continue?"),
					() => {
						frappe.call({
							method: "apex_habitat.habitat.doctype.accommodation_lease.accommodation_lease.regenerate_schedule",
							args: { name: frm.doc.name },
							callback(r) {
								frappe.show_alert({
									message: __("{0} payment rows generated.", [r.message]),
									indicator: "green",
								});
								frm.reload_doc();
							},
						});
					}
				);
			}, __("Actions"));
		}

		if (frm.doc.docstatus === 1 && frm.doc.status !== "Expired") {
			frm.add_custom_button(__("Generate Payment"), function() {
				// Get selected row or first unpaid row
				const schedule = frm.doc.payment_schedule || [];
				const selected = schedule.find(r => r.__checked) || schedule.find(r => !r.paid);
				if (!selected) {
					frappe.msgprint({
						message: __("Select a row from the Rent Payment Schedule to generate a payment."),
						indicator: "orange"
					});
					return;
				}

				frappe.db.get_single_value("Habitat Settings", "default_payment_method").then(method => {
					if (method === "Expense Request Afmco") {
						frappe.db.exists("DocType", "Expense Request Afmco").then(exists => {
							if (!exists) {
								frappe.msgprint({message: __("Expense Request Afmco DocType is not installed."), indicator: "red"});
								return;
							}
							const doc = frappe.model.get_new_doc("Expense Request Afmco");
							doc.tax_invoice_number = frm.doc.name;
							doc.beneficiary_name = frm.doc.supplier;
							doc.amount = selected.amount || frm.doc.rent_amount;
							doc.project = frm.doc.project || "";
							doc.cost_center = frm.doc.cost_center || "";
							doc.jv_status = "JV Not Created";
							doc.naming_series = "PR-.YYYY.-";
							doc.date = frappe.datetime.nowdate();
							doc.bank_payment_date = frappe.datetime.nowdate();
							doc.payment_type = "Rent";
							doc.remark = __("Rent payment generated for building: {0} under lease {1}", [frm.doc.building, frm.doc.name]);
							frappe.set_route("Form", "Expense Request Afmco", doc.name);
						});
					} else if (method === "Payment Order") {
						const doc = frappe.model.get_new_doc("Payment Order");
						doc.payment_order_date = frappe.datetime.nowdate();
						doc.company = frm.doc.company;
						const ref = frappe.model.add_child(doc, "references");
						ref.reference_doctype = "Accommodation Lease";
						ref.reference_name = frm.doc.name;
						ref.amount = selected.amount || frm.doc.rent_amount;
						ref.supplier = frm.doc.supplier;
						frappe.set_route("Form", "Payment Order", doc.name);
					} else {
						// Default: Payment Entry
						const doc = frappe.model.get_new_doc("Payment Entry");
						doc.payment_type = "Pay";
						doc.party_type = "Supplier";
						doc.party = frm.doc.supplier;
						doc.paid_amount = selected.amount || frm.doc.rent_amount;
						doc.received_amount = selected.amount || frm.doc.rent_amount;
						doc.reference_no = frm.doc.name;
						doc.reference_date = frappe.datetime.nowdate();
						doc.remarks = __("Lease payment reference: {0}", [frm.doc.name]);
						frappe.set_route("Form", "Payment Entry", doc.name);
					}
				});
			}, __("Actions"));
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
