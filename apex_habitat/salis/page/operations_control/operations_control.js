// [#odtona]

frappe.pages["operations-control"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Fleet Control"),
		single_column: true,
	});
	new FleetControl(page).setup();
};

const STATUS_COLOR = {
	Active: "green",
	Stopped: "orange",
	"Under Maintenance": "red",
	Released: "gray",
};

class FleetControl {
	constructor(page) {
		this.page = page;
		this.data = { vehicles: [], summary: null, offices: [], projects: [], statuses: [] };
		this.filters = { status: "", rental_office: "", project: "", search: "" };
		this.view = "cards";
	}

	setup() {
		this.$root = $('<div class="fc-root"></div>').appendTo(this.page.main);
		this.$progress = $('<div class="fc-progress"></div>').appendTo(this.$root);
		this.$summary = $('<div class="fc-summary"></div>').appendTo(this.$root);
		this.$controls = $('<div class="fc-controls"></div>').appendTo(this.$root);
		this.$body = $('<div class="fc-body"></div>').appendTo(this.$root);
		this.$grid = $('<div class="fc-grid"></div>').appendTo(this.$body);
		this.$drawer = $('<div class="fc-drawer"></div>').appendTo(this.$body);

		this.page.set_primary_action(__("Refresh"), () => this.refresh(), "refresh");
		this.page.add_button(__("Export CSV"), () => this.export_csv(), { icon: "download" });
		this.page.add_button(__("Cards / Table"), () => this.toggle_view());

		this._build_controls();
		this._render_skeleton();
		this.refresh();
	}

	_build_controls() {
		this.$controls.empty();
		this.$status = this._select(__("Status"), () => this._on_filter());
		this.$office = this._select(__("Rental Office"), () => this._on_filter());
		this.$project = this._select(__("Project"), () => this._on_filter());
		this.$search = $(
			`<input type="text" class="form-control input-sm fc-search" placeholder="${__("Search plate or category")}">`
		).appendTo(this.$controls);
		this.$search.on(
			"input",
			frappe.utils.debounce(() => {
				this.filters.search = this.$search.val();
				this.refresh();
			}, 350)
		);
	}

	_select(label, on_change) {
		const $wrap = $('<span class="fc-filter"></span>').appendTo(this.$controls);
		$(`<label>${frappe.utils.escape_html(label)}</label>`).appendTo($wrap);
		const $sel = $('<select class="form-control input-sm"></select>').appendTo($wrap);
		$sel.on("change", on_change);
		return $sel;
	}

	_fill_select($sel, values, current) {
		$sel.empty();
		$('<option value=""></option>').text(__("All")).appendTo($sel);
		(values || []).forEach((v) => {
			const $o = $("<option></option>").attr("value", v).text(v);
			if (v === current) $o.attr("selected", "selected");
			$o.appendTo($sel);
		});
	}

	_on_filter() {
		this.filters.status = this.$status.val();
		this.filters.rental_office = this.$office.val();
		this.filters.project = this.$project.val();
		this.refresh();
	}

	refresh() {
		this._set_loading(true);
		frappe.call({
			method: "apex_habitat.salis.api.operations_control.get_fleet",
			args: { ...this.filters },
			callback: (r) => {
				if (!r || !r.message) return;
				this.data = r.message;
				this._fill_select(this.$status, this.data.statuses, this.filters.status);
				this._fill_select(this.$office, this.data.offices, this.filters.rental_office);
				this._fill_select(this.$project, this.data.projects, this.filters.project);
				this._render_summary();
				this._render();
			},
			always: () => this._set_loading(false),
		});
	}

	// Disable Refresh + show the top progress bar while a fetch is in flight (no blank screen, no double-click).
	_set_loading(active) {
		this.$progress.toggleClass("fc-progress-on", active);
		if (this.page.btn_primary) this.page.btn_primary.prop("disabled", active);
	}

