// Copyright (c) 2026, afmcoltd

frappe.pages["transfer-board"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Transfer Board"),
		single_column: true,
	});

	const tb = new TransferBoard(page);
	tb.setup();
};

function tb_indicator_color(bed_color) {
	return { green: "green", red: "red", amber: "orange", grey: "gray" }[bed_color] || "gray";
}

const TB_BED_PALETTE = {
	green: "background:var(--green-100);border-color:var(--green-500);color:var(--green-700);",
	red: "background:var(--red-100);border-color:var(--red-500);color:var(--red-700);",
	amber: "background:var(--yellow-100);border-color:var(--orange-500);color:var(--orange-700);cursor:not-allowed;",
	grey: "background:var(--gray-100);border-color:var(--gray-400);color:var(--gray-600);cursor:not-allowed;",
};
const TB_STYLE = {
	help: "margin-block:var(--margin-sm,10px);font-size:var(--text-sm,12px);",
	split: "display:flex;flex-wrap:wrap;gap:var(--margin-md,15px);align-items:flex-start;",
	pane:
		"flex:1 1 360px;min-inline-size:320px;border:1px solid var(--border-color);border-radius:var(--border-radius-md,8px);padding:var(--padding-md,15px);background:var(--card-bg);",
	pane_label: "font-weight:600;font-size:var(--text-md,14px);margin-block-end:var(--margin-sm,10px);",
	summary:
		"display:flex;flex-wrap:wrap;align-items:baseline;gap:var(--margin-sm,10px);margin-block-end:var(--margin-sm,10px);padding-block-end:8px;border-block-end:1px solid var(--border-color);",
	summary_title: "font-weight:600;font-size:var(--text-md,14px);",
	summary_counts: "font-size:var(--text-sm,12px);color:var(--text-muted);",
	floor: "margin-block-end:var(--margin-md,15px);",
	floor_header: "font-size:var(--text-sm,12px);font-weight:600;color:var(--text-muted);margin-block-end:8px;",
	rooms: "display:flex;flex-direction:column;gap:var(--margin-sm,10px);",
	room: "border:1px solid var(--border-color);border-radius:var(--border-radius-md,8px);padding:var(--padding-sm,10px);",
	room_header: "font-weight:600;font-size:var(--text-sm,12px);margin-block-end:8px;",
	beds: "display:grid;grid-template-columns:repeat(auto-fill,minmax(90px,1fr));gap:8px;",
	bed:
		"border:2px solid var(--border-color);border-radius:var(--border-radius-md,8px);padding:10px 8px;min-height:78px;display:flex;flex-direction:column;gap:3px;cursor:pointer;background:var(--card-bg);user-select:none;",
	bed_code: "font-weight:700;font-size:var(--text-md,14px);",
	bed_occupant: "font-size:11px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;",
	empty: "padding-block:var(--padding-lg,20px);text-align:center;font-size:var(--text-sm,12px);",
	loading: "padding-block:var(--padding-lg,20px);text-align:center;",
	error: "padding-block:var(--padding-lg,20px);text-align:center;",
};

class TransferBoard {
	constructor(page) {
		this.page = page;
		this.panes = {
			left: { building: null, data: null, $grid: null, field: null },
			right: { building: null, data: null, $grid: null, field: null },
		};
		this.selected_source = null;
	}

	setup() {
		this.$root = $('<div class="tb-board"></div>').appendTo(this.page.main);

		$('<div class="tb-help text-muted"></div>')
			.attr("style", TB_STYLE.help)
			.text(__("Drag an occupied bed onto an empty bed to transfer the resident."))
			.appendTo(this.$root);

		this.$split = $('<div class="tb-split"></div>').attr("style", TB_STYLE.split).appendTo(this.$root);
		this.panes.left.$grid = this._make_pane("left", __("Building A"));
		this.panes.right.$grid = this._make_pane("right", __("Building B"));

		this._setup_controls();
	}

	_make_pane(side, label) {
		const $pane = $(`<div class="tb-pane tb-pane--${side}"></div>`).attr("style", TB_STYLE.pane).appendTo(this.$split);
		$(`<div class="tb-pane-label"></div>`).attr("style", TB_STYLE.pane_label).text(label).appendTo($pane);
		const $grid = $('<div class="tb-grid"></div>').appendTo($pane);
		this._render_empty($grid, __("Select a building to load the board."));
		return $grid;
	}

	_setup_controls() {
		this.panes.left.field = this.page.add_field({
			fieldname: "building_left",
			label: __("Building A"),
			fieldtype: "Link",
			options: "Building",
			change: () => this._on_building_change("left"),
		});
		this.panes.right.field = this.page.add_field({
			fieldname: "building_right",
			label: __("Building B"),
			fieldtype: "Link",
			options: "Building",
			change: () => this._on_building_change("right"),
		});

		this.page.set_primary_action(
			__("Refresh Board"),
			() => this.refresh_all(),
			"refresh"
		);
	}

	_on_building_change(side) {
		const pane = this.panes[side];
		const val = pane.field.get_value();
		if (val && val !== pane.building) {
			pane.building = val;
			this.selected_source = null;
			this.refresh(side);
		}
	}

