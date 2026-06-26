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

// Compliance states that warrant a card flag, with the indicator colour.
const COMPLIANCE_FLAG = { "Expiring Soon": "orange", Expired: "red" };

// Open-alert severities, most-severe first — drives the strip order, the card
// corner badge colour, and the risk sort weighting.
const SEVERITY_ORDER = ["Critical", "Warning", "Info"];
const SEVERITY_RANK = { Critical: 3, Warning: 2, Info: 1 };

// Persisted-filter key for frappe.ui.users_settings (per-page supervisor scope).
const SETTINGS_KEY = "operations-control";
// Filters that round-trip through the route / saved settings.
const ROUTE_FILTERS = ["status", "rental_office", "project", "search", "compliance"];

// 'N days' / '1 day', localised, for embedding in the expiry phrase.
function _days_label(n) {
	return n === 1 ? __("1 day") : __("{0} days", [n]);
}

// Relative phrase for the next-expiry date: 'expires in N days' (future) or
// 'expired N days ago' (past), localised via __().
function _expiry_phrase(date) {
	if (!date) return "";
	const days = frappe.datetime.get_day_diff(date, frappe.datetime.get_today());
	if (days >= 0) return __("expires in {0}", [_days_label(days)]);
	return __("expired {0} ago", [_days_label(-days)]);
}

// Isolate an LTR token (plate, odometer, date, VEH-* id) inside RTL text so its
// digits/latin chars don't reorder. escape_html guards the value as we go to HTML.
function _bdi(value) {
	return `<bdi>${frappe.utils.escape_html(value == null ? "" : String(value))}</bdi>`;
}

class FleetControl {
	constructor(page) {
		this.page = page;
		this.data = { vehicles: [], summary: null, offices: [], projects: [], statuses: [], unscoped: false };
		this.filters = { status: "", rental_office: "", project: "", search: "", compliance: "" };
		// Off-board view filters: alerts_only (cards), sort key, active severity facet.
		this.alerts_only = false;
		this.sort = "risk";
		this.severity_filter = "";
		// Per-vehicle open alerts + strip summary, refreshed alongside the fleet.
		this.alerts = [];
		this.alerts_by_vehicle = {};
		this.alert_summary = { total: 0, by_severity: {} };
		this.view = "cards";
		this.selected_alerts = new Set();
	}

	setup() {
		this._restore_filters();
		this.$root = $('<div class="fc-root"></div>')
			.attr("dir", frappe.utils.is_rtl() ? "rtl" : "ltr")
			.appendTo(this.page.main);
		this.$progress = $('<div class="fc-progress"></div>').appendTo(this.$root);
		this.$strip = $('<div class="fc-alert-strip"></div>').appendTo(this.$root);
		this.$summary = $('<div class="fc-summary"></div>').appendTo(this.$root);
		// fc-sheet/-closed are inert above 768px; below it the bar becomes a bottom
		// sheet toggled by the Filters button.
		this.$controls = $('<div class="fc-controls fc-sheet fc-sheet-closed"></div>').appendTo(this.$root);
		this.$body = $('<div class="fc-body"></div>').appendTo(this.$root);
		this.$grid = $('<div class="fc-grid"></div>').appendTo(this.$body);
		this.$drawer = $('<div class="fc-drawer"></div>').appendTo(this.$body);

		this.page.set_primary_action(__("Refresh"), () => this.refresh(), "refresh");
		this.page.add_button(__("Cards / Table"), () => this.toggle_view("table"));
		this.page.add_button(__("Alert queue"), () => this.toggle_view("queue"));
		// Mobile-only Filters trigger for the bottom-sheet filter bar.
		this.$sheet_toggle = $(
			`<button class="btn btn-sm btn-default fc-sheet-toggle">${__("Filters")}</button>`
		)
			.on("click", () => this.$controls.toggleClass("fc-sheet-closed"))
			.insertBefore(this.$strip);

		this._build_controls();
		this._render_skeleton();
		this._subscribe_realtime();
		// Wait for the async saved-scope fetch (if any) so the first load opens to
		// the restored filters, then sync the controls to them.
		this.ready.then(() => {
			this._sync_controls();
			this.refresh();
		});
	}

	// Push the (possibly route/settings-restored) filter values back onto the inputs.
	_sync_controls() {
		if (this.$status) this.$status.val(this.filters.status || "");
		if (this.$office) this.$office.val(this.filters.rental_office || "");
		if (this.$project) this.$project.val(this.filters.project || "");
		if (this.$compliance) this.$compliance.val(this.filters.compliance || "");
		if (this.$search) this.$search.val(this.filters.search || "");
	}

	// Live-patch the strip/queue when the scheduler raises/resolves an alert on a
	// project in view, so the board never goes stale without a manual Refresh.
	// Server side (publish_realtime in salis/tasks.py) is the integrator's to add.
	_subscribe_realtime() {
		const reload = frappe.utils.debounce(() => this._refresh_alerts(), 1500);
		frappe.realtime.on("operations_alert", (data) => {
			const proj = this.filters.project;
			if (proj && data && data.project && data.project !== proj) return;
			reload();
		});
	}

