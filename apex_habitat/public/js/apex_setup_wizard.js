// [#5runtp]
frappe.provide("apex_habitat.setup");

frappe.setup.on("before_load", function () {
	apex_habitat.setup.slides_settings.map(frappe.setup.add_slide);
});

apex_habitat.setup.slides_settings = [
	{
		name: "apex_config",
		title: __("Apex — Accommodation and Fleet Setup"),
		icon: "fa fa-home",
		help: __(
			"Choose how Apex handles payments and salary deductions. You can change any of these later in Habitat Settings."
		),
		fields: [
			{
				fieldname: "apex_default_payment_method",
				label: __("Default Payment Method"),
				fieldtype: "Select",
				options: "Payment Entry\nPayment Order\nExpense Request Afmco",
				default: "Payment Entry",
				description: __("Which document accommodation payments link to."),
			},
			{ fieldname: "apex_deductions_sb", fieldtype: "Section Break", label: __("Salary Deductions") },
			{
				fieldname: "apex_deduct_housing_allowance",
				label: __("Deduct housing allowance from salary?"),
				fieldtype: "Check",
				default: 0,
				description: __("Off by default — no automatic housing-allowance deduction."),
			},
			{
				fieldname: "apex_deduct_damage",
				label: __("Post custody-damage deductions to salary?"),
				fieldtype: "Check",
				default: 0,
				description: __("Off by default."),
			},
			{ fieldname: "apex_gl_sb", fieldtype: "Section Break", label: __("Accounting") },
			{
				fieldname: "apex_post_gl",
				label: __("Post accommodation costs to the General Ledger?"),
				fieldtype: "Check",
				default: 0,
				description: __("Off by default — operational memo only, no GL entries until you enable it."),
			},
		],
	},
];
