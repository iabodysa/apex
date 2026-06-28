// Copyright (c) 2026, AFMCO and contributors
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

// Persists the last building a multi-building user opened, so the board reopens
// where they left off instead of cold.
const LAST_BUILDING_KEY = "fd:last-building";

// Locale-consistent digit grouping via the framework formatter — never
// hand-concatenate a raw number. format_number (not the Int formatter, which
// skips grouping) applies the system number format; precision 0 keeps it whole.
function fd_int(n) {
	return format_number(cint(n), null, 0);
}

// A "used/total" bed fraction, each side locale-formatted; the caller wraps it in
// an LTR/bdi isolate so it does not reverse beside Arabic text.
function fd_fraction(used, total) {
	return `${fd_int(used)}/${fd_int(total)}`;
}

// A whole-number percent rendered with the locale's grouping + an isolated sign.
function fd_percent(pct) {
	return `${fd_int(pct)}%`;
}

class FrontDesk {
	constructor(page) {
		this.page = page;
		this.building = null;
		// Client-side board filters toggled from the legend (no server round-trip).
		this.filters = {
			only_available: false,
			hide_out_of_service: false,
			only_needs_readiness: false,
		};
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
		let permission_denied = false;
		frappe.call({
			method: "apex_habitat.habitat.api.front_desk.list_supervisor_buildings",
			error_handlers: {
				// A role without the building read grant is refused at the gate;
				// surface the permission-gap copy, not a generic failure or retry.
				PermissionError: () => {
					permission_denied = true;
					$loading.remove();
					frappe.hide_msgprint();
					this._render_strip_permission_gap();
				},
			},
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
				if (permission_denied) return;
				$loading.remove();
				this._render_strip_error();
			},
		});
	}

	_render_strip_error() {
		this.$strip.empty();
		const $err = $('<div class="fd-buildings-error"></div>').appendTo(this.$strip);
		$('<span class="fd-buildings-error-msg"></span>')
			.text(__("Could not load your buildings. Check your connection and try again."))
			.appendTo($err);
		$('<button class="btn btn-default btn-xs"></button>')
			.text(__("Retry"))
			.on("click", () => this._load_buildings())
			.appendTo($err);
	}

	// Distinct from a connection error: the caller is allowed to use the desk but
	// has no building assigned, so retry won't help — point them at an admin.
	_render_strip_permission_gap() {
		this.$strip.empty();
		$('<div class="fd-buildings-empty text-muted"></div>')
			.text(__("You don't have any building assigned. Ask an administrator to grant you a building."))
			.appendTo(this.$strip);
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
			this._render_buildings_empty();
			return;
		}
		const $row = $('<div class="fd-buildings-row"></div>').appendTo(this.$strip);
		this.buildings.forEach((b) => {
			this._render_building_chip($row, b);
		});
		this._auto_select_building();
	}

	// Land the operator straight on a loaded board with no Link interaction: a
	// single allowed building (or the server's auto hint) opens immediately; a
	// multi-building user reopens their last board if it is still in scope.
	_auto_select_building() {
		if (this.building) return;
		const only = this.buildings.length === 1 || this.buildings.some((b) => b.auto);
		if (only) {
			const target = this.buildings.find((b) => b.auto) || this.buildings[0];
			this._select_building(target.building);
			return;
		}
		let last = null;
		try {
			last = localStorage.getItem(LAST_BUILDING_KEY);
		} catch (e) {
			last = null;
		}
		if (last && this.buildings.some((b) => b.building === last)) {
			this._select_building(last);
		}
	}

	_render_building_chip($row, b) {
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
		// bdi LTR-isolates the locale-grouped fraction so it cannot reverse beside
		// an Arabic building name.
		$('<bdi class="fd-building-chip-counts" dir="ltr"></bdi>')
			.text(fd_fraction(b.available, b.total_beds))
			.appendTo($chip);
		$chip.on("click", () => this._select_building(b.building));
	}

	// An empty building list has two meanings — a scoped supervisor with no
	// assigned building (a permission gap) vs no Active building existing at all.
	// The server tells them apart so the copy can be actionable, not generic.
	_render_buildings_empty() {
		this.$strip.empty();
		const $empty = $('<div class="fd-buildings-empty text-muted"></div>')
			.text(__("No buildings to show."))
			.appendTo(this.$strip);
		frappe.call({
			method: "apex_habitat.habitat.api.front_desk.get_buildings_scope_state",
			callback: (r) => {
				if (r.exc || !r.message) return;
				if (r.message.is_scoped && !r.message.active_buildings) {
					$empty.text(
						__("You don't have any building assigned. Ask an administrator to grant you a building.")
					);
				} else if (!r.message.active_buildings) {
					$empty.text(__("No active buildings exist yet."));
				}
			},
		});
	}

	_select_building(building) {
		if (!building || building === this.building) return;
		this.building = building;
		try {
			localStorage.setItem(LAST_BUILDING_KEY, building);
		} catch (e) {
			// Private-mode / storage-disabled: persistence is best-effort.
		}
		this._render_buildings();
		this.refresh();
	}

	refresh() {
		if (!this.building) return;
		const requested = this.building;
		this._render_loading();
		// Typed permission failure: PermissionError carries exc_type, so the
		// framework's per-request error_handlers hook is the reliable place to
		// surface it (the generic error: callback gets no xhr on a 403). A retry
		// won't help, so no Retry button — and we suppress the generic message.
		let permission_denied = false;
		frappe.call({
			method: "apex_habitat.habitat.api.front_desk.get_building_grid",
			args: { building: this.building },
			error_handlers: {
				PermissionError: () => {
					permission_denied = true;
					if (requested !== this.building) return;
					frappe.hide_msgprint();
					this._render_error(
						__("You don't have permission to view this building."),
						{ retry: false }
					);
				},
			},
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
				if (requested !== this.building || permission_denied) return;
				this._render_error(
					__("Could not load the board. Check your connection and try again.")
				);
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

	_render_error(message, opts) {
		const allow_retry = !opts || opts.retry !== false;
		this.$container.empty();
		const $err = $('<div class="fd-error"></div>').appendTo(this.$container);
		$('<div class="fd-error-msg"></div>').text(message).appendTo($err);
		if (allow_retry) {
			$('<button class="btn btn-default btn-sm"></button>')
				.text(__("Retry"))
				.on("click", () => this.refresh())
				.appendTo($err);
		}
	}

	_render_grid(data) {
		this.$container.empty();

		// [#pmav3l]
		this._render_summary_bar(data);

		this._render_legend();

		if (!data.floors || !data.floors.length) {
			this._render_empty(__("No beds found for this building."));
			return;
		}

		const NOT_READY = ["Needs Cleaning", "Needs Repair", "Out of Service"];
		data.floors.forEach((floor) => {
			const $floor = $('<div class="fd-floor"></div>').appendTo(this.$container);
			$('<div class="fd-floor-header"></div>')
				.text(floor.floor_label)
				.appendTo($floor);
			const $rooms = $('<div class="fd-rooms"></div>').appendTo($floor);

			(floor.rooms || []).forEach((room) => {
				const needs_readiness = NOT_READY.includes(room.readiness_status);
				const $room = $('<div class="fd-room"></div>')
					.attr("data-needs-readiness", needs_readiness ? "1" : "0")
					.appendTo($rooms);
				const $rh = $('<div class="fd-room-header"></div>').appendTo($room);
				// The room label keeps the word translatable but bdi-isolates the room
				// code so the alphanumeric code is not reversed in an RTL locale.
				const $rn = $('<span class="fd-room-number"></span>').appendTo($rh);
				$rn.append(document.createTextNode(`${__("Room")} `));
				$('<bdi dir="ltr"></bdi>').text(room.room_number || room.room).appendTo($rn);
				// Room type stays in document direction; the occupancy fraction is
				// LTR-isolated and locale-formatted.
				const $rm = $('<span class="fd-room-meta"></span>').appendTo($rh);
				const room_type = __(room.room_type || "");
				if (room_type) {
					$rm.append(document.createTextNode(`${room_type} · `));
				}
				$('<bdi dir="ltr"></bdi>')
					.text(fd_fraction(room.current_occupancy, room.bed_capacity))
					.appendTo($rm);

				// [#mark-ready] Offer a one-tap "Mark Ready" only on not-ready rooms.
				if (needs_readiness) {
					$('<button class="btn btn-xs btn-default fd-room-ready"></button>')
						.text(__("Mark Ready"))
						.on("click", () => this._mark_room_ready(room.room))
						.appendTo($rh);
				}

				const $beds = $('<div class="fd-beds"></div>').appendTo($room);
				(room.beds || []).forEach((bed) => {
					this._render_bed_card(bed, room, data.building)
						.attr("data-color", bed.bed_color)
						.appendTo($beds);
				});
			});
		});

		this._apply_filters();
	}

	// A position:sticky portfolio header: the building title, four mini-stats from
	// the existing summary, and a thin occupancy meter. Presentational only — it
	// reuses the grid's summary counts (no extra server call) and stays pinned
	// while the operator scrolls floors.
	_render_summary_bar(data) {
		const s = data.summary || {};
		const total = cint(s.total_beds);
		const occupied = cint(s.occupied);
		const pct = total ? Math.round((occupied / total) * 100) : 0;

		const $bar = $('<div class="fd-summary" role="status" aria-live="polite"></div>').appendTo(
			this.$container
		);

		const $head = $('<div class="fd-summary-head"></div>').appendTo($bar);
		$('<span class="fd-summary-title"></span>')
			.text(data.building_title || data.building)
			.appendTo($head);
		this._render_open_requests_badge($head, data.building);

		const $stats = $('<div class="fd-summary-stats"></div>').appendTo($bar);
		const stat = (key, label, value, tone) => {
			const $stat = $(`<div class="fd-summary-stat fd-summary-stat--${tone}"></div>`).appendTo(
				$stats
			);
			$('<bdi class="fd-summary-stat-num" dir="ltr"></bdi>').text(fd_int(value)).appendTo($stat);
			$('<span class="fd-summary-stat-label"></span>').text(label).appendTo($stat);
			$stat.attr("data-stat", key);
		};
		stat("available", __("Available"), s.available, "green");
		stat("occupied", __("Occupied"), s.occupied, "red");
		stat("blocked", __("Room not ready"), s.blocked, "amber");
		stat("out_of_service", __("Out of service"), s.out_of_service, "grey");

		const $meter = $('<div class="fd-summary-meter"></div>').appendTo($bar);
		const $track = $(
			`<div class="fd-summary-meter-track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}"></div>`
		).appendTo($meter);
		$('<div class="fd-summary-meter-fill"></div>')
			.css("inline-size", `${pct}%`)
			.appendTo($track);
		$('<bdi class="fd-summary-meter-label" dir="ltr"></bdi>')
			.text(fd_percent(pct))
			.appendTo($meter);
		$('<span class="fd-summary-meter-caption"></span>')
			.text(__("{0} of {1} beds available", [fd_int(s.available), fd_int(s.total_beds)]))
			.appendTo($meter);
	}

	// A legend that doubles as client-side filters. The color swatches name what
	// each bed color means; three toggles narrow the board without a round-trip
	// (filtering is purely show/hide over the already-loaded grid).
	_render_legend() {
		const $legend = $('<div class="fd-legend"></div>').appendTo(this.$container);

		const swatches = [
			["green", __("Available")],
			["red", __("Occupied")],
			["amber", __("Room not ready")],
			["grey", __("Out of service")],
		];
		const $key = $('<div class="fd-legend-key"></div>').appendTo($legend);
		swatches.forEach(([color, label]) => {
			const $item = $('<span class="fd-legend-item"></span>').appendTo($key);
			$(`<span class="fd-legend-dot fd-bed--${color}"></span>`).appendTo($item);
			$('<span class="fd-legend-label"></span>').text(label).appendTo($item);
		});

		const toggles = [
			["only_available", __("Show only available")],
			["hide_out_of_service", __("Hide out of service")],
			["only_needs_readiness", __("Rooms needing readiness")],
		];
		const $filters = $('<div class="fd-legend-filters"></div>').appendTo($legend);
		toggles.forEach(([key, label]) => {
			const active = this.filters[key];
			const $btn = $('<button type="button" class="fd-legend-filter"></button>')
				.toggleClass("fd-legend-filter--active", active)
				.attr("aria-pressed", active ? "true" : "false")
				.text(label)
				.appendTo($filters);
			$btn.on("click", () => {
				this.filters[key] = !this.filters[key];
				$btn.toggleClass("fd-legend-filter--active", this.filters[key]);
				$btn.attr("aria-pressed", this.filters[key] ? "true" : "false");
				this._apply_filters();
			});
		});
	}

	// Apply the active legend filters by hiding non-matching beds, then collapsing
	// rooms/floors left with no visible bed. Pure client-side show/hide.
	_apply_filters() {
		const f = this.filters;
		this.$container.find(".fd-bed").each((_i, el) => {
			const $bed = $(el);
			const color = $bed.attr("data-color");
			let show = true;
			if (f.only_available && color !== "green") show = false;
			if (f.hide_out_of_service && color === "grey") show = false;
			$bed.toggleClass("fd-bed--filtered", !show);
		});
		this.$container.find(".fd-room").each((_i, el) => {
			const $room = $(el);
			const needs_readiness = $room.attr("data-needs-readiness") === "1";
			const has_visible_bed = $room.find(".fd-bed:not(.fd-bed--filtered)").length > 0;
			const readiness_ok = !f.only_needs_readiness || needs_readiness;
			$room.toggleClass("fd-room--filtered", !(has_visible_bed && readiness_ok));
		});
		// Collapse a floor whose every room is hidden.
		this.$container.find(".fd-floor").each((_i, el) => {
			const $floor = $(el);
			const has_visible_room = $floor.find(".fd-room:not(.fd-room--filtered)").length > 0;
			$floor.toggleClass("fd-floor--filtered", !has_visible_room);
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
					.text(__("{0} open requests", [fd_int(count)]))
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
		// The bed code is a naming-series-style token; isolate it LTR so it renders
		// left-to-right on its own line, even on an RTL board beside an Arabic name.
		$('<bdi class="fd-bed-code" dir="ltr"></bdi>').text(bed.bed_code || bed.bed).appendTo($card);

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

		const handler = () => this._on_bed_click(bed, room, building, $card);
		$card.on("click", handler);
		$card.on("keydown", (e) => {
			if (e.key === "Enter" || e.key === " ") {
				e.preventDefault();
				handler();
			}
		});
		return $card;
	}

	// Mark/unmark a bed card busy during a check-in/out round-trip so the operator
	// sees the clicked bed is working before the board refresh repaints it.
	_set_bed_updating($card, busy) {
		if (!$card) return;
		$card.toggleClass("fd-bed--updating", !!busy);
		$card.attr("aria-busy", busy ? "true" : null);
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

	_on_bed_click(bed, room, building, $card) {
		switch (bed.bed_color) {
			case "green":
				this._open_check_in_dialog(bed, room, building, $card);
				break;
			case "red":
				this._open_check_out_dialog(bed, room, building, $card);
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

	_open_check_in_dialog(bed, room, building, $card) {
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
				d.hide();
				this._set_bed_updating($card, true);
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
					callback: (r) => {
						if (r.exc || !r.message) {
							this._set_bed_updating($card, false);
							return;
						}
						frappe.show_alert({
							message: __("Checked in: {0}", [r.message.assignment]),
							indicator: "green",
						});
						this.refresh();
					},
					error: () => this._set_bed_updating($card, false),
				});
			},
		});
		d.show();
	}

	_open_check_out_dialog(bed, room, building, $card) {
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
				d.hide();
				this._set_bed_updating($card, true);
				frappe.call({
					method: "apex_habitat.habitat.api.front_desk.quick_check_out",
					args: {
						bed: bed.bed,
						checkout_date: values.checkout_date,
						checkout_reason: values.checkout_reason,
						room_condition_snapshot: values.room_condition_snapshot || null,
					},
					callback: (r) => {
						if (r.exc || !r.message) {
							this._set_bed_updating($card, false);
							return;
						}
						if (r.message.requires_full_form) {
							this._set_bed_updating($card, false);
							frappe.show_alert({
								message: __("This resident has custody items. Opening the full Checkout form to clear custody."),
								indicator: "orange",
							});
							frappe.new_doc("Accommodation Checkout", { assignment: r.message.assignment });
							return;
						}
						frappe.show_alert({
							message: __("Checked out: {0}", [r.message.checkout]),
							indicator: "green",
						});
						this.refresh();
					},
					error: () => this._set_bed_updating($card, false),
				});
			},
		});
		d.show();
	}
}