	_build_controls() {
		this.$controls.empty();
		this.$status = this._select(__("Status"), () => this._on_filter());
		this.$office = this._select(__("Rental Office"), () => this._on_filter());
		this.$project = this._select(__("Project"), () => this._on_filter());
		// Compliance facet (Compliant/Expiring/Expired) — applied server-side by get_fleet.
		this.$compliance = this._select(__("Compliance"), () => this._on_filter());
		this._fill_select(this.$compliance, ["Compliant", "Expiring Soon", "Expired"], this.filters.compliance);
		this.$search = $(
			`<input type="text" class="form-control input-sm fc-search" placeholder="${__("Search plate or category")}">`
		).appendTo(this.$controls);
		this.$search.val(this.filters.search || "");
		this.$search.on(
			"input",
			frappe.utils.debounce(() => {
				this.filters.search = this.$search.val();
				this.refresh();
			}, 350)
		);
		// 'Alerts only' narrows the card board to vehicles with an open alert.
		const $alerts_wrap = $('<span class="fc-filter"></span>').appendTo(this.$controls);
		$(`<label>${frappe.utils.escape_html(__("Alerts only"))}</label>`).appendTo($alerts_wrap);
		this.$alerts_only = $('<input type="checkbox" class="fc-alerts-only">')
			.prop("checked", this.alerts_only)
			.on("change", () => {
				this.alerts_only = this.$alerts_only.prop("checked");
				this._render();
			})
			.appendTo($alerts_wrap);
		// Sort control: risk-desc (default) vs plate-asc.
		this.$sort = this._select(__("Sort"), () => {
			this.sort = this.$sort.val() || "risk";
			this._render();
		});
		this.$sort.empty();
		$('<option value="risk"></option>').text(__("Risk")).appendTo(this.$sort);
		$('<option value="plate"></option>').text(__("Plate")).appendTo(this.$sort);
		this.$sort.val(this.sort);
		// Live '{n} vehicles' count, right-aligned in the filter bar.
		this.$count = $('<span class="fc-result-count"></span>').appendTo(this.$controls);
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
		this.filters.compliance = this.$compliance.val();
		this.refresh();
	}

	// Restore the active filter set on load. The URL route_options win (a shared /
	// bookmarked link reopens identically). Otherwise this user's saved per-page
	// scope is fetched async and applied so a supervisor reopens to their own
	// project; the fetch resolves before the first refresh via this.ready.
	_restore_filters() {
		const opts = frappe.route_options || {};
		let from_route = false;
		ROUTE_FILTERS.forEach((k) => {
			if (opts[k] != null && opts[k] !== "") {
				this.filters[k] = String(opts[k]);
				from_route = true;
			}
		});
		frappe.route_options = null;
		if (from_route) {
			this.ready = Promise.resolve();
			return;
		}
		this.ready = frappe.model.user_settings
			.get(SETTINGS_KEY)
			.then((s) => {
				const saved = (s || {}).filters;
				if (saved) ROUTE_FILTERS.forEach((k) => { if (saved[k]) this.filters[k] = saved[k]; });
			})
			.catch(() => {});
	}

	// Persist the active filters two ways: into the page route (shareable URL,
	// survives refresh) and into this user's per-page settings (their own scope).
	_persist_filters() {
		const active = {};
		ROUTE_FILTERS.forEach((k) => { if (this.filters[k]) active[k] = this.filters[k]; });
		frappe.model.user_settings.save(SETTINGS_KEY, "filters", active);
		// Reflect the filters in the URL so a refresh / shared link reopens identically.
		const route = frappe.get_route() || [];
		const qs = frappe.utils.make_query_string(active);
		frappe.router.push_state("/" + ["app", route[1] || "operations-control"].join("/") + qs);
	}

	refresh() {
		this._set_loading(true);
		this._persist_filters();
		this._refresh_alerts();
		frappe.call({
			method: "apex_habitat.salis.api.operations_control.get_fleet",
			args: { ...this.filters },
			callback: (r) => {
				// A 200 with no payload is still a failure here: surface it, don't blank-swallow.
				if (!r || !r.message) {
					this._render_board_error(() => this.refresh());
					return;
				}
				this.data = r.message;
				this._fill_select(this.$status, this.data.statuses, this.filters.status);
				this._fill_select(this.$office, this.data.offices, this.filters.rental_office);
				this._fill_select(this.$project, this.data.projects, this.filters.project);
				this._render_summary();
				this._render();
			},
			error: (r) => this._render_board_error(() => this.refresh(), r),
			always: () => this._set_loading(false),
		});
	}

