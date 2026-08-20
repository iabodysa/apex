// Copyright (c) 2026, afmcoltd
frappe.provide("apex.setup");

frappe.setup.on("before_load", function () {
	apex.setup.slides_settings.map(frappe.setup.add_slide);
});

apex.setup.slides_settings = [
	{
		name: "apex_defaults",
		title: __("Apex — Accounting and Payment Defaults"),
		icon: "fa fa-building",
		help: __(
			"Apex takes its default company and cost center from the company this wizard creates. Set how it posts costs and which document the Pay action builds. You can change all of these later in Habitat Settings, Salis Settings, and Payment Routing Settings."
		),
		fields: [
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
				fieldtype: "Link",
				options: "DocType",
				get_query: () => ({ filters: { issingle: 0, istable: 0 } }),
				description: __("The payment document the Pay action builds (sets the Payment Routing target). Leave blank to use the native Payment Request."),
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
		name: "apex_recovery_support",
		title: __("Apex — Recovery and Support"),
		icon: "fa fa-money",
		help: __(
			"Employee Advance recovery and the Salis support SLA are off by default. Enable them only after Payroll, Accounts, and Support have supplied the native records and schedule below."
		),
		fields: [
			{
				fieldname: "apex_recovery_sb",
				fieldtype: "Section Break",
				label: __("Employee Advance Recovery"),
			},
			{
				fieldname: "apex_enable_employee_advance_recovery",
				label: __("Enable Employee Advance recovery?"),
				fieldtype: "Check",
				default: 0,
				description: __("Off by default — schedules draft HRMS Additional Salary installments only after native accounts and payroll are configured."),
			},
			{
				fieldname: "apex_employee_advance_recovery_component",
				label: __("Recovery Salary Component"),
				fieldtype: "Link",
				options: "Salary Component",
				// `after_install` seeds this component disabled, so the picker always has an
				// answer and nobody has to create a record from inside the wizard. `only_select`
				// removes the "Create a new" affordance, which loses wizard state when taken.
				default: "Employee Advance Recovery",
				only_select: 1,
				get_query: () => ({ filters: { type: "Deduction" } }),
				description: __("Native HRMS Deduction component used for Employee Advance installments."),
			},
			{
				fieldname: "apex_employee_advance_recovery_max_percent",
				label: __("Maximum Recovery Percent"),
				fieldtype: "Percent",
				default: 50,
				description: __("Per-installment scheduling limit. It cannot exceed 50% of actual pay-period gross pay from the native Salary Slip preview."),
			},
			{
				fieldname: "apex_support_sb",
				fieldtype: "Section Break",
				label: __("Salis Support SLA"),
			},
			{
				fieldname: "apex_enable_salis_support_sla",
				label: __("Enable the Salis support SLA?"),
				fieldtype: "Check",
				default: 0,
				description: __("Off by default — creates the native ERPNext Issue SLA only with a complete operating schedule."),
			},
			{
				fieldname: "apex_salis_support_holiday_list",
				label: __("Support Holiday List Name"),
				fieldtype: "Data",
				description: __("Name for the native ERPNext Holiday List created during setup."),
			},
			{
				fieldname: "apex_salis_support_holiday_from_date",
				label: __("Holiday Calendar From Date"),
				fieldtype: "Date",
			},
			{
				fieldname: "apex_salis_support_holiday_to_date",
				label: __("Holiday Calendar To Date"),
				fieldtype: "Date",
			},
			{
				fieldname: "apex_salis_support_weekly_off",
				label: __("Weekly Off"),
				fieldtype: "Select",
				options: "\nSunday\nMonday\nTuesday\nWednesday\nThursday\nFriday\nSaturday",
			},
			{
				fieldname: "apex_salis_support_country",
				label: __("Holiday Country Code"),
				fieldtype: "Data",
				description: __("Optional ISO country code used by ERPNext's native local-holiday generator."),
			},
			{
				fieldname: "apex_salis_support_subdivision",
				label: __("Holiday Subdivision Code"),
				fieldtype: "Data",
				description: __("Optional subdivision code for the selected country."),
			},
			{
				fieldname: "apex_salis_support_workdays",
				label: __("Support Workdays"),
				fieldtype: "MultiCheck",
				columns: 4,
				options: [
					"Sunday",
					"Monday",
					"Tuesday",
					"Wednesday",
					"Thursday",
					"Friday",
					"Saturday",
				].map((day) => ({ label: __(day), value: day })),
			},
			{ fieldname: "apex_support_time_col", fieldtype: "Column Break" },
			{
				fieldname: "apex_salis_support_start_time",
				label: __("Support Start Time"),
				fieldtype: "Time",
			},
			{
				fieldname: "apex_salis_support_end_time",
				label: __("Support End Time"),
				fieldtype: "Time",
			},
			{ fieldname: "apex_demo_sb", fieldtype: "Section Break", label: __("Demo Data") },
			{
				fieldname: "apex_setup_demo",
				label: __("Create demo data to explore Apex?"),
				fieldtype: "Check",
				default: 0,
				description: __(
					"Off by default — builds one sample accommodation site with rooms, beds, a resident and an open maintenance request. You can remove all of it later from Apex Settings."
				),
			},
		],
	},
];
