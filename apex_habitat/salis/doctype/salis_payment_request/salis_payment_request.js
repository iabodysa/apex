// Client-side script for Salis Payment Request.
//
// Surfaces the Payment Router's "Create Payment" action. The button appears
// only on a finance-approved request that has not yet been routed to a payment
// document (linked_payment_entry empty). It calls the POST-only router endpoint,
// reloads, and routes to the created payment document.
frappe.ui.form.on("Salis Payment Request", {
	refresh(frm) {
		const finance_approved =
			!!frm.doc.finance_approved_by ||
			["Approved by Finance", "Paid"].includes(frm.doc.status);

		if (!finance_approved || frm.doc.linked_payment_entry) {
			return;
		}

		// Only/primary toolbar action -> render directly, no dropdown group.
		frm.add_custom_button(__("Create Payment"), function () {
			frappe.confirm(
				__("Create the payment document for this approved request?"),
				function () {
					frappe.call({
						method:
							"apex_habitat.apex_core.payment_router.create_routed_payment",
						args: { payment_request: frm.doc.name },
						freeze: true,
						freeze_message: __("Creating payment..."),
						callback: function (r) {
							if (r.exc || !r.message) {
								return;
							}
							const payment_name = r.message;
							frappe.show_alert({
								message: __("Payment {0} created.", [payment_name]),
								indicator: "green",
							});
							frm.reload_doc();
							// Resolve the configured target DocType to route there;
							// fall back to native Payment Request (the router's
							// default) when none is configured.
							frappe.db
								.get_single_value(
									"Payment Routing Settings",
									"target_payment_doctype"
								)
								.then(function (target_doctype) {
									frappe.set_route(
										"Form",
										target_doctype || "Payment Request",
										payment_name
									);
								});
						},
						error: function () {
							frappe.show_alert({
								message: __("Could not create the payment. Please try again."),
								indicator: "red",
							});
						},
					});
				}
			);
		});
	},
});