	// Pull the open-alert queue for the current project scope: one call feeds the
	// severity strip, the per-card corner badge and the alert queue view. Keeps the
	// alert axis a single source so the strip and the cards
	// can never disagree. A failure leaves the strip empty (the board still loads).
	_refresh_alerts() {
		frappe.call({
			method: "apex_habitat.salis.api.operations_alerts.get_open_alerts",
			args: { project: this.filters.project || undefined },
			callback: (r) => {
				const m = (r && r.message) || { alerts: [], summary: { total: 0, by_severity: {} } };
				this.alerts = m.alerts || [];
				this.alert_summary = m.summary || { total: 0, by_severity: {} };
				this.alerts_by_vehicle = {};
				this.alerts.forEach((a) => {
					if (!a.vehicle) return;
					(this.alerts_by_vehicle[a.vehicle] = this.alerts_by_vehicle[a.vehicle] || []).push(a);
				});
				this._render_strip();
				// Re-render so card badges / the queue reflect the fresh alert set.
				this._render();
			},
			error: () => {
				this.alerts = [];
				this.alert_summary = { total: 0, by_severity: {} };
				this.alerts_by_vehicle = {};
				this._render_strip();
			},
		});
	}

	// Highest open severity for a vehicle (Critical > Warning > Info), or null.
	_vehicle_top_severity(name) {
		const list = this.alerts_by_vehicle[name];
		if (!list || !list.length) return null;
		let best = null;
		list.forEach((a) => {
			if (!best || (SEVERITY_RANK[a.severity] || 0) > (SEVERITY_RANK[best] || 0)) best = a.severity;
		});
		return best;
	}

	// Render an error panel (with the server message) + Retry into a target element.
	_render_error($target, retry, r) {
		$target.empty();
		const $panel = $('<div class="fc-error"></div>').appendTo($target);
		$('<div class="fc-error-msg"></div>').text(this._error_text(r)).appendTo($panel);
		const $btn = $('<button class="btn btn-sm btn-default fc-error-retry"></button>')
			.text(__("Retry"))
			.appendTo($panel);
		$btn.on("click", () => retry());
	}

	// Best-effort human message from a failed frappe.call response. Rendered via .text() so it is auto-escaped.
	_error_text(r) {
		const raw = r && r._server_messages;
		if (raw) {
			try {
				const first = JSON.parse(raw)[0];
				const obj = typeof first === "string" ? JSON.parse(first) : first;
				const msg = obj && obj.message ? obj.message : first;
				if (msg) return String(msg).replace(/<[^>]*>/g, "").trim();
			} catch (e) {
				// fall through to the generic message
			}
		}
		return __("Could not load fleet data. Please try again.");
	}

