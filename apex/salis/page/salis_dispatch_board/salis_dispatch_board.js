// Copyright (c) 2026, afmcoltd

frappe.pages["salis-dispatch-board"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Salis Dispatch Board"),
		single_column: true,
	});

	const board = new SalisDispatchBoard(page);
	board.setup();
};

const VEHICLE_STATUS_COLOR = {
	Active: "green",
	Stopped: "orange",
	"Under Maintenance": "red",
	Released: "grey",
	Other: "grey",
};

const TRIP_STATUS_COLOR = {
	Planned: "blue",
	Dispatched: "orange",
	Completed: "green",
	Cancelled: "grey",
	Other: "grey",
};

class SalisDispatchBoard {
	constructor(page) {
		this.page = page;
		this.project = null;
	}

	setup() {
		this.$board = $('<div class="sdb-board"></div>').appendTo(this.page.main);
		$('<div class="sdb-help text-muted"></div>')
			.css("margin-block-start", "var(--margin-sm, 10px)")
			.text(
				__(
					"Live fleet glance: vehicles by status, today's trips, driver availability and open transport requests."
				)
			)
			.appendTo(this.$board);
		this.$panes = $('<div class="sdb-panes"></div>').appendTo(this.$board);

		this._setup_controls();
		this.refresh();
	}

	_setup_controls() {
		this.project_field = this.page.add_field({
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
			change: () => {
				this.project = this.project_field.get_value() || null;
				this.refresh();
			},
		});

		this.page.set_primary_action(__("Refresh"), () => this.refresh(), "refresh");
	}

	refresh() {
		if (this._loading) return;
		this._loading = true;
		this._show_loading();
		frappe.call({
			method: "apex.salis.api.dispatch_board.get_dispatch_board",
			args: { project: this.project || null },
			callback: (r) => {
				if (r.exc || !r.message) {
					this._show_error();
					return;
				}
				this._render(r.message);
			},
			error: () => {
				this._show_error();
			},
			always: () => {
				this._loading = false;
			},
		});
	}

	_show_loading() {
		this.$panes.empty();
		for (let i = 0; i < 4; i++) {
			const $pane = $('<div class="sdb-pane"></div>').appendTo(this.$panes);
			$('<div class="skeleton-block"></div>')
				.css({ height: "20px", margin: "var(--padding-md, 15px)", background: "var(--skeleton-bg)", "border-radius": "6px" })
				.appendTo($pane);
			const $body = $('<div class="sdb-pane-body"></div>').appendTo($pane);
			for (let j = 0; j < 3; j++) {
				$('<div class="skeleton-block"></div>').css({ height: "48px", background: "var(--skeleton-bg)", "border-radius": "8px" }).appendTo($body);
			}
		}
	}

	_show_error() {
		this.$panes.empty();
		const $err = $('<div class="sdb-error"></div>')
			.css({ "grid-column": "1 / -1", "text-align": "center", "padding-block": "var(--padding-xl, 30px)" })
			.appendTo(this.$panes);
		$('<div class="sdb-error-msg"></div>')
			.css("margin-block-end", "var(--margin-sm, 10px)")
			.text(
				__(
					"Could not load the dispatch board. Please check your connection and try again."
				)
			)
			.appendTo($err);
		const $retry = $(
			'<button class="btn btn-default btn-sm sdb-retry"></button>'
		)
			.text(__("Retry"))
			.appendTo($err);
		$retry.on("click", () => this.refresh());
	}

	_render(data) {
		this.$panes.empty();
		this._render_vehicles_pane(data.vehicles || {});
		this._render_trips_pane(data.trips_today || {});
		this._render_drivers_pane(data.drivers || {});
		this._render_requests_pane(data.transport_requests || {});
	}


	_make_pane(title, count_text) {
		const $pane = $('<div class="sdb-pane"></div>').appendTo(this.$panes);
		const $head = $('<div class="sdb-pane-head"></div>').appendTo($pane);
		$('<span class="sdb-pane-title"></span>').text(title).appendTo($head);
		if (count_text !== undefined && count_text !== null) {
			$('<span class="sdb-pane-count"></span>')
				.text(count_text)
				.appendTo($head);
		}
		const $body = $('<div class="sdb-pane-body"></div>').appendTo($pane);
		return $body;
	}

	_render_empty($parent, message) {
		$('<div class="sdb-empty text-muted"></div>').text(message).appendTo($parent);
	}

	_indicator(label, color) {
		const $span = $(`<span class="indicator-pill ${color || "grey"}"></span>`);
		$('<span></span>').text(label).appendTo($span);
		return $span;
	}

	_kv($parent, label, value) {
		const $r = $('<div class="sdb-kv"></div>').appendTo($parent);
		$('<span class="sdb-kv-label"></span>').text(label).appendTo($r);
		$('<span class="sdb-kv-value"></span>')
			.text(value === null || value === undefined || value === "" ? "—" : value)
			.appendTo($r);
		return $r;
	}