	// Placeholder chips + cards shown on first load, before get_fleet returns.
	_render_skeleton() {
		this.$summary.empty();
		for (let i = 0; i < 4; i++) {
			$('<div class="fc-chip fc-skeleton"></div>').appendTo(this.$summary);
		}
		this.$grid.empty();
		for (let i = 0; i < 6; i++) {
			$('<div class="fc-card fc-skeleton"></div>').appendTo(this.$grid);
		}
	}

	_render_summary() {
		this.$summary.empty();
		const s = this.data.summary || { by_status: {}, total: 0, open_incidents: 0 };
		const chip = (label, value, cls) => {
			const $c = $('<div class="fc-chip"></div>').addClass(cls || "").appendTo(this.$summary);
			$('<div class="fc-chip-val"></div>').text(value).appendTo($c);
			$('<div class="fc-chip-lbl"></div>').text(label).appendTo($c);
		};
		chip(__("Total"), s.total, "fc-chip-total");
		(this.data.statuses || []).forEach((st) =>
			chip(__(st), s.by_status[st] || 0, "fc-chip-" + (STATUS_COLOR[st] || "gray"))
		);
		chip(__("Open Incidents"), s.open_incidents || 0, "fc-chip-red");
	}

	toggle_view() {
		this.view = this.view === "cards" ? "table" : "cards";
		this._render();
	}

	_render() {
		this.$grid.empty();
		this.$grid.toggleClass("fc-grid-table", this.view === "table");
		if (!this.data.vehicles.length) {
			$('<div class="fc-empty text-muted"></div>').text(__("No vehicles match the current filters.")).appendTo(this.$grid);
			return;
		}
		if (this.view === "table") this._render_table();
		else this.data.vehicles.forEach((v) => this._render_card(v));
	}

	_render_card(v) {
		const color = STATUS_COLOR[v.status] || "gray";
		const $c = $('<div class="fc-card"></div>').addClass("fc-accent-" + color);
		$c.on("click", () => this.open_detail(v));
		const $head = $('<div class="fc-card-head"></div>').appendTo($c);
		$('<div class="fc-plate"></div>').text(v.plate_number || v.name).appendTo($head);
		$('<span class="indicator-pill"></span>').addClass(color).text(__(v.status || "")).appendTo($head);
		const $meta = $('<div class="fc-card-meta"></div>').appendTo($c);
		$('<div></div>').text(v.vehicle_category || __("No category")).appendTo($meta);
		$('<div class="text-muted"></div>')
			.text([v.rental_office, v.project].filter(Boolean).join(" · ") || "—")
			.appendTo($meta);
		const $foot = $('<div class="fc-card-foot"></div>').appendTo($c);
		$('<div></div>').text("👤 " + (v.current_driver_name || __("Unassigned"))).appendTo($foot);
		if (v.open_incidents) {
			$('<span class="indicator-pill red fc-inc"></span>')
				.text(__("{0} open", [v.open_incidents]))
				.appendTo($foot);
		}
		$c.appendTo(this.$grid);
	}

	_render_table() {
		const cols = [
			["Plate", "plate_number"], ["Category", "vehicle_category"], ["Status", "status"],
			["Driver", "current_driver_name"], ["Office", "rental_office"], ["Project", "project"],
			["Open Incidents", "open_incidents"],
		];
		const $t = $('<table class="table table-bordered fc-table"></table>').appendTo(this.$grid);
		const $hr = $("<tr></tr>").appendTo($("<thead></thead>").appendTo($t));
		cols.forEach((c) => $("<th></th>").text(__(c[0])).appendTo($hr));
		const $tb = $("<tbody></tbody>").appendTo($t);
		this.data.vehicles.forEach((v) => {
			const $r = $("<tr></tr>").appendTo($tb);
			$r.on("click", () => this.open_detail(v));
			cols.forEach((c) => $("<td></td>").text(v[c[1]] == null ? "" : String(v[c[1]])).appendTo($r));
		});
	}

