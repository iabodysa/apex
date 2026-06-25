// [#khaxgw]

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
		this.$strip = $('<div class="fd-buildings"></div>').appendTo(this.page.main);
		this.$container = $('<div class="fd-board"></div>').appendTo(this.page.main);
		this._render_empty(__("Select a building to load the board."));
		this._setup_controls();
		this._load_buildings();
	}

	_setup_controls() {
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

	// Scope-aware chip strip from list_supervisor_buildings(): one chip per
	// allowed building, color-weighted by free-bed pressure. The chip is the
	// primary building selector (replaces the cold Link field).
	_load_buildings() {
		this.$strip.empty();
		const $loading = $('<div class="fd-buildings-loading text-muted"></div>')
			.text(__("Loading buildings…"))
			.appendTo(this.$strip);
		frappe.call({
			method: "apex_habitat.habitat.api.front_desk.list_supervisor_buildings",
			callback: (r) => {
				$loading.remove();
				if (r.exc) {
					this._render_strip_error();
					return;
				}
				this.buildings = r.message || [];
				this._render_buildings();
			},
			error: () => {
				$loading.remove();
				this._render_strip_error();
			},
		});
	}

	_render_strip_error() {
		this.$strip.empty();
		const $err = $('<div class="fd-buildings-error"></div>').appendTo(this.$strip);
		$('<span class="fd-buildings-error-msg"></span>')
			.text(__("Could not load your buildings."))
			.appendTo($err);
		$('<button class="btn btn-default btn-xs"></button>')
			.text(__("Retry"))
			.on("click", () => this._load_buildings())
			.appendTo($err);
	}

	// Free-bed-pressure color: red when full/over, amber when near-full, green
	// when beds are free. Derived client-side from the server counts; the bed
	// board's own colors stay server-computed.
	_building_pressure(b) {
		if ((b.available || 0) <= 0) return "red";
		if ((b.occupancy_pct || 0) >= 85) return "amber";
		return "green";
	}

	_render_buildings() {
		this.$strip.empty();
		if (!this.buildings || !this.buildings.length) {
			// Neutral placeholder; the permission-gap copy is owned elsewhere.
			$('<div class="fd-buildings-empty text-muted"></div>')
				.text(__("No buildings to show."))
				.appendTo(this.$strip);
			return;
		}
		const $row = $('<div class="fd-buildings-row"></div>').appendTo(this.$strip);
		this.buildings.forEach((b) => {
			const pressure = this._building_pressure(b);
			const is_selected = b.building === this.building;
			const selected = is_selected ? " fd-building-chip--selected" : "";
			const $chip = $(
				`<button class="fd-building-chip fd-building-chip--${pressure}${selected}" type="button"></button>`
			).appendTo($row);
			$chip.attr("aria-pressed", is_selected);
			$chip.attr("title", b.building_title || b.building);
			$('<span class="fd-building-chip-name"></span>')
				.text(b.building_title || b.building)
				.appendTo($chip);
			// LTR-isolate the fraction so it does not reverse beside Arabic names.
			$('<span class="fd-building-chip-counts" dir="ltr"></span>')
				.text(`${b.available || 0}/${b.total_beds || 0}`)
				.appendTo($chip);
			$chip.on("click", () => this._select_building(b.building));
		});
	}

	_select_building(building) {
		if (!building || building === this.building) return;
		this.building = building;
		this._render_buildings();
		this.refresh();
	}

	refresh() {
		if (!this.building) return;
		const requested = this.building;
		this._render_loading();
		frappe.call({
			method: "apex_habitat.habitat.api.front_desk.get_building_grid",
			args: { building: this.building },
			callback: (r) => {
				// [#ojympt]
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

		// [#pmav3l]
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

		this._render_open_requests_badge($summary, data.building);

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

				// [#mark-ready] Offer a one-tap "Mark Ready" only on not-ready rooms.
				const NOT_READY = ["Needs Cleaning", "Needs Repair", "Out of Service"];
				if (NOT_READY.includes(room.readiness_status)) {
					$('<button class="btn btn-xs btn-default fd-room-ready"></button>')
						.text(__("Mark Ready"))
						.on("click", () => this._mark_room_ready(room.room))
						.appendTo($rh);
				}

				const $beds = $('<div class="fd-beds"></div>').appendTo($room);
				(room.beds || []).forEach((bed) => {
					this._render_bed_card(bed, room, data.building).appendTo($beds);
				});
			});
		});
	}

	_render_open_requests_badge($summary, building) {
		// Async so the board paints without waiting; the badge clicks through to
		// the Resident Request list filtered to this building + open statuses
		// (statuses come from the server so the filter can't drift).
		const requested = building;
		frappe.call({
			method: "apex_habitat.habitat.api.front_desk.building_open_requests",
			args: { building: building },
			callback: (r) => {
				if (requested !== this.building || r.exc || !r.message) return;
				const count = r.message.open_requests || 0;
				const statuses = r.message.statuses || [];
				const indicator = count > 0 ? "fd-summary-requests--open" : "";
				$(`<span class="fd-summary-requests ${indicator}" role="button" tabindex="0"></span>`)
					.text(__("{0} open requests", [count]))
					.on("click keydown", (e) => {
						if (e.type === "keydown" && e.key !== "Enter" && e.key !== " ") return;
						e.preventDefault();
						frappe.set_route("List", "Accommodation Resident Request", {
							building: building,
							status: ["in", statuses],
						});
					})
					.appendTo($summary);
			},
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

	_mark_room_ready(room) {
		frappe.call({
			method: "apex_habitat.habitat.api.front_desk.set_room_readiness",
			args: { room: room, status: "Ready" },
			callback: (r) => {
				if (r.exc) return;
				frappe.show_alert({ message: __("Room marked ready."), indicator: "green" });
				this.refresh();
			},
		});
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
					fieldname: "scan",
					label: __("Scan Iqama / Worker Link"),
					fieldtype: "Data",
					description: __("Scan or type an Iqama number or personal link, then press Enter to identify the worker."),
					onchange: function () {
						const id = (this.get_value && this.get_value()) || "";
						if (!id.trim()) return;
						frappe.call({
							method: "apex_habitat.habitat.api.front_desk.resolve_worker",
							args: { identifier: id.trim() },
							callback: (r) => {
								const $status = d.fields_dict.scan_status.$wrapper;
								if (r.exc || !r.message) {
									$status.html(`<div class="text-muted">${__("Could not identify the worker.")}</div>`);
									return;
								}
								const m = r.message;
								if (!m.found) {
									$status.html(`<div class="text-muted">${frappe.utils.escape_html(m.message || __("No worker matched."))}</div>`);
									return;
								}
								// One-tap prefill: an Employee match fills the link (firing its
								// photo onchange); a Temporary Worker has no Employee link, so we
								// only surface the identity and route housing to Arrivals Desk.
								if (m.employee) {
									d.set_value("employee", m.employee);
								}
								const warn = m.has_active_assignment
									? `<div class="text-danger" style="margin-top:4px">${__("This worker already holds an active bed.")}</div>`
									: "";
								const tw = m.party_type === "Temporary Worker" && !m.employee
									? `<div class="text-muted" style="margin-top:4px">${__("Temporary Worker — use the Arrivals Desk to house this worker.")}</div>`
									: "";
								$status.html(
									`<div style="margin-top:4px"><b>${frappe.utils.escape_html(m.employee_name || m.party)}</b></div>${warn}${tw}`
								);
							},
						});
					},
				},
				{ fieldname: "scan_status", fieldtype: "HTML" },
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
						// [#rwp9u0]
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

		// [#rukrv3]
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
