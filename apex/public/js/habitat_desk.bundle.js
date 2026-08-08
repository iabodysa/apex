// Copyright (c) 2026, afmcoltd
frappe.provide("apex.habitat");

apex.habitat.BED_PALETTE = {
	green: "background:var(--green-100);border-color:var(--green-500);color:var(--green-700);",
	red: "background:var(--red-100);border-color:var(--red-500);color:var(--red-700);",
	amber: "background:var(--yellow-100);border-color:var(--orange-500);color:var(--orange-700);cursor:not-allowed;",
	grey: "background:var(--gray-100);border-color:var(--gray-400);color:var(--gray-600);cursor:not-allowed;",
};

/**
 * Map a bed colour to the framework's own indicator name.
 *
 * Three desk pages painted beds from their own copy of this table, two of them
 * byte-identical, so recolouring a bed state cost three edits and could drift.
 */
apex.habitat.indicator_color = function (bed_color) {
	return { green: "green", red: "red", amber: "orange", grey: "gray" }[bed_color] || "gray";
};

/**
 * The style attribute for one bed card, from its colour and the page's own base style.
 */
apex.habitat.bed_style = function (bed_color, base) {
	return (base || "") + (apex.habitat.BED_PALETTE[bed_color] || "");
};

/**
 * Open the quick check-out dialog for one bed and post the checkout.
 *
 * Written out in full on both the front desk and the arrivals desk, so one change to
 * what a checkout asks for landed on only one of them. The caller keeps its own busy
 * state through on_busy, which is the only thing the two copies did differently.
 */
apex.habitat.quick_checkout_dialog = function (occupant, on_busy, on_done) {
	const busy = (state) => {
		if (on_busy) {
			on_busy(state);
		}
	};
	const d = new frappe.ui.Dialog({
		title: __("Quick Check-out"),
		fields: [
			{
				fieldname: "context",
				fieldtype: "HTML",
				options: `<div class="text-muted" style="margin-bottom:8px">${frappe.utils.escape_html(
					occupant.employee_name || ""
				)}</div>`,
			},
			{
				fieldname: "checkout_date",
				label: __("Check-out Date"),
				fieldtype: "Date",
				reqd: 1,
				default: frappe.datetime.get_today(),
			},
			{
				fieldname: "checkout_reason",
				label: __("Check-out Reason"),
				fieldtype: "Select",
				reqd: 1,
				options: "\nFinal Exit\nInternal Transfer\nProject Transfer\nAbsconding\nEnd of Contract",
			},
			{
				fieldname: "room_condition_snapshot",
				label: __("Room Condition Snapshot"),
				fieldtype: "Attach Image",
			},
		],
		primary_action_label: __("Check Out"),
		primary_action: (values) => {
			d.hide();
			busy(true);
			frappe.call({
				method: "apex.habitat.api.front_desk.quick_check_out",
				args: {
					bed: occupant.bed,
					checkout_date: values.checkout_date,
					checkout_reason: values.checkout_reason,
					room_condition_snapshot: values.room_condition_snapshot || null,
				},
				callback: (r) => {
					if (r.exc || !r.message) {
						busy(false);
						return;
					}
					if (r.message.requires_full_form) {
						busy(false);
						frappe.show_alert({
							message: __(
								"This resident has custody items. Opening the full Checkout form to clear custody."
							),
							indicator: "orange",
						});
						frappe.new_doc("Housing Checkout", { assignment: r.message.assignment });
						return;
					}
					frappe.show_alert({
						message: __("Checked out: {0}", [r.message.checkout]),
						indicator: "green",
					});
					if (on_done) {
						on_done(r.message);
					}
				},
				error: () => busy(false),
			});
		},
	});
	d.show();
	return d;
};
