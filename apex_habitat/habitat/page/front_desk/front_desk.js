// Front Desk — visual bed check-in board (v0.8.6).
//
// Standard Frappe page. No SPA / Vue / React / external libraries: built from
// frappe.ui.Page primitives + native frappe.ui.Dialog. All reads come from the
// single whitelisted reader get_building_grid (no N+1); all writes route through
// the existing Accommodation Assignment / Accommodation Checkout controllers via
// quick_check_in / quick_check_out. The server is the source of truth: after any
// write we re-fetch the grid rather than mutating the DOM optimistically.

frappe.pages["front-desk"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Front Desk"),
		single_column: true,
	});

	const fd = new FrontDesk(page);
	fd.setup();
};

class FrontDesk {
	constructor(page) {
		this.page = page;
		this.building = null;
	}

	setup() {
		this.$container = $('<div class="fd-board"></div>').appendTo(this.page.main);
		this._render_empty(__("Select a building to load the board."));
		this._setup_controls();
	}

	_setup_controls() {
		// Building selector in the page head.
		this.building_field = this.page.add_field({
			fieldname: "building",
			label: __("Building"),
			fieldtype: "Link",
			options: "Accommodation Building",
			change: () => {
				const val = this.building_field.get_value();
				if (val && val !== this.building) {
					this.building = val;
					this.refresh();
				} else if (!val && this.building) {
					// Field cleared — reset the board instead of leaving stale data.
					this.building = null;
					this._render_empty(__("Select a building to load the board."));
				}
			},
		});

		this.page.set_primary_action(__("Refresh Board"), () => {
			if (this.building) {
				this.refresh();
			} else {
				frappe.show_alert({
					message: __("Select a building to load the board."),
					indicator: "orange",
				});
			}
		}, "refresh");
	}

	refresh() {
		if (!this.building) return;
		const requested = this.building;
		this._render_loading();
		frappe.call({
			method: "apex_habitat.habitat.api.front_desk.get_building_grid",
			args: { building: this.building },
			callback: (r) => {
				// Ignore a stale response if the user switched buildings mid-flight.
				if (requested !== this.building) return;
				if (r.exc || !r.message) {
					this._render_error(__("Could not load the board for this building."));
					return;
				}
				this._render_grid(r.message);
			},
			error: () => {
				if (requested !== this.building) return;
				this._render_error(__("Could not load the board. Check your connection and try again."));
			},
		});
	}

	_render_empty(message) {
		this.$container.empty();
		$(`<div class="fd-empty text-muted"></div>`)
			.text(message)
			.appendTo(this.$container);
	}

	_render_loading() {
		this.$container.empty();
		const $wrap = $('<div class="fd-loading" aria-busy="true"></div>').appendTo(this.$container);
		$('<div class="fd-loading-label text-muted"></div>')
			.text(__("Loading board…"))
			.appendTo($wrap);
		const $skeleton = $('<div class="fd-skeleton-rooms"></div>').appendTo($wrap);
		for (let i = 0; i < 6; i++) {
			$('<div class="fd-skeleton-room"></div>').appendTo($skeleton);
		}
	}

	_render_error(message) {
		this.$container.empty();
		const $err = $('<div class="fd-error"></div>').appendTo(this.$container);
		$('<div class="fd-error-msg"></div>').text(message).appendTo($err);
		$('<button class="btn btn-default btn-sm"></button>')
			.text(__("Retry"))
			.on("click", () => this.refresh())
			.appendTo($err);
	}