	_render_vehicles_pane(pane) {
		const $body = this._make_pane(
			__("Vehicles by Status"),
			__("{0} total", [pane.total || 0])
		);
		const groups = pane.groups || [];
		if (!groups.length) {
			this._render_empty($body, __("No vehicles in scope."));
			return;
		}
		groups.forEach((group) => {
			const $group = $('<div class="sdb-group"></div>').appendTo($body);
			const $gh = $('<div class="sdb-group-head"></div>').appendTo($group);
			this._indicator(
				__(group.status),
				VEHICLE_STATUS_COLOR[group.status] || "grey"
			).appendTo($gh);
			$('<span class="sdb-group-count"></span>')
				.text(group.count || 0)
				.appendTo($gh);

			const $list = $('<div class="sdb-cards"></div>').appendTo($group);
			(group.items || []).forEach((v) => {
				const $card = $('<div class="sdb-card"></div>').appendTo($list);
				$('<div class="sdb-card-title"></div>')
					.text(v.plate_number || v.name)
					.appendTo($card);
				this._kv($card, __("Category"), v.vehicle_category);
				this._kv($card, __("Driver"), v.current_driver);
				this._kv($card, __("Project"), v.project);
				if (v.compliance_status) {
					this._kv($card, __("Compliance"), __(v.compliance_status));
				}
			});
		});
	}


	_render_trips_pane(pane) {
		const $body = this._make_pane(
			__("Today's Dispatch Trips"),
			__("{0} total", [pane.total || 0])
		);
		const groups = pane.groups || [];
		const has_any = groups.some((g) => (g.count || 0) > 0);
		if (!has_any) {
			this._render_empty($body, __("No trips scheduled for today."));
			return;
		}
		groups.forEach((group) => {
			if (!(group.count || 0)) return;
			const $group = $('<div class="sdb-group"></div>').appendTo($body);
			const $gh = $('<div class="sdb-group-head"></div>').appendTo($group);
			this._indicator(
				__(group.status),
				TRIP_STATUS_COLOR[group.status] || "grey"
			).appendTo($gh);
			$('<span class="sdb-group-count"></span>')
				.text(group.count || 0)
				.appendTo($gh);

			const $list = $('<div class="sdb-cards"></div>').appendTo($group);
			(group.items || []).forEach((t) => {
				const $card = $('<div class="sdb-card"></div>').appendTo($list);
				$('<div class="sdb-card-title"></div>').text(t.name).appendTo($card);
				this._kv($card, __("Vehicle"), t.vehicle_plate || t.vehicle);
				this._kv($card, __("Driver"), t.driver_name || t.driver);
				this._kv($card, __("Route Plan"), t.route_plan);
				this._kv(
					$card,
					__("Window"),
					[t.depart_time, t.return_time].filter(Boolean).join(" → ") || null
				);
			});
		});
	}


	_render_drivers_pane(pane) {
		const active = pane.active_total || 0;
		const $body = this._make_pane(
			__("Driver Availability"),
			__("{0} active", [active])
		);

		const $split = $('<div class="sdb-driver-split"></div>').appendTo($body);
		this._render_driver_column(
			$split,
			__("Available"),
			"green",
			pane.available_count || 0,
			pane.available || [],
			__("No available drivers.")
		);
		this._render_driver_column(
			$split,
			__("Assigned Today"),
			"orange",
			pane.assigned_count || 0,
			pane.assigned || [],
			__("No drivers assigned today.")
		);
	}

	_render_driver_column($parent, label, color, count, drivers, empty_msg) {
		const $col = $('<div class="sdb-driver-col"></div>').appendTo($parent);
		const $ch = $('<div class="sdb-group-head"></div>').appendTo($col);
		this._indicator(label, color).appendTo($ch);
		$('<span class="sdb-group-count"></span>').text(count).appendTo($ch);

		if (!drivers.length) {
			this._render_empty($col, empty_msg);
			return;
		}
		const $list = $('<div class="sdb-cards"></div>').appendTo($col);
		drivers.forEach((d) => {
			const $card = $('<div class="sdb-card"></div>').appendTo($list);
			$('<div class="sdb-card-title"></div>')
				.text(d.full_name || d.name)
				.appendTo($card);
			this._kv($card, __("Vehicle"), d.current_vehicle);
			this._kv($card, __("Project"), d.project);
		});
	}


	_render_requests_pane(pane) {
		const $body = this._make_pane(
			__("Open Transport Requests"),
			__("{0} open", [pane.open_count || 0])
		);
		const rows = pane.open || [];
		if (!rows.length) {
			this._render_empty($body, __("No open transport requests."));
			return;
		}
		const $list = $('<div class="sdb-cards"></div>').appendTo($body);
		rows.forEach((req) => {
			const $card = $('<div class="sdb-card"></div>').appendTo($list);
			const $head = $('<div class="sdb-card-head"></div>').appendTo($card);
			$('<span class="sdb-card-title"></span>').text(req.name).appendTo($head);
			this._indicator(__(req.status), "blue").appendTo($head);

			this._kv($card, __("Type"), req.request_type ? __(req.request_type) : null);
			this._kv(
				$card,
				__("Service Line"),
				req.service_line ? __(req.service_line) : null
			);
			this._kv($card, __("Project"), req.project);
			const route = [req.from_location, req.to_location || req.destination]
				.filter(Boolean)
				.join(" → ");
			this._kv($card, __("Route"), route || null);
			this._kv($card, __("Pickup"), req.pickup_datetime);
			const pax = req.passenger_count || req.worker_count;
			if (pax) this._kv($card, __("Passengers"), pax);
		});
	}
}
