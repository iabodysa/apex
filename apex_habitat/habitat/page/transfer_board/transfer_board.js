// Transfer Board — split-screen drag-and-drop resident transfer (v0.9.0).
//
// Standard Frappe page built from frappe.ui.Page primitives + native HTML5
// drag-and-drop + native frappe.ui.Dialog. No SPA / Vue / React / external
// libraries. Each pane reuses the read-only front_desk.get_building_grid reader
// (one bulk, N+1-free call per side). The single write routes through the
// existing Room Bed Transfer controller via transfer_occupant. The server is the
// source of truth: after a transfer we RE-FETCH both panes rather than mutating
// the DOM optimistically.
//
// Gestures:
//   * HTML5 drag-and-drop (mouse): drag an OCCUPIED bed card onto an AVAILABLE
//     bed card → confirm dialog → transfer.
//   * Tap/click fallback (tablets/keyboard): tap an occupied bed to select the
//     source (it highlights), then tap an available bed to pick the target.

frappe.pages["transfer-board"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Transfer Board"),
		single_column: true,
	});

	const tb = new TransferBoard(page);
	tb.setup();
};

class TransferBoard {
	constructor(page) {
		this.page = page;
		// One pane descriptor per side.
		this.panes = {
			left: { building: null, data: null, $grid: null, field: null },
			right: { building: null, data: null, $grid: null, field: null },
		};
		// Tap-fallback selection: {side, bed, room, building} or null.
		this.selected_source = null;
	}

	setup() {
		this.$root = $('<div class="tb-board"></div>').appendTo(this.page.main);

		$('<div class="tb-help text-muted"></div>')
			.text(__("Drag an occupied bed onto an empty bed to transfer the resident."))
			.appendTo(this.$root);

		this.$split = $('<div class="tb-split"></div>').appendTo(this.$root);
		this.panes.left.$grid = this._make_pane("left", __("Building A"));
		this.panes.right.$grid = this._make_pane("right", __("Building B"));

		this._setup_controls();
	}

	_make_pane(side, label) {
		const $pane = $(`<div class="tb-pane tb-pane--${side}"></div>`).appendTo(this.$split);
		$(`<div class="tb-pane-label"></div>`).text(label).appendTo($pane);
		const $grid = $('<div class="tb-grid"></div>').appendTo($pane);
		this._render_empty($grid, __("Select a building to load the board."));
		return $grid;
	}

