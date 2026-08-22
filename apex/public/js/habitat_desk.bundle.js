// Copyright (c) 2026, afmcoltd
frappe.provide("apex.habitat");

/**
 * Map a bed colour to the framework's own indicator name.
 *
 * The desk pages that paint beds hold no copy of this table, so recolouring a bed state
 * is one edit and cannot drift between them.
 */
apex.habitat.indicator_color = function (bed_color) {
	return { green: "green", red: "red", amber: "orange", grey: "gray" }[bed_color] || "gray";
};

/**
 * The class list for one bed card, from its colour.
 *
 * The colours themselves live in habitat_desk.bundle.css; an unknown colour falls back to
 * the base class alone, which paints a neutral card rather than nothing.
 */
apex.habitat.bed_class = function (bed_color) {
	const known = ["green", "red", "amber", "grey"].includes(bed_color);
	return known ? `apex-bed apex-bed--${bed_color}` : "apex-bed";
};

/**
 * Open the quick check-out dialog for one bed and post the checkout.
 *
 * Written out in full on both desks, so one change landed on only one of them. on_busy
 * is the one thing the copies did differently.
 */
apex.habitat.custody_block_dialog = function (assignment) {
	const d = new frappe.ui.Dialog({
		title: __("Quick Check-out"),
		fields: [
			{
				fieldname: "msg",
				fieldtype: "HTML",
				options: `<div>${__(
					"This resident has custody items. Opening the full Checkout form to clear custody."
				)}</div>`,
			},
		],
		primary_action_label: __("Open Checkout Form"),
		primary_action: () => {
			d.hide();
			frappe.new_doc("Housing Checkout", { assignment: assignment });
		},
	});
	d.show();
	return d;
};

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