	open_detail(v) {
		this.$drawer.addClass("fc-open").empty();
		const $close = $('<button class="btn btn-xs btn-default fc-close"></button>').text(__("Close"));
		$close.on("click", () => this.$drawer.removeClass("fc-open"));
		const $head = $('<div class="fc-drawer-head"></div>').appendTo(this.$drawer);
		$('<div class="fc-drawer-title"></div>').text(v.plate_number || v.name).appendTo($head);
		$close.appendTo($head);
		const $open = $('<a class="btn btn-xs btn-primary fc-form-link"></a>').text(__("Open Vehicle"));
		$open.attr("href", "/app/salis-vehicle/" + encodeURIComponent(v.name)).appendTo($head);
		// [#kv4vij]
		["Vehicle Stop", "Vehicle Incident", "Vehicle Assignment"].forEach((doctype) => {
			const $a = $('<button class="btn btn-xs btn-default fc-action"></button>').text("+ " + __(doctype));
			$a.on("click", () => {
				frappe.route_options = { vehicle: v.name };
				frappe.new_doc(doctype);
			});
			$a.appendTo($head);
		});
		const $body = $('<div class="fc-drawer-body text-muted"></div>').text(__("Loading…")).appendTo(this.$drawer);

		frappe.call({
			method: "apex_habitat.salis.api.operations_control.get_vehicle_detail",
			args: { vehicle: v.name },
			callback: (r) => {
				if (!r || !r.message) return;
				$body.empty().removeClass("text-muted");
				this._detail_fields($body, r.message.vehicle);
				this._detail_list($body, __("Recent Incidents"), r.message.incidents,
					(x) => `${x.incident_date || ""} · ${__(x.incident_type || "")} · ${__(x.status || "")}`);
				this._detail_list($body, __("Recent Assignments"), r.message.assignments,
					(x) => `${x.start_date || ""} → ${x.end_date || __("open")} · ${x.driver || ""}`);
			},
		});
	}

	_detail_fields($body, d) {
		const rows = [
			["Status", d.status], ["Category", d.vehicle_category], ["Driver", d.current_driver_name],
			["Office", d.rental_office], ["Project", d.project], ["Ownership", d.ownership],
			["Odometer", d.odometer], ["Planned Fuel", d.planned_fuel_grade],
			["Compliance", d.compliance_status], ["Next Expiry", d.next_expiry_date],
		];
		const $dl = $('<div class="fc-dl"></div>').appendTo($body);
		rows.forEach(([k, val]) => {
			if (val == null || val === "") return;
			const $row = $('<div class="fc-dl-row"></div>').appendTo($dl);
			$('<div class="fc-dl-k"></div>').text(__(k)).appendTo($row);
			$('<div class="fc-dl-v"></div>').text(String(val)).appendTo($row);
		});
	}

	_detail_list($body, title, items, fmt) {
		$('<div class="fc-drawer-sub"></div>').text(title).appendTo($body);
		if (!items || !items.length) {
			$('<div class="text-muted small"></div>').text(__("None.")).appendTo($body);
			return;
		}
		const $ul = $('<ul class="fc-list"></ul>').appendTo($body);
		items.forEach((x) => $("<li></li>").text(fmt(x)).appendTo($ul));
	}

	export_csv() {
		const cols = [
			["Plate", "plate_number"], ["Category", "vehicle_category"], ["Status", "status"],
			["Driver", "current_driver_name"], ["Office", "rental_office"], ["Project", "project"],
			["Ownership", "ownership"], ["Odometer", "odometer"], ["Open Incidents", "open_incidents"],
		];
		const rows = [cols.map((c) => c[0])];
		this.data.vehicles.forEach((v) => rows.push(cols.map((c) => v[c[1]] == null ? "" : v[c[1]])));
		const csv = rows
			.map((r) => r.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(","))
			.join("\n");
		const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8;" });
		const url = URL.createObjectURL(blob);
		const a = document.createElement("a");
		a.href = url;
		a.download = "fleet_control.csv";
		document.body.appendChild(a);
		a.click();
		document.body.removeChild(a);
		URL.revokeObjectURL(url);
		frappe.show_alert({ message: __("Exported {0} vehicles", [this.data.vehicles.length]), indicator: "green" });
	}
}