	_setup_controls() {
		this.panes.left.field = this.page.add_field({
			fieldname: "building_left",
			label: __("Building A"),
			fieldtype: "Link",
			options: "Accommodation Building",
			change: () => this._on_building_change("left"),
		});
		this.panes.right.field = this.page.add_field({
			fieldname: "building_right",
			label: __("Building B"),
			fieldtype: "Link",
			options: "Accommodation Building",
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
		// Keep a stable selection across a manual re-fetch of the side that does
		// not hold the current source highlight; clear it if it belongs here.
		this._render_loading(pane.$grid);
		frappe.call({
			method: "apex_habitat.habitat.api.front_desk.get_building_grid",
			args: { building: pane.building },
			// Inline per-pane loading state instead of a global freeze, so the
			// other pane and the page chrome stay interactive while one loads.
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
		$('<div class="tb-empty text-muted"></div>').text(message).appendTo($grid);
	}

	_render_loading($grid) {
		$grid.empty();
		const $wrap = $('<div class="tb-loading" aria-busy="true"></div>').appendTo($grid);
		$('<div class="tb-spinner" role="status" aria-label="Loading"></div>').appendTo($wrap);
		$('<div class="tb-loading-text text-muted"></div>').text(__("Loading board…")).appendTo($wrap);
		// Lightweight skeleton rows so the pane has shape while data arrives.
		const $sk = $('<div class="tb-skeleton"></div>').appendTo($wrap);
		for (let i = 0; i < 3; i++) {
			$('<div class="tb-skeleton-row"></div>').appendTo($sk);
		}
	}

	_render_error(side) {
		const pane = this.panes[side];
		const $grid = pane.$grid;
		$grid.empty();
		const $err = $('<div class="tb-error"></div>').appendTo($grid);
		$('<div class="tb-error-msg"></div>')
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
		const $summary = $('<div class="tb-summary"></div>').appendTo($grid);
		$('<span class="tb-summary-title"></span>')
			.text(data.building_title || data.building)
			.appendTo($summary);
		$('<span class="tb-summary-counts"></span>')
			.text(__("{0} of {1} beds available", [s.available || 0, s.total_beds || 0]))
			.appendTo($summary);

		if (!data.floors || !data.floors.length) {
			this._render_empty($grid, __("No beds found for this building."));
			return;
		}

		data.floors.forEach((floor) => {
			const $floor = $('<div class="tb-floor"></div>').appendTo($grid);
			$('<div class="tb-floor-header"></div>').text(floor.floor_label).appendTo($floor);
			const $rooms = $('<div class="tb-rooms"></div>').appendTo($floor);

			(floor.rooms || []).forEach((room) => {
				const $room = $('<div class="tb-room"></div>').appendTo($rooms);
				$('<div class="tb-room-header"></div>')
					.text(`${__("Room")} ${room.room_number || room.room}`)
					.appendTo($room);
				const $beds = $('<div class="tb-beds"></div>').appendTo($room);
				(room.beds || []).forEach((bed) => {
					this._render_bed_card(side, bed, room, data.building).appendTo($beds);
				});
			});
		});
	}

	_render_bed_card(side, bed, room, building) {
		const is_occupied = bed.bed_color === "red" && bed.occupant;
		const is_available = bed.bed_color === "green";

		const $card = $(
			`<div class="tb-bed tb-bed--${bed.bed_color}" tabindex="0" role="button"></div>`
		);
		$card.data("ctx", { side, bed, room, building });

		$('<div class="tb-bed-code"></div>').text(bed.bed_code || bed.bed).appendTo($card);

		let badge = "";
		if (is_available) badge = __("Available");
		else if (bed.bed_color === "red") badge = __("Occupied");
		else if (bed.bed_color === "amber") badge = __("Room not ready");
		else badge = __("Out of Service");
		$('<div class="tb-bed-badge"></div>').text(badge).appendTo($card);

		if (is_occupied) {
			$('<div class="tb-bed-occupant"></div>')
				.text(bed.occupant.employee_name || bed.occupant.employee)
				.appendTo($card);
		}

		// HTML5 drag source: only occupied beds are draggable.
		if (is_occupied) {
			$card.attr("draggable", "true");
			$card.addClass("tb-bed--draggable");
			$card.on("dragstart", (e) => {
				const dt = e.originalEvent.dataTransfer;
				dt.effectAllowed = "move";
				dt.setData("text/plain", bed.bed);
				$card.addClass("tb-bed--dragging");
			});
			$card.on("dragend", () => $card.removeClass("tb-bed--dragging"));
		}

		// HTML5 drop target: only available beds accept a drop.
		if (is_available) {
			$card.on("dragover", (e) => {
				e.preventDefault();
				e.originalEvent.dataTransfer.dropEffect = "move";
				$card.addClass("tb-bed--dropover");
			});
			$card.on("dragleave", () => $card.removeClass("tb-bed--dropover"));
			$card.on("drop", (e) => {
				e.preventDefault();
				$card.removeClass("tb-bed--dropover");
				const source_bed = e.originalEvent.dataTransfer.getData("text/plain");
				if (source_bed) {
					this._begin_transfer(source_bed, bed, building);
				}
			});
		}

		// Tap/click fallback (tablet + keyboard).
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

		// Step 1 — pick an occupied source.
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
			$card.addClass("tb-bed--selected");
			frappe.show_alert({
				message: __("Now tap an available bed to transfer the resident."),
				indicator: "blue",
			});
			return;
		}

		// Tapping the same source again deselects.
		if (this.selected_source.bed.bed === bed.bed) {
			this.selected_source = null;
			this._clear_selection_highlight();
			return;
		}

		// Step 2 — pick an available target.
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
		this.$root.find(".tb-bed--selected").removeClass("tb-bed--selected");
	}

	_begin_transfer(source_bed, target_bed_card, target_building) {
		// Look up the occupant label of the source for the confirm dialog.
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
					method: "apex_habitat.habitat.api.transfer_board.transfer_occupant",
					args: {
						source_bed: source_bed,
						target_bed: target_bed_card.bed,
						transfer_date: values.transfer_date,
						reason: values.reason || null,
					},
					freeze: true,
					freeze_message: __("Transferring…"),
					callback: (r) => {
						// On a server-side throw Frappe surfaces the message itself;
						// keep the dialog open so the operator can correct and retry.
						if (r.exc || !r.message || !r.message.transfer) {
							return;
						}
						d.hide();
						frappe.show_alert({
							message: __("Transferred: {0}", [r.message.transfer]),
							indicator: "green",
						});
						// Re-fetch BOTH panes — server is the source of truth.
						this.refresh_all();
					},
					error: () => {
						// Network/unexpected failure: keep dialog open, tell the user.
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

	// Find the rendered bed context (across both panes) by bed docname.
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