	refresh_all() {
		["left", "right"].forEach((side) => {
			if (this.panes[side].building) this.refresh(side);
		});
	}

	refresh(side) {
		const pane = this.panes[side];
		if (!pane.building) return;
		this._render_loading(pane.$grid);
		frappe.call({
			method: "apex.habitat.api.front_desk.get_building_grid",
			args: { building: pane.building },
			callback: (r) => {
				if (r.exc || !r.message) {
					this._render_error(side);
					return;
				}
				pane.data = r.message;
				this._render_grid(side);
			},
			error: () => {
				this._render_error(side);
			},
		});
	}

	_render_empty($grid, message) {
		$grid.empty();
		$('<div class="tb-empty text-muted"></div>').attr("style", TB_STYLE.empty).text(message).appendTo($grid);
	}

	_render_loading($grid) {
		$grid.empty();
		const $wrap = $('<div class="tb-loading" aria-busy="true"></div>').attr("style", TB_STYLE.loading).appendTo($grid);
		$('<div class="tb-loading-text text-muted"></div>')
			.css("margin-block-end", "var(--margin-sm, 10px)")
			.text(__("Loading board…"))
			.appendTo($wrap);
		const $sk = $('<div class="tb-skeleton"></div>').css({ display: "flex", "flex-direction": "column", gap: "8px" }).appendTo($wrap);
		for (let i = 0; i < 3; i++) {
			$('<div class="skeleton-block"></div>').css({ height: "48px", background: "var(--skeleton-bg)", "border-radius": "8px" }).appendTo($sk);
		}
	}

	_render_error(side) {
		const pane = this.panes[side];
		const $grid = pane.$grid;
		$grid.empty();
		const $err = $('<div class="tb-error"></div>').attr("style", TB_STYLE.error).appendTo($grid);
		$('<div class="tb-error-msg"></div>')
			.css("margin-block-end", "var(--margin-sm, 10px)")
			.text(__("Could not load this building. Please try again."))
			.appendTo($err);
		$('<button class="btn btn-default btn-sm tb-retry"></button>')
			.text(__("Retry"))
			.on("click", () => this.refresh(side))
			.appendTo($err);
	}

	_render_grid(side) {
		const pane = this.panes[side];
		const $grid = pane.$grid;
		const data = pane.data;
		$grid.empty();

		const s = (data && data.summary) || {};
		const $summary = $('<div class="tb-summary"></div>').attr("style", TB_STYLE.summary).appendTo($grid);
		$('<span class="tb-summary-title"></span>')
			.attr("style", TB_STYLE.summary_title)
			.text(data.building_title || data.building)
			.appendTo($summary);
		$('<span class="tb-summary-counts"></span>')
			.attr("style", TB_STYLE.summary_counts)
			.text(__("{0} of {1} beds available", [s.available || 0, s.total_beds || 0]))
			.appendTo($summary);

		if (!data.floors || !data.floors.length) {
			this._render_empty($grid, __("No beds found for this building."));
			return;
		}

		data.floors.forEach((floor) => {
			const $floor = $('<div class="tb-floor"></div>').attr("style", TB_STYLE.floor).appendTo($grid);
			$('<div class="tb-floor-header"></div>').attr("style", TB_STYLE.floor_header).text(floor.floor_label).appendTo($floor);
			const $rooms = $('<div class="tb-rooms"></div>').attr("style", TB_STYLE.rooms).appendTo($floor);

			(floor.rooms || []).forEach((room) => {
				const $room = $('<div class="tb-room"></div>').attr("style", TB_STYLE.room).appendTo($rooms);
				$('<div class="tb-room-header"></div>')
					.attr("style", TB_STYLE.room_header)
					.text(`${__("Room")} ${room.room_number || room.room}`)
					.appendTo($room);
				const $beds = $('<div class="tb-beds"></div>').attr("style", TB_STYLE.beds).appendTo($room);
				(room.beds || []).forEach((bed) => {
					this._render_bed_card(side, bed, room, data.building).appendTo($beds);
				});
			});
		});
	}

