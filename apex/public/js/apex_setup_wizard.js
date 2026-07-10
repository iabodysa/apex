// Copyright (c) 2026, AFMCO and contributors
// [#5runtp]
frappe.provide("apex.setup");

frappe.setup.on("before_load", function () {
	apex.setup.slides_settings.map(frappe.setup.add_slide);
});

// Three grouped Apex slides cover every re-engineered Single. Every field is
// skip-safe: leaving a Link blank or a toggle at its pre-filled value keeps the
// Single's own default (see apex_core/setup/setup_wizard.py). The fieldnames here
// are the wizard args the server reads on setup completion.
apex.setup.slides_settings = [
	{
		name: "apex_defaults",
		title: __("Apex — Company and Accounting Defaults"),
		icon: "fa fa-building",
		help: __(
			"Set the default company, cost center, and payment routing Apex uses for Habitat and Salis. You can change all of these later in Habitat Settings, Salis Settings, and Payment Routing Settings."
		),
		fields: [
			{
				fieldname: "apex_default_company",
				label: __("Default Company"),
				fieldtype: "Link",
				options: "Company",
				description: __("Default company for Habitat and Salis documents. Leave blank to set it per-module later."),
			},
			{
				fieldname: "apex_default_cost_center",
				label: __("Default Cost Center"),
				fieldtype: "Link",
				options: "Cost Center",
				description: __("Default cost center for Salis fleet cost postings. Leave blank to set it later."),
			},
			{ fieldname: "apex_gl_sb", fieldtype: "Section Break", label: __("Accounting") },
			{
				fieldname: "apex_post_gl",
				label: __("Post accommodation and fleet costs to the General Ledger?"),
				fieldtype: "Check",
				default: 0,
				description: __("Off by default — operational memo only, no GL entries until you enable it."),
			},
			{ fieldname: "apex_payment_sb", fieldtype: "Section Break", label: __("Payment Routing") },
			{
				fieldname: "apex_default_payment_method",
				label: __("Default Payment Method"),
				fieldtype: "Select",
				options: "Payment Entry\nPayment Order\nExpense Request Afmco",
				default: "Payment Entry",
				description: __("The payment document the Pay action builds (sets the Payment Routing target). Leave on the default to use Payment Entry."),
			},
		],
	},
	{
		name: "apex_operations",
		title: __("Apex — Notifications and Operations"),
		icon: "fa fa-bell",
		help: __(
			"Turn on email and operational notifications, the driver self-service portal, and approval routing. All of these can be changed later in Habitat Settings and Salis Settings."
		),
		fields: [
			{ fieldname: "apex_notify_sb", fieldtype: "Section Break", label: __("Notifications") },
			{
				fieldname: "apex_enable_email",
				label: __("Enable email notifications?"),
				fieldtype: "Check",
				default: 0,
				description: __("Off by default — turn on only after the site's outgoing email (SMTP) is configured."),
			},
			{
				fieldname: "apex_enable_operational_notifications",
				label: __("Enable operational notifications?"),
				fieldtype: "Check",
				default: 0,
				description: __("Off by default — post expiry and overdue reminders as timeline comments on the source document."),
			},
			{ fieldname: "apex_ops_sb", fieldtype: "Section Break", label: __("Fleet Operations") },
			{
				fieldname: "apex_enable_driver_portal",
				label: __("Enable the driver self-service portal?"),
				fieldtype: "Check",
				default: 0,
				description: __("Off by default — let drivers access the Salis self-service portal."),
			},
			{
				fieldname: "apex_enable_approvals",
				label: __("Enable approval routing for fleet transactions?"),
				fieldtype: "Check",
				default: 1,
				description: __("On by default — route Salis assignments, transfers, and fuel requests through approval gates."),
			},
		],
	},
	{
		name: "apex_deductions",
		title: __("Apex — Salary Deductions"),
		icon: "fa fa-money",
		help: __(
			"Salary deductions are OFF by default and require legal/HR review before activation. You can configure them later in the Salary Deduction Policy."
		),
		fields: [
			{ fieldname: "apex_deductions_sb", fieldtype: "Section Break", label: __("Salary Deductions") },
			{
				fieldname: "apex_deduct_housing_allowance",
				label: __("Deduct housing allowance from salary?"),
				fieldtype: "Check",
				default: 0,
				description: __("Off by default — no automatic housing-allowance deduction. Requires legal/HR review."),
			},
			{
				fieldname: "apex_deduct_damage",
				label: __("Post custody-damage deductions to salary?"),
				fieldtype: "Check",
				default: 0,
				description: __("Off by default. Requires legal/HR review."),
			},
		],
	},
];
