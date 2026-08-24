// Copyright (c) 2026, afmcoltd
frappe.provide("apex.habitat");

apex.habitat.indicator_color = function (bed_color) {
	return { green: "green", red: "red", amber: "orange", grey: "gray" }[bed_color] || "gray";
};

apex.habitat.bed_class = function (bed_color) {
	const known = ["green", "red", "amber", "grey"].includes(bed_color);
	return known ? `apex-bed apex-bed--${bed_color}` : "apex-bed";
};

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