	_render_grid(data) {
		this.$container.empty();

		// Summary line.
		const s = data.summary || {};
		const $summary = $('<div class="fd-summary"></div>').appendTo(this.$container);
		$summary.append(
			$('<span class="fd-summary-title"></span>').text(data.building_title || data.building)
		);
		$summary.append(
			$('<span class="fd-summary-counts"></span>').text(
				__("{0} of {1} beds available", [s.available || 0, s.total_beds || 0])
			)
		);

		if (!data.floors || !data.floors.length) {
			this._render_empty(__("No beds found for this building."));
			return;
		}

		data.floors.forEach((floor) => {
			const $floor = $('<div class="fd-floor"></div>').appendTo(this.$container);
			$('<div class="fd-floor-header"></div>')
				.text(floor.floor_label)
				.appendTo($floor);
			const $rooms = $('<div class="fd-rooms"></div>').appendTo($floor);

			(floor.rooms || []).forEach((room) => {
				const $room = $('<div class="fd-room"></div>').appendTo($rooms);
				const $rh = $('<div class="fd-room-header"></div>').appendTo($room);
				$('<span class="fd-room-number"></span>')
					.text(`${__("Room")} ${room.room_number || room.room}`)
					.appendTo($rh);
				$('<span class="fd-room-meta"></span>')
					.text(`${__(room.room_type || "")} · ${room.current_occupancy || 0}/${room.bed_capacity || 0}`)
					.appendTo($rh);

				const $beds = $('<div class="fd-beds"></div>').appendTo($room);
				(room.beds || []).forEach((bed) => {
					this._render_bed_card(bed, room, data.building).appendTo($beds);
				});
			});
		});
	}

	_render_bed_card(bed, room, building) {
		const $card = $(`<div class="fd-bed fd-bed--${bed.bed_color}" tabindex="0" role="button"></div>`);
		$('<div class="fd-bed-code"></div>').text(bed.bed_code || bed.bed).appendTo($card);

		let badge = "";
		if (bed.bed_color === "green") badge = __("Available");
		else if (bed.bed_color === "red") badge = __("Occupied");
		else if (bed.bed_color === "amber") badge = __("Room not ready");
		else badge = __("Out of Service");
		$('<div class="fd-bed-badge"></div>').text(badge).appendTo($card);

		if (bed.bed_color === "red" && bed.occupant) {
			$('<div class="fd-bed-occupant"></div>')
				.text(bed.occupant.employee_name || bed.occupant.employee)
				.appendTo($card);
		}

		const handler = () => this._on_bed_click(bed, room, building);
		$card.on("click", handler);
		$card.on("keydown", (e) => {
			if (e.key === "Enter" || e.key === " ") {
				e.preventDefault();
				handler();
			}
		});
		return $card;
	}

	_on_bed_click(bed, room, building) {
		switch (bed.bed_color) {
			case "green":
				this._open_check_in_dialog(bed, room, building);
				break;
			case "red":
				this._open_check_out_dialog(bed, room, building);
				break;
			case "amber":
				frappe.show_alert({
					message: __("This bed is in a room that is not ready. Resolve room readiness before check-in."),
					indicator: "orange",
				});
				break;
			default:
				frappe.show_alert({
					message: __("This bed is out of service and cannot be assigned."),
					indicator: "red",
				});
		}
	}