	// Full-board error state: clears the summary skeleton/chips too.
	_render_board_error(retry, r) {
		this.$summary.empty();
		this.$grid.empty();
		this._render_error(this.$grid, retry, r);
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

	// Full-width severity strip. Each counter toggles the matching severity facet
	// on the board; an all-clear (zero open alerts) collapses to a calm message.
	_render_strip() {
		this.$strip.empty();
		const sev = (this.alert_summary && this.alert_summary.by_severity) || {};
		const total = (this.alert_summary && this.alert_summary.total) || 0;
		if (!total) {
			$('<div class="fc-alert-strip-clear"></div>')
				.text(__("All clear — no open alerts"))
				.appendTo(this.$strip);
			return;
		}
		$('<span class="text-muted small"></span>').text(__("Alerts")).appendTo(this.$strip);
		SEVERITY_ORDER.forEach((s) => {
			const n = sev[s] || 0;
			if (!n) return;
			const active = this.severity_filter === s;
			const $b = $('<button type="button" class="fc-sev-counter"></button>')
				.attr("aria-pressed", active ? "true" : "false")
				.appendTo(this.$strip);
			$('<span class="fc-sev-dot"></span>').addClass("fc-sev-" + s).appendTo($b);
			$('<span class="fc-sev-count"></span>').text(n).appendTo($b);
			$('<span></span>').text(__(s)).appendTo($b);
			// Toggle the severity facet; it narrows the queue and the card board.
			$b.on("click", () => {
				this.severity_filter = active ? "" : s;
				this._render_strip();
				this._render();
			});
		});
	}

	_render_summary() {
		this.$summary.empty();
		const s = this.data.summary || { by_status: {}, total: 0, open_incidents: 0 };
		// Each chip toggles the board filter that matches it (status / incidents /
		// compliance), so the summary is a one-click facet, not a static number.
		const chip = (label, value, cls, on_click, pressed) => {
			const $c = $('<div class="fc-chip"></div>').addClass(cls || "").appendTo(this.$summary);
			$('<div class="fc-chip-val"></div>').text(value).appendTo($c);
			$('<div class="fc-chip-lbl"></div>').text(label).appendTo($c);
			if (on_click) {
				$c.attr("aria-pressed", pressed ? "true" : "false").on("click", on_click);
			}
			return $c;
		};
		chip(__("Total"), s.total, "fc-chip-total", () => this._clear_filters());
		(this.data.statuses || []).forEach((st) =>
			chip(
				__(st),
				s.by_status[st] || 0,
				"fc-chip-" + (STATUS_COLOR[st] || "gray"),
				() => this._toggle_status(st),
				this.filters.status === st
			)
		);
		chip(
			__("Open Incidents"),
			s.open_incidents || 0,
			"fc-chip-red",
			() => { this.alerts_only = false; this.$alerts_only && this.$alerts_only.prop("checked", false); this._toggle_incidents(); },
			this._incidents_only
		);
		chip(
			__("Compliance at risk"),
			s.compliance_at_risk || 0,
			"fc-chip-orange",
			() => this._toggle_compliance_risk(),
			this.filters.compliance === "Expired" || this.filters.compliance === "Expiring Soon"
		);
		chip(__("Stopped > {0} days", [s.stopped_over_days || 0]), s.stopped_over_n || 0, "fc-chip-orange");
	}

	// Chip → filter toggles. Each flips its facet and refetches.
	_toggle_status(st) {
		this.filters.status = this.filters.status === st ? "" : st;
		this._sync_controls();
		this.refresh();
	}
	_toggle_compliance_risk() {
		// Cycle the compliance facet between 'at risk' (Expired) and off.
		const on = this.filters.compliance === "Expired" || this.filters.compliance === "Expiring Soon";
		this.filters.compliance = on ? "" : "Expired";
		this._sync_controls();
		this.refresh();
	}
	// Open-incidents is a client-side card narrowing (no server param), like alerts-only.
	_toggle_incidents() {
		this._incidents_only = !this._incidents_only;
		this._render();
	}

	// Cycle a named view: clicking the same button returns to cards.
	toggle_view(target) {
		this.view = this.view === target ? "cards" : target;
		this._render();
	}

	// Order the cards: risk-desc (open critical alerts → expired compliance →
	// Stopped → rest) by default, or plate-asc when the sort control is switched.
	_sort_vehicles(vehicles) {
		if (this.sort === "plate") {
			return vehicles.slice().sort((a, b) =>
				String(a.plate_number || a.name).localeCompare(String(b.plate_number || b.name))
			);
		}
		const risk = (v) => {
			const sev = this._vehicle_top_severity(v.name);
			let score = 0;
			if (sev === "Critical") score += 1000;
			else if (sev === "Warning") score += 500;
			else if (sev === "Info") score += 100;
			if (v.compliance_status === "Expired") score += 60;
			else if (v.compliance_status === "Expiring Soon") score += 30;
			if (v.status === "Stopped") score += 10;
			score += (v.open_incidents || 0);
			return score;
		};
		return vehicles.slice().sort((a, b) => risk(b) - risk(a));
	}

	// Apply the client-side card facets (alerts-only, open-incidents, active severity).
	_visible_vehicles() {
		let list = this.data.vehicles || [];
		if (this.alerts_only) list = list.filter((v) => this.alerts_by_vehicle[v.name]);
		if (this._incidents_only) list = list.filter((v) => v.open_incidents);
		if (this.severity_filter)
			list = list.filter((v) => this._vehicle_top_severity(v.name) === this.severity_filter);
		return this._sort_vehicles(list);
	}

	_render() {
		// The alert-queue view replaces the card/table grid entirely.
		if (this.view === "queue") {
			this._update_count(this.alerts.length, true);
			this._render_queue();
			return;
		}
		this.$grid.empty();
		this.$grid.toggleClass("fc-grid-table", this.view === "table");
		const vehicles = this._visible_vehicles();
		this._update_count(vehicles.length, false);
		if (!vehicles.length) {
			this._render_empty();
			return;
		}
		if (this.view === "table") this._render_table(vehicles);
		else vehicles.forEach((v) => this._render_card(v));
	}

	// Live count in the filter bar: '{n} vehicles' (or alerts in the queue view).
	_update_count(n, is_alerts) {
		if (!this.$count) return;
		this.$count.text(is_alerts ? __("{0} alerts", [n]) : __("{0} vehicles", [n]));
	}

	// Two distinct zero-row states: a scope gap (scoped user with no fleet project)
	// vs an over-filtered no-match. unscoped guards an empty-project oversight user.
	_render_empty() {
		if (!this.data.unscoped && (this.data.projects || []).length === 0) {
			const $e = $('<div class="fc-empty fc-empty-scope"></div>').appendTo(this.$grid);
			$('<div class="fc-empty-title"></div>')
				.text(__("You have no fleet project assigned"))
				.appendTo($e);
			$('<div class="fc-empty-hint text-muted"></div>')
				.text(__("Contact your Fleet Manager to be granted a project."))
				.appendTo($e);
			return;
		}
		const $e = $('<div class="fc-empty fc-empty-filtered text-muted"></div>').appendTo(this.$grid);
		$('<div></div>').text(__("No vehicles match the current filters.")).appendTo($e);
		// Escape hatch out of an over-filtered board: reset every filter + refetch.
		const $clear = $('<button class="btn btn-sm btn-default fc-clear-filters"></button>')
			.text(__("Clear filters"))
			.appendTo($e);
		$clear.on("click", () => this._clear_filters());
	}

	// Reset all filters (status/office/project/search) and reload the board.
	_clear_filters() {
		this.filters = { status: "", rental_office: "", project: "", search: "" };
		if (this.$status) this.$status.val("");
		if (this.$office) this.$office.val("");
		if (this.$project) this.$project.val("");
		if (this.$search) this.$search.val("");
		this.refresh();
	}

	_render_card(v) {
		const color = STATUS_COLOR[v.status] || "gray";
		const $c = $('<div class="fc-card"></div>').addClass("fc-accent-" + color);
		$c.on("click", () => this.open_detail(v));
		// Top-corner severity badge when the vehicle has open alerts, coloured by the
		// highest open severity (Critical red > Warning orange > Info blue).
		const top_sev = this._vehicle_top_severity(v.name);
		if (top_sev) {
			const n = (this.alerts_by_vehicle[v.name] || []).length;
			$('<span class="fc-card-sev"></span>')
				.addClass("fc-sev-" + top_sev)
				.attr("title", __(top_sev))
				.text(n)
				.appendTo($c);
		}
		const $head = $('<div class="fc-card-head"></div>').appendTo($c);
		// Plate / VEH-* id is LTR: <bdi> keeps it from reversing inside an RTL card.
		$('<div class="fc-plate"></div>').html(_bdi(v.plate_number || v.name)).appendTo($head);
		$('<span class="indicator-pill"></span>').addClass(color).text(__(v.status || "")).appendTo($head);
		const $meta = $('<div class="fc-card-meta"></div>').appendTo($c);
		$('<div></div>').text(v.vehicle_category || __("No category")).appendTo($meta);
		// Office·project as separate nodes with a CSS dot separator — no string glue,
		// so the middot doesn't strand between LTR/RTL tokens under RTL.
		const $op = $('<div class="text-muted fc-sep-dot"></div>').appendTo($meta);
		const parts = [v.rental_office, v.project].filter(Boolean);
		if (!parts.length) $('<span></span>').text("—").appendTo($op);
		else parts.forEach((p) => $("<span></span>").text(p).appendTo($op));
		const $foot = $('<div class="fc-card-foot"></div>').appendTo($c);
		// Driver: an icon node + a text node, not an emoji glued onto the string.
		const $driver = $('<div class="fc-driver"></div>').appendTo($foot);
		$('<span class="fc-driver-icon"></span>')
			.html(frappe.utils.icon("users", "sm"))
			.appendTo($driver);
		$('<span class="fc-driver-name"></span>')
			.text(v.current_driver_name || __("Unassigned"))
			.appendTo($driver);
		if (v.open_incidents) {
			$('<span class="indicator-pill red fc-inc"></span>')
				.text(__("{0} open", [v.open_incidents]))
				.appendTo($foot);
		}
		const flag = COMPLIANCE_FLAG[v.compliance_status];
		if (flag) {
			const rel = _expiry_phrase(v.next_expiry_date);
			const label = rel ? __(v.compliance_status) + " · " + rel : __(v.compliance_status);
			$('<span class="indicator-pill fc-compliance"></span>')
				.addClass(flag)
				.text(label)
				.appendTo($foot);
		}
		$c.appendTo(this.$grid);
	}

	_render_table(vehicles) {
		const cols = [
			["Plate", "plate_number"], ["Category", "vehicle_category"], ["Status", "status"],
			["Driver", "current_driver_name"], ["Office", "rental_office"], ["Project", "project"],
			["Open Incidents", "open_incidents"],
		];
		const $t = $('<table class="table table-bordered fc-table"></table>').appendTo(this.$grid);
		const $hr = $("<tr></tr>").appendTo($("<thead></thead>").appendTo($t));
		cols.forEach((c) => $("<th></th>").text(__(c[0])).appendTo($hr));
		const $tb = $("<tbody></tbody>").appendTo($t);
		(vehicles || this.data.vehicles).forEach((v) => {
			const $r = $("<tr></tr>").appendTo($tb);
			$r.on("click", () => this.open_detail(v));
			cols.forEach((c) => $("<td></td>").text(v[c[1]] == null ? "" : String(v[c[1]])).appendTo($r));
		});
	}

	// Alert-queue view: open Operations Alerts, severity-sorted, with inline
	// Acknowledge/Resolve and checkbox multi-select + a single bulk-acknowledge.
	_render_queue() {
		this.$grid.empty().removeClass("fc-grid-table");
		const sorted = (this.alerts || [])
			.filter((a) => !this.severity_filter || a.severity === this.severity_filter)
			.slice()
			.sort((a, b) => (SEVERITY_RANK[b.severity] || 0) - (SEVERITY_RANK[a.severity] || 0));
		if (!sorted.length) {
			const $e = $('<div class="fc-empty text-muted"></div>').appendTo(this.$grid);
			$('<div></div>').text(__("All clear — no open alerts")).appendTo($e);
			return;
		}
		// Bulk bar: select-all + acknowledge the currently selected ids in one call.
		const $bulk = $('<div class="fc-queue-bulk"></div>').appendTo(this.$grid);
		const $all = $('<input type="checkbox">')
			.on("change", () => {
				this.selected_alerts = $all.prop("checked")
					? new Set(sorted.filter((a) => a.status === "Open").map((a) => a.name))
					: new Set();
				this._render_queue();
			})
			.appendTo($('<label class="fc-queue-bulk-all"></label>').appendTo($bulk));
		$('<span></span>').text(__("Select all")).appendTo($all.parent());
		$('<button class="btn btn-xs btn-default"></button>')
			.text(__("Acknowledge selected ({0})", [this.selected_alerts.size]))
			.prop("disabled", !this.selected_alerts.size)
			.on("click", () => this._bulk_acknowledge())
			.appendTo($bulk);

		const $wrap = $('<div class="fc-queue"></div>').appendTo(this.$grid);
		sorted.forEach((a) => this._render_queue_row(a, $wrap));
	}

	_render_queue_row(a, $wrap) {
		const $row = $('<div class="fc-queue-row"></div>')
			.addClass("fc-sev-row-" + a.severity)
			.appendTo($wrap);
		if (a.status === "Open") {
			$('<input type="checkbox" class="fc-queue-pick">')
				.prop("checked", this.selected_alerts.has(a.name))
				.on("change", (e) => {
					if (e.target.checked) this.selected_alerts.add(a.name);
					else this.selected_alerts.delete(a.name);
					this._render_queue();
				})
				.appendTo($row);
		}
		const $main = $('<div class="fc-queue-main"></div>').appendTo($row);
		$('<div class="fc-queue-msg"></div>').text(a.message || __(a.alert_type || "")).appendTo($main);
		// Meta line: plate · type · age · status, dot-separated nodes (RTL-safe).
		const $meta = $('<div class="fc-queue-meta fc-sep-dot"></div>').appendTo($main);
		if (a.plate_number) $('<span></span>').html(_bdi(a.plate_number)).appendTo($meta);
		$('<span></span>').text(__(a.alert_type || "")).appendTo($meta);
		if (a.raised_on)
			$('<span></span>').text(frappe.datetime.comment_when(a.raised_on)).appendTo($meta);
		$('<span></span>').text(__(a.status || "")).appendTo($meta);
		this._alert_actions(a, $('<div class="fc-queue-actions"></div>').appendTo($row));
	}

	// Inline Acknowledge (Open only) + Resolve buttons shared by the queue and the
	// drawer; both call the permission-gated server API and refresh the alert set.
	_alert_actions(a, $into) {
		if (a.status === "Open") {
			$('<button class="btn btn-xs btn-default"></button>')
				.text(__("Acknowledge"))
				.on("click", (e) => {
					e.stopPropagation();
					this._alert_action("acknowledge_alert", { name: a.name }, __("Alert acknowledged"));
				})
				.appendTo($into);
		}
		$('<button class="btn btn-xs btn-default"></button>')
			.text(__("Resolve"))
			.on("click", (e) => {
				e.stopPropagation();
				this._alert_action("resolve_alert", { name: a.name }, __("Alert resolved"));
			})
			.appendTo($into);
	}

	// Single-alert action (acknowledge/resolve), then re-pull the alert set.
	_alert_action(method, args, ok_msg) {
		frappe.call({
			method: "apex_habitat.salis.api.operations_alerts." + method,
			args,
			callback: (r) => {
				if (r && r.message && r.message.ok) {
					frappe.show_alert({ message: ok_msg, indicator: "green" });
					this._refresh_alerts();
				}
			},
		});
	}

	// Bulk-acknowledge the selected open alerts in one server call. The endpoint
	// re-checks write permission per alert server-side, so a row the user may not
	// act on is skipped rather than trusted from the client.
	_bulk_acknowledge() {
		const names = Array.from(this.selected_alerts);
		if (!names.length) return;
		frappe.call({
			method: "apex_habitat.salis.api.operations_alerts.bulk_acknowledge_alerts",
			args: { names },
			callback: (r) => {
				const n = (r && r.message && (r.message.acknowledged || []).length) || 0;
				frappe.show_alert({ message: __("{0} acknowledged", [n]), indicator: "green" });
				this.selected_alerts = new Set();
				this._refresh_alerts();
			},
		});
	}

	open_detail(v) {
		this.$drawer.addClass("fc-open").empty();
		const $close = $('<button class="btn btn-xs btn-default fc-close"></button>').text(__("Close"));
		$close.on("click", () => this.$drawer.removeClass("fc-open"));
		const $head = $('<div class="fc-drawer-head"></div>').appendTo(this.$drawer);
		// Plate / VEH-* id is LTR: <bdi> isolates it inside the RTL drawer header.
		$('<div class="fc-drawer-title"></div>').html(_bdi(v.plate_number || v.name)).appendTo($head);
		$close.appendTo($head);
		// Drawer actions are grouped by intent: open the record, then operate on this
		// vehicle (reassign / release), then create related records last.
		const $open = $('<a class="btn btn-xs btn-primary fc-form-link"></a>').text(__("Open Vehicle"));
		$open.attr("href", "/app/salis-vehicle/" + encodeURIComponent(v.name)).appendTo($head);

		// Reassign driver: a guided driver pick that ends the current assignment and
		// starts a new one server-side, instead of opening a blank Vehicle Assignment.
		const $reassign = $('<button class="btn btn-xs btn-default fc-action"></button>').text(
			__("Reassign driver")
		);
		$reassign.on("click", () => this.reassign_driver(v, $reassign));
		$reassign.appendTo($head);
		// Release back to service: closes the open Vehicle Stop natively (server side).
		if (v.status === "Stopped") {
			const $rel = $('<button class="btn btn-xs btn-default fc-action fc-release"></button>').text(
				__("Release vehicle")
			);
			$rel.on("click", () => this.release_vehicle(v, $rel));
			$rel.appendTo($head);
		}
		// [#kv4vij]
		["Vehicle Assignment", "Vehicle Stop", "Vehicle Incident"].forEach((doctype) => {
			const $a = $('<button class="btn btn-xs btn-default fc-action"></button>').text("+ " + __(doctype));
			$a.on("click", () => {
				frappe.route_options = { vehicle: v.name };
				frappe.new_doc(doctype);
			});
			$a.appendTo($head);
		});
		// Open alerts for this vehicle pinned at the top of the drawer, each with
		// inline Acknowledge/Resolve (server-side permission-gated).
		this._render_drawer_alerts(v);
		const $body = $('<div class="fc-drawer-body"></div>').appendTo(this.$drawer);
		this._load_detail(v, $body);
	}

	// Render the vehicle's open Operations Alerts at the top of the drawer.
	_render_drawer_alerts(v) {
		const list = (this.alerts_by_vehicle[v.name] || [])
			.slice()
			.sort((a, b) => (SEVERITY_RANK[b.severity] || 0) - (SEVERITY_RANK[a.severity] || 0));
		if (!list.length) return;
		const $wrap = $('<div class="fc-drawer-alerts"></div>').appendTo(this.$drawer);
		$('<div class="fc-drawer-sub"></div>').text(__("Alerts")).appendTo($wrap);
		list.forEach((a) => {
			const $a = $('<div class="fc-drawer-alert"></div>')
				.addClass("fc-sev-row-" + a.severity)
				.appendTo($wrap);
			const $top = $('<div class="fc-sep-dot"></div>').appendTo($a);
			$('<span></span>').text(__(a.severity)).appendTo($top);
			$('<span></span>').text(__(a.alert_type || "")).appendTo($top);
			$('<div class="small"></div>').text(a.message || "").appendTo($a);
			this._alert_actions(a, $('<div class="fc-drawer-alert-actions"></div>').appendTo($a));
		});
	}

	// Fetch the drawer detail; surface failures (incl. empty payload) with a Retry instead of leaving 'Loading…'.
	_load_detail(v, $body) {
		$body.empty().addClass("text-muted").text(__("Loading…"));
		frappe.call({
			method: "apex_habitat.salis.api.operations_control.get_vehicle_detail",
			args: { vehicle: v.name },
			callback: (r) => {
				if (!r || !r.message) {
					this._render_error($body.removeClass("text-muted"), () => this._load_detail(v, $body));
					return;
				}
				$body.empty().removeClass("text-muted");
				this._detail_fields($body, r.message.vehicle);
				// Master fields render immediately; the consolidated history loads under them.
				this._load_timeline(v, $body);
			},
			error: (r) =>
				this._render_error($body.removeClass("text-muted"), () => this._load_detail(v, $body), r),
		});
	}

	// One consolidated, date-sorted feed (incidents · stops · assignments · resolved
	// alerts) replacing the old separate Recent-Incidents / Recent-Assignments lists.
	_load_timeline(v, $body) {
		const $section = $('<div class="fc-drawer-timeline"></div>').appendTo($body);
		$('<div class="fc-drawer-sub"></div>').text(__("Timeline")).appendTo($section);
		const $loading = $('<div class="text-muted small"></div>').text(__("Loading…")).appendTo($section);
		frappe.call({
			method: "apex_habitat.salis.api.operations_control.get_vehicle_timeline",
			args: { vehicle: v.name },
			callback: (r) => {
				$loading.remove();
				const events = (r && r.message && r.message.events) || [];
				if (!events.length) {
					$('<div class="text-muted small"></div>').text(__("None.")).appendTo($section);
					return;
				}
				const $ul = $('<ul class="fc-list fc-timeline"></ul>').appendTo($section);
				events.forEach((e) => this._timeline_row(e, $("<li></li>").appendTo($ul)));
			},
			error: (r) => {
				$loading.remove();
				this._render_error($section, () => { $section.remove(); this._load_timeline(v, $body); }, r);
			},
		});
	}

	// Render one normalised timeline event. Each event kind contributes its own
	// dot-separated nodes; the leading label says what KIND of event this is so the
	// merged feed stays legible. Dates/ids are LTR (<bdi>) inside the RTL drawer.
	_timeline_row(e, $li) {
		$li.addClass("fc-sep-dot");
		const KIND = { incident: "Incident", stop: "Stop", assignment: "Assignment", alert: "Alert" };
		$('<span class="fc-timeline-kind"></span>').text(__(KIND[e.kind] || e.kind)).appendTo($li);
		if (e.date) $("<span></span>").html(_bdi(e.date)).appendTo($li);
		if (e.kind === "incident") {
			$("<span></span>").text(__(e.incident_type || "")).appendTo($li);
			if (e.status) $("<span></span>").text(__(e.status)).appendTo($li);
		} else if (e.kind === "stop") {
			$("<span></span>").text(__(e.stop_reason || "")).appendTo($li);
			if (e.driver) $("<span></span>").html(_bdi(e.driver)).appendTo($li);
		} else if (e.kind === "assignment") {
			if (e.driver) $("<span></span>").html(_bdi(e.driver)).appendTo($li);
			if (e.status) $("<span></span>").text(__(e.status)).appendTo($li);
		} else if (e.kind === "alert") {
			$("<span></span>").text(__(e.alert_type || "")).appendTo($li);
			if (e.severity) $("<span></span>").text(__(e.severity)).appendTo($li);
		}
	}

	_detail_fields($body, d) {
		// 3rd tuple flags an LTR value (odometer number / date) → wrapped in <bdi>
		// so digits don't reverse inside the RTL detail list.
		const rows = [
			["Status", d.status], ["Category", d.vehicle_category], ["Driver", d.current_driver_name],
			["Office", d.rental_office], ["Project", d.project], ["Ownership", d.ownership],
			["Odometer", d.odometer, true], ["Planned Fuel", d.planned_fuel_grade],
			["Compliance", d.compliance_status], ["Next Expiry", d.next_expiry_date, true],
		];
		const $dl = $('<div class="fc-dl"></div>').appendTo($body);
		rows.forEach(([k, val, ltr]) => {
			if (val == null || val === "") return;
			const $row = $('<div class="fc-dl-row"></div>').appendTo($dl);
			$('<div class="fc-dl-k"></div>').text(__(k)).appendTo($row);
			const $v = $('<div class="fc-dl-v"></div>').appendTo($row);
			if (ltr) $v.html(_bdi(val));
			else $v.text(String(val));
		});
	}

	// Confirm, then close the vehicle's open stop on the server and refresh the board.
	release_vehicle(v, $btn) {
		frappe.confirm(__("Release {0} back to service?", [v.plate_number || v.name]), () => {
			$btn.prop("disabled", true);
			frappe.call({
				method: "apex_habitat.salis.api.operations_control.release_vehicle",
				args: { vehicle: v.name },
				callback: (r) => {
					if (r && r.message && r.message.ok) {
						frappe.show_alert({ message: __("Vehicle released"), indicator: "green" });
						this.$drawer.removeClass("fc-open");
						this.refresh();
					}
				},
				error: () => $btn.prop("disabled", false),
			});
		});
	}

	// Guided reassign: pick a Salis Driver, then end the current assignment and
	// start a new one server-side (no blank Vehicle Assignment form).
	reassign_driver(v, $btn) {
		frappe.prompt(
			[
				{
					fieldname: "driver",
					fieldtype: "Link",
					options: "Salis Driver",
					label: __("New driver"),
					reqd: 1,
				},
			],
			({ driver }) => {
				$btn.prop("disabled", true);
				frappe.call({
					method: "apex_habitat.salis.api.operations_control.reassign_driver",
					args: { vehicle: v.name, driver },
					callback: (r) => {
						if (r && r.message && r.message.ok) {
							frappe.show_alert({ message: __("Driver reassigned"), indicator: "green" });
							this.$drawer.removeClass("fc-open");
							this.refresh();
						}
					},
					error: () => $btn.prop("disabled", false),
				});
			},
			__("Reassign driver"),
			__("Reassign")
		);
	}
}