	_render_bed_card(side, bed, room, building) {
		const is_occupied = bed.bed_color === "red" && bed.occupant;
		const is_available = bed.bed_color === "green";

		const $card = $(`<div class="tb-bed" tabindex="0" role="button"></div>`);
		$card.attr("style", TB_STYLE.bed + (TB_BED_PALETTE[bed.bed_color] || ""));
		$card.data("ctx", { side, bed, room, building });

		$('<div class="tb-bed-code"></div>').attr("style", TB_STYLE.bed_code).text(bed.bed_code || bed.bed).appendTo($card);

		let badge = "";
		if (is_available) badge = __("Available");
		else if (bed.bed_color === "red") badge = __("Occupied");
		else if (bed.bed_color === "amber") badge = __("Room not ready");
		else badge = __("Out of Service");
		$(`<span class="tb-bed-badge indicator-pill ${tb_indicator_color(bed.bed_color)}"></span>`)
			.text(badge)
			.appendTo($card);

		if (is_occupied) {
			$('<div class="tb-bed-occupant"></div>')
				.attr("style", TB_STYLE.bed_occupant)
				.text(bed.occupant.employee_name || bed.occupant.employee)
				.appendTo($card);
		}

		if (is_occupied) {
			$card.attr("draggable", "true");
			$card.on("dragstart", (e) => {
				const dt = e.originalEvent.dataTransfer;
				dt.effectAllowed = "move";
				dt.setData("text/plain", bed.bed);
				$card.addClass("invisible");
			});
			$card.on("dragend", () => $card.removeClass("invisible"));
		}

		if (is_available) {
			$card.on("dragover", (e) => {
				e.preventDefault();
				e.originalEvent.dataTransfer.dropEffect = "move";
				$card.addClass("active").css("box-shadow", "0 0 0 2px var(--primary)");
			});
			$card.on("dragleave", () => $card.removeClass("active").css("box-shadow", ""));
			$card.on("drop", (e) => {
				e.preventDefault();
				$card.removeClass("active").css("box-shadow", "");
				const source_bed = e.originalEvent.dataTransfer.getData("text/plain");
				if (source_bed) {
					this._begin_transfer(source_bed, bed, building);
				}
			});
		}

		const handler = () => this._on_bed_tap(side, bed, room, building, $card);
		$card.on("click", handler);
		$card.on("keydown", (e) => {
			if (e.key === "Enter" || e.key === " ") {
				e.preventDefault();
				handler();
			}
		});

		return $card;
	}

	_on_bed_tap(side, bed, room, building, $card) {
		const is_occupied = bed.bed_color === "red" && bed.occupant;
		const is_available = bed.bed_color === "green";

		if (!this.selected_source) {
			if (!is_occupied) {
				if (is_available) {
					frappe.show_alert({
						message: __("Source bed has no active resident to transfer."),
						indicator: "orange",
					});
				}
				return;
			}
			this.selected_source = { side, bed, room, building };
			this._clear_selection_highlight();
			$card.addClass("active").css("box-shadow", "0 0 0 2px var(--primary)");
			frappe.show_alert({
				message: __("Now tap an available bed to transfer the resident."),
				indicator: "blue",
			});
			return;
		}

		if (this.selected_source.bed.bed === bed.bed) {
			this.selected_source = null;
			this._clear_selection_highlight();
			return;
		}

		if (!is_available) {
			frappe.show_alert({
				message: __("Drop target must be an available bed."),
				indicator: "orange",
			});
			return;
		}

		const source_bed = this.selected_source.bed.bed;
		this.selected_source = null;
		this._clear_selection_highlight();
		this._begin_transfer(source_bed, bed, building);
	}

	_clear_selection_highlight() {
		this.$root.find(".tb-bed.active").removeClass("active").css("box-shadow", "");
	}

	_begin_transfer(source_bed, target_bed_card, target_building) {
		const source_ctx = this._find_bed(source_bed);
		const occupant_label = source_ctx && source_ctx.bed.occupant
			? source_ctx.bed.occupant.employee_name || source_ctx.bed.occupant.employee
			: source_bed;
		const from_label = source_ctx
			? source_ctx.bed.bed_code || source_ctx.bed.bed
			: source_bed;
		const to_label = target_bed_card.bed_code || target_bed_card.bed;

		const d = new frappe.ui.Dialog({
			title: __("Confirm Transfer"),
			fields: [
				{
					fieldname: "context",
					fieldtype: "HTML",
					options: `<div style="margin-bottom:8px">${frappe.utils.escape_html(
						__("Move {0} from {1} to {2}?", [occupant_label, from_label, to_label])
					)}</div>`,
				},
				{
					fieldname: "transfer_date",
					label: __("Transfer Date"),
					fieldtype: "Date",
					reqd: 1,
					default: frappe.datetime.get_today(),
				},
				{ fieldname: "reason", label: __("Reason"), fieldtype: "Small Text" },
			],
			primary_action_label: __("Transfer"),
			primary_action: (values) => {
				frappe.call({
					method: "apex.habitat.api.transfer_board.transfer_occupant",
					args: {
						source_bed: source_bed,
						target_bed: target_bed_card.bed,
						transfer_date: values.transfer_date,
						reason: values.reason || null,
					},
					freeze: true,
					freeze_message: __("Transferring…"),
					callback: (r) => {
						if (r.exc || !r.message || !r.message.transfer) {
							return;
						}
						d.hide();
						frappe.show_alert({
							message: __("Transferred: {0}", [r.message.transfer]),
							indicator: "green",
						});
						this.refresh_all();
					},
					error: () => {
						frappe.show_alert({
							message: __("Transfer failed. Please try again."),
							indicator: "red",
						});
					},
				});
			},
		});
		d.show();
	}

	_find_bed(bed_name) {
		let found = null;
		this.$root.find(".tb-bed").each(function () {
			const ctx = $(this).data("ctx");
			if (ctx && ctx.bed && ctx.bed.bed === bed_name) {
				found = ctx;
				return false;
			}
		});
		return found;
	}
}