	_open_check_in_dialog(bed, room, building) {
		const context = `${building} · ${__("Room")} ${room.room_number || room.room} · ${bed.bed_code || bed.bed}`;
		const d = new frappe.ui.Dialog({
			title: __("Quick Check-in"),
			fields: [
				{
					fieldname: "context",
					fieldtype: "HTML",
					options: `<div class="text-muted" style="margin-bottom:8px">${frappe.utils.escape_html(context)}</div>`,
				},
				{
					fieldname: "employee",
					label: __("Employee"),
					fieldtype: "Link",
					options: "Employee",
					reqd: 1,
					onchange: function () {
						const emp = this.get_value && this.get_value();
						const photo = d.fields_dict.employee_photo;
						if (!emp) {
							photo.$wrapper.html("");
							return;
						}
						// Security: show the worker's HR photo to verify identity before assigning.
						frappe.call({
							method: "apex_habitat.habitat.api.front_desk.get_employee_card",
							args: { employee: emp },
							callback: (r) => {
								if (r.exc || !r.message) {
									photo.$wrapper.html(
										`<div class="text-muted">${__("Could not load employee photo.")}</div>`
									);
									return;
								}
								const img = r.message.image
									? `<img src="${frappe.utils.escape_html(r.message.image)}" style="width:84px;height:84px;object-fit:cover;border-radius:6px;border:1px solid var(--border-color)">`
									: `<div class="text-muted">${__("No photo on file")}</div>`;
								photo.$wrapper.html(
									`<div style="margin:6px 0">${img}<div><b>${frappe.utils.escape_html(r.message.employee_name || emp)}</b></div></div>`
								);
							},
						});
					},
				},
				{ fieldname: "employee_photo", fieldtype: "HTML" },
				{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project", reqd: 1 },
				{
					fieldname: "check_in_date",
					label: __("Check-in Date"),
					fieldtype: "Date",
					reqd: 1,
					default: frappe.datetime.get_today(),
				},
				{ fieldname: "cost_center", label: __("Cost Center"), fieldtype: "Link", options: "Cost Center" },
				{
					fieldname: "assignment_type",
					label: __("Assignment Type"),
					fieldtype: "Select",
					options: "New Assignment\nTransfer\nReturn from Leave",
					default: "New Assignment",
				},
				{
					fieldname: "room_condition_snapshot",
					label: __("Room Condition Snapshot"),
					fieldtype: "Attach Image",
				},
			],
			primary_action_label: __("Check In"),
			primary_action: (values) => {
				frappe.call({
					method: "apex_habitat.habitat.api.front_desk.quick_check_in",
					args: {
						bed: bed.bed,
						employee: values.employee,
						project: values.project,
						check_in_date: values.check_in_date,
						cost_center: values.cost_center || null,
						assignment_type: values.assignment_type || "New Assignment",
						room_condition_snapshot: values.room_condition_snapshot || null,
					},
					freeze: true,
					freeze_message: __("Checking in…"),
					callback: (r) => {
						if (r.exc || !r.message) return;
						d.hide();
						frappe.show_alert({
							message: __("Checked in: {0}", [r.message.assignment]),
							indicator: "green",
						});
						this.refresh();
					},
				});
			},
		});
		d.show();
	}

	_open_check_out_dialog(bed, room, building) {
		const occupant = bed.occupant || {};

		// Custody items present → no one-click; route to the full Checkout form
		// so the custody-clearance gate runs interactively.
		if (occupant.has_custody) {
			const d = new frappe.ui.Dialog({
				title: __("Quick Check-out"),
				fields: [
					{
						fieldname: "msg",
						fieldtype: "HTML",
						options: `<div>${__("This resident has custody items. Opening the full Checkout form to clear custody.")}</div>`,
					},
				],
				primary_action_label: __("Open Checkout Form"),
				primary_action: () => {
					d.hide();
					frappe.new_doc("Accommodation Checkout", { assignment: occupant.assignment });
				},
			});
			d.show();
			return;
		}

		const d = new frappe.ui.Dialog({
			title: __("Quick Check-out"),
			fields: [
				{
					fieldname: "context",
					fieldtype: "HTML",
					options: `<div class="text-muted" style="margin-bottom:8px">${frappe.utils.escape_html(occupant.employee_name || "")}</div>`,
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
				frappe.call({
					method: "apex_habitat.habitat.api.front_desk.quick_check_out",
					args: {
						bed: bed.bed,
						checkout_date: values.checkout_date,
						checkout_reason: values.checkout_reason,
						room_condition_snapshot: values.room_condition_snapshot || null,
					},
					freeze: true,
					freeze_message: __("Checking out…"),
					callback: (r) => {
						if (r.exc || !r.message) return;
						if (r.message.requires_full_form) {
							d.hide();
							frappe.show_alert({
								message: __("This resident has custody items. Opening the full Checkout form to clear custody."),
								indicator: "orange",
							});
							frappe.new_doc("Accommodation Checkout", { assignment: r.message.assignment });
							return;
						}
						d.hide();
						frappe.show_alert({
							message: __("Checked out: {0}", [r.message.checkout]),
							indicator: "green",
						});
						this.refresh();
					},
				});
			},
		});
		d.show();
	}
}
