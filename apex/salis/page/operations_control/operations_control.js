// Copyright (c) 2026, afmcoltd

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

const COMPLIANCE_FLAG = { "Expiring Soon": "orange", Expired: "red" };

const SEVERITY_ORDER = ["Critical", "Warning", "Info"];
const SEVERITY_RANK = { Critical: 3, Warning: 2, Info: 1 };

const SETTINGS_KEY = "operations-control";
const ROUTE_FILTERS = ["status", "rental_office", "project", "search", "compliance"];
const COMPLIANCE_OPTIONS = ["Compliant", "Expiring Soon", "Expired"];

function _empty_filters() {
	return ROUTE_FILTERS.reduce((acc, k) => {
		acc[k] = "";
		return acc;
	}, {});
}

const SNOOZE_PRESETS = [
	["tomorrow", "Tomorrow"],
	["2d", "In 2 days"],
	["1w", "In a week"],
];

function _days_label(n) {
	return n === 1 ? __("1 day") : __("{0} days", [n]);
}

function _expiry_phrase(date) {
	if (!date) return "";
	const days = frappe.datetime.get_day_diff(date, frappe.datetime.get_today());
	if (days >= 0) return __("expires in {0}", [_days_label(days)]);
	return __("expired {0} ago", [_days_label(-days)]);
}

function _bdi(value) {
	return `<bdi>${frappe.utils.escape_html(value == null ? "" : String(value))}</bdi>`;
}

const FC_ACCENT = { green: "var(--green-500)", orange: "var(--orange-500)", red: "var(--red-500)", gray: "var(--gray-400)" };
const FC_SEV_COLOR = { Critical: "var(--red-500)", Warning: "var(--orange-500)", Info: "var(--blue-500)" };
const FC = {
	progress: "height:3px;margin-block-end:8px;border-radius:3px;overflow:hidden;background:transparent;",
	progress_on: "background:var(--gray-200);",
	banner_on:
		"display:flex;align-items:center;gap:10px;margin-block-end:12px;padding:6px 12px;border-radius:var(--border-radius-md,8px);background:var(--control-bg);font-size:var(--text-sm,13px);",
	summary: "display:flex;flex-wrap:wrap;gap:10px;margin-block-end:14px;align-items:stretch;",
	chip:
		"flex:1 1 120px;min-inline-size:110px;background:var(--card-bg);border:1px solid var(--border-color);border-block-start:3px solid var(--gray-400);border-radius:var(--border-radius-md,8px);padding:10px 14px;",
	chip_pressed: "outline:2px solid var(--primary);outline-offset:-2px;",
	chip_val: "font-size:22px;font-weight:700;line-height:1.1;",
	chip_lbl: "font-size:11px;color:var(--text-muted);",
	controls: "display:flex;flex-wrap:wrap;align-items:flex-end;gap:10px;margin-block-end:14px;",
	filter: "display:flex;flex-direction:column;gap:2px;font-size:var(--text-sm,12px);",
	search: "min-inline-size:180px;",
	result_count: "font-size:12px;color:var(--text-muted);margin-inline-start:auto;align-self:center;",
	body: "display:flex;gap:14px;align-items:flex-start;",
	grid: "flex:1 1 auto;display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px;",
	card:
		"position:relative;background:var(--card-bg);border:1px solid var(--border-color);border-inline-start:4px solid var(--gray-300);border-radius:var(--border-radius-md,8px);padding:12px;cursor:pointer;",
	card_sev:
		"position:absolute;inset-block-start:8px;inset-inline-end:8px;min-inline-size:18px;height:18px;border-radius:9px;color:var(--white,#fff);font-size:11px;font-weight:700;display:inline-flex;align-items:center;justify-content:center;padding:0 5px;",
	card_head: "display:flex;justify-content:space-between;align-items:center;gap:8px;",
	plate: "font-size:16px;font-weight:700;",
	card_meta: "margin-block:6px;font-size:var(--text-sm,13px);",
	sep_dot: "display:flex;flex-wrap:wrap;align-items:center;gap:6px;",
	card_foot: "display:flex;justify-content:space-between;align-items:center;gap:8px;font-size:12px;margin-block-start:6px;flex-wrap:wrap;",
	driver: "display:inline-flex;align-items:center;gap:5px;",
	driver_icon: "display:inline-flex;color:var(--text-muted);",
	empty: "padding:40px;text-align:center;inline-size:100%;",
	empty_scope:
		"padding:40px;text-align:center;inline-size:100%;border:1px solid var(--border-color);border-radius:var(--border-radius-md,8px);background:var(--control-bg);",
	empty_title: "font-weight:600;font-size:var(--text-md,14px);margin-block-end:6px;",
	error: "padding:24px;text-align:center;inline-size:100%;",
	error_msg: "margin-block-end:10px;",
	table: "inline-size:100%;font-size:var(--text-sm,13px);",
	sev_counter:
		"display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border:1px solid transparent;border-radius:14px;background:var(--control-bg);font-size:var(--text-sm,12px);cursor:pointer;",
	sev_counter_pressed: "border-color:var(--primary);background:var(--bg-color);",
	sev_dot: "inline-size:9px;block-size:9px;border-radius:50%;flex:0 0 auto;",
	sev_count: "font-weight:700;",
	alert_clear: "display:inline-flex;align-items:center;padding:4px 10px;font-size:var(--text-sm,12px);color:var(--text-muted);",
	queue_bulk: "display:flex;align-items:center;gap:10px;margin-block-end:8px;flex-wrap:wrap;inline-size:100%;",
	queue: "inline-size:100%;display:flex;flex-direction:column;gap:6px;",
	queue_row:
		"display:flex;align-items:center;gap:10px;padding:8px 10px;border:1px solid var(--border-color);border-inline-start:4px solid var(--gray-300);border-radius:var(--border-radius-md,8px);background:var(--card-bg);",
	queue_aging: "background:var(--yellow-50,var(--yellow-100));",
	queue_main: "flex:1 1 auto;min-inline-size:0;",
	queue_msg: "font-size:var(--text-sm,13px);",
	queue_meta: "font-size:11.5px;color:var(--text-muted);margin-block-start:2px;",
	queue_owner: "font-weight:500;",
	unowned: "color:var(--text-muted);font-style:italic;",
	queue_aging_pill: "font-size:10.5px;font-weight:700;color:var(--orange-700);background:var(--yellow-100);border-radius:8px;padding:0 6px;",
	queue_actions: "display:inline-flex;gap:6px;flex:0 0 auto;flex-wrap:wrap;",
	drawer:
		"flex:0 0 320px;inline-size:320px;background:var(--card-bg);border:1px solid var(--border-color);border-radius:var(--border-radius-md,8px);padding:14px;max-block-size:80vh;overflow:auto;",
	drawer_head: "display:flex;align-items:center;gap:8px;margin-block-end:10px;flex-wrap:wrap;",
	drawer_title: "font-size:17px;font-weight:700;flex:1 1 auto;",
	drawer_sub: "font-size:11px;color:var(--text-muted);margin:14px 0 6px;font-weight:600;",
	drawer_alerts: "display:flex;flex-direction:column;gap:6px;",
	drawer_alert:
		"border:1px solid var(--border-color);border-inline-start:4px solid var(--gray-300);border-radius:var(--border-radius-md,8px);padding:8px;",
	dl: "display:flex;flex-direction:column;",
	dl_row: "display:flex;gap:8px;padding:3px 0;font-size:var(--text-sm,13px);",
	dl_k: "flex:0 0 110px;color:var(--text-muted);",
	dl_v: "flex:1 1 auto;font-weight:500;",
	list: "margin:0;padding-inline-start:0;list-style:none;font-size:12.5px;",
	timeline_kind: "font-size:10.5px;font-weight:700;color:var(--text-muted);text-transform:uppercase;",
};

class FleetControl {
	constructor(page) {
		this.page = page;
		this.data = { vehicles: [], summary: null, offices: [], projects: [], statuses: [], unscoped: false };
		this.filters = _empty_filters();
		this.sort = "risk";
		this.severity_filter = "";
		this.ownership_filter = "";
		this._incidents_only = false;
		this._gen = 0;
		this._alert_gen = 0;
		this.alerts = [];
		this.alerts_by_vehicle = {};
		this.alert_summary = { total: 0, by_severity: {}, mine: 0, unowned: 0 };
		this.aging_hours = {};
		this.server_now = null;
		this.current_user = frappe.session.user;
		this.last_seen = null;
		this.resolved_since = 0;
		this.view = "cards";
		this.selected_alerts = new Set();
	}

	setup() {
		this._restore_filters();
		this.$root = $('<div class="fc-root"></div>')
			.attr("dir", frappe.utils.is_rtl() ? "rtl" : "ltr")
			.appendTo(this.page.main);
		this.$progress = $('<div class="fc-progress"></div>').attr("style", FC.progress).appendTo(this.$root);
		this.$banner = $('<div class="fc-since-banner"></div>').css("display", "none").appendTo(this.$root);
		this.$summary = $('<div class="fc-summary"></div>').attr("style", FC.summary).appendTo(this.$root);
		this.$controls = $('<div class="fc-controls"></div>').attr("style", FC.controls).appendTo(this.$root);
		this.$body = $('<div class="fc-body"></div>').attr("style", FC.body).appendTo(this.$root);
		this.$grid = $('<div class="fc-grid"></div>').attr("style", FC.grid).appendTo(this.$body);
		this.$drawer = $('<div class="fc-drawer"></div>').css("display", "none").appendTo(this.$body);

		this.page.set_primary_action(__("Refresh"), () => this.refresh(), "refresh");
		this.page.add_button(__("Cards / Table"), () => this.toggle_view("table"));
		this.page.add_button(__("Alert queue"), () => this.toggle_view("queue"));

		this._build_controls();
		this._render_skeleton();
		this._subscribe_realtime();
		this.ready.then(() => {
			this._sync_controls();
			this.refresh();
		});
	}

	_sync_controls() {
		if (this.$status) this.$status.val(this.filters.status || "");
		if (this.$office) this.$office.val(this.filters.rental_office || "");
		if (this.$project) this.$project.val(this.filters.project || "");
		if (this.$compliance) this.$compliance.val(this.filters.compliance || "");
		if (this.$search) this.$search.val(this.filters.search || "");
	}

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
		this.$compliance = this._select(__("Compliance"), () => this._on_filter());
		this._fill_select(this.$compliance, COMPLIANCE_OPTIONS, this.filters.compliance);
		this.$search = $(
			`<input type="text" class="form-control input-sm fc-search" placeholder="${__("Search plate or category")}">`
		).attr("style", FC.search).appendTo(this.$controls);
		this.$search.val(this.filters.search || "");
		this.$search.on(
			"input",
			frappe.utils.debounce(() => {
				this.filters.search = this.$search.val();
				this.refresh();
			}, 350)
		);
		this.$sort = this._select(__("Sort"), () => {
			this.sort = this.$sort.val() || "risk";
			this._render();
		});
		this.$sort.empty();
		$('<option value="risk"></option>').text(__("Risk (default)")).appendTo(this.$sort);
		$('<option value="plate" class="fc-sort-secondary"></option>')
			.text(__("Plate"))
			.appendTo(this.$sort);
		this.$sort.val(this.sort);
		this.$count = $('<span class="fc-result-count"></span>').attr("style", FC.result_count).appendTo(this.$controls);
	}

	_select(label, on_change) {
		const $wrap = $('<span class="fc-filter"></span>').attr("style", FC.filter).appendTo(this.$controls);
		$(`<label>${frappe.utils.escape_html(label)}</label>`).css({ "font-size": "11px", color: "var(--text-muted)", margin: "0" }).appendTo($wrap);
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
		this.ready = frappe.model.user_settings
			.get(SETTINGS_KEY)
			.then((s) => {
				const blob = s || {};
				this.last_seen = blob.last_seen || null;
				const saved = blob.filters;
				if (!from_route && saved)
					ROUTE_FILTERS.forEach((k) => { if (saved[k]) this.filters[k] = saved[k]; });
			})
			.catch(() => {});
	}

	_mark_seen() {
		if (this._seen_marked) return;
		this._seen_marked = true;
		frappe.model.user_settings.save(SETTINGS_KEY, "last_seen", frappe.datetime.now_datetime());
	}

	_persist_filters() {
		const active = {};
		ROUTE_FILTERS.forEach((k) => { if (this.filters[k]) active[k] = this.filters[k]; });
		frappe.model.user_settings.save(SETTINGS_KEY, "filters", active);
		const route = frappe.get_route() || [];
		const qs = frappe.utils.make_query_string(active);
		frappe.router.push_state("/" + ["app", route[1] || "operations-control"].join("/") + qs);
	}

	_call_failed(r, message) {
		if (!r || !r.exc) return false;
		frappe.show_alert({ message: message, indicator: "red" });
		return true;
	}

	refresh() {
		const gen = ++this._gen;
		this._set_loading(true);
		this._persist_filters();
		this._refresh_alerts();
		frappe.call({
			method: "apex.salis.api.operations_control.get_fleet",
			args: { ...this.filters },
			callback: (r) => {
				if (gen !== this._gen) return;
				if (!r || r.exc || !r.message) {
					this._render_board_error(() => this.refresh());
					return;
				}
				this.data = r.message;
				this._fill_select(this.$status, this.data.statuses, this.filters.status);
				this._fill_select(this.$office, this.data.offices, this.filters.rental_office);
				this._fill_select(this.$project, this.data.projects, this.filters.project);
				if (this._drop_dead_filters()) return;
				this._render_summary();
				this._render();
			},
			error: (r) => {
				if (gen === this._gen) this._render_board_error(() => this.refresh(), r);
			},
			always: () => {
				if (gen === this._gen) this._set_loading(false);
			},
		});
	}

	_refresh_alerts() {
		const gen = ++this._alert_gen;
		frappe.call({
			method: "apex.salis.api.operations_alerts.get_open_alerts",
			args: { project: this.filters.project || undefined, since: this.last_seen || undefined },
			callback: (r) => {
				if (gen !== this._alert_gen) return;
				if (this._call_failed(r, __("Could not load the alerts."))) return;
				const m = (r && r.message) || { alerts: [], summary: { total: 0, by_severity: {} } };
				this.alerts = m.alerts || [];
				this.alert_summary = m.summary || { total: 0, by_severity: {}, mine: 0, unowned: 0 };
				this.aging_hours = m.aging_hours || {};
				this.server_now = m.server_now || null;
				this.resolved_since = m.resolved_since || 0;
				if (m.current_user) this.current_user = m.current_user;
				this.alerts_by_vehicle = {};
				this.alerts.forEach((a) => {
					if (!a.vehicle) return;
					(this.alerts_by_vehicle[a.vehicle] = this.alerts_by_vehicle[a.vehicle] || []).push(a);
				});
				this._render_summary();
				this._render_since_banner();
				this._render();
				this._mark_seen();
			},
			error: () => {
				if (gen !== this._alert_gen) return;
				this.alerts = [];
				this.alert_summary = { total: 0, by_severity: {}, mine: 0, unowned: 0 };
				this.alerts_by_vehicle = {};
				this._render_summary();
			},
		});
	}

	_render_since_banner() {
		this.$banner.empty().css("display", "none");
		const since = this.last_seen;
		if (!since) return;
		const raised = (this.alerts || []).filter((a) => a.raised_on && a.raised_on > since);
		const new_critical = raised.filter((a) => a.severity === "Critical").length;
		const new_total = raised.length;
		const resolved = this.resolved_since || 0;
		if (!new_total && !resolved) return;
		this.$banner.attr("style", FC.banner_on);
		const hhmm = since.slice(11, 16);
		const parts = [];
		if (new_critical) parts.push(__("{0} new Critical", [new_critical]));
		else if (new_total) parts.push(__("{0} new", [new_total]));
		if (resolved) parts.push(__("{0} resolved", [resolved]));
		const phrase = __("{0} since {1}", [parts.join(", "), hhmm]);
		$('<span class="fc-since-text"></span>').css("font-weight", "600").text(phrase).appendTo(this.$banner);
		$('<button class="btn btn-xs btn-default fc-since-dismiss"></button>')
			.css("margin-inline-start", "auto")
			.text(__("Dismiss"))
			.on("click", () => { this.last_seen = null; this._render_since_banner(); })
			.appendTo(this.$banner);
	}

	_alert_age_hours(a) {
		if (!a.raised_on || !this.server_now) return null;
		const ms = frappe.datetime.str_to_obj(this.server_now) - frappe.datetime.str_to_obj(a.raised_on);
		return ms > 0 ? ms / 3600000 : 0;
	}

	_alert_is_aging(a) {
		const limit = this.aging_hours[a.severity];
		if (!limit) return false;
		const age = this._alert_age_hours(a);
		return age != null && age >= limit;
	}

	_vehicle_top_severity(name) {
		const list = this.alerts_by_vehicle[name];
		if (!list || !list.length) return null;
		let best = null;
		list.forEach((a) => {
			if (!best || (SEVERITY_RANK[a.severity] || 0) > (SEVERITY_RANK[best] || 0)) best = a.severity;
		});
		return best;
	}

	_render_error($target, retry, r) {
		$target.empty();
		const $panel = $('<div class="fc-error"></div>').attr("style", FC.error).appendTo($target);
		$('<div class="fc-error-msg"></div>').attr("style", FC.error_msg).text(this._error_text(r)).appendTo($panel);
		const $btn = $('<button class="btn btn-sm btn-default fc-error-retry"></button>')
			.text(__("Retry"))
			.appendTo($panel);
		$btn.on("click", () => retry());
	}

	_error_text(r) {
		const raw = r && r._server_messages;
		if (raw) {
			try {
				const first = JSON.parse(raw)[0];
				const obj = typeof first === "string" ? JSON.parse(first) : first;
				const msg = obj && obj.message ? obj.message : first;
				if (msg) return strip_html(msg).trim();
			} catch (e) {
			}
		}
		return __("Could not load fleet data. Please try again.");
	}

	_render_board_error(retry, r) {
		this.$summary.empty();
		this.$grid.empty();
		this._render_error(this.$grid, retry, r);
	}

	_set_loading(active) {
		this.$progress.attr("style", FC.progress + (active ? FC.progress_on : ""));
		if (this.page.btn_primary) this.page.btn_primary.prop("disabled", active);
	}

	_render_skeleton() {
		this.$summary.empty();
		for (let i = 0; i < 4; i++) {
			$('<div class="skeleton-block"></div>').css({ flex: "1 1 120px", "min-inline-size": "110px", height: "62px", "border-radius": "8px", background: "var(--skeleton-bg)" }).appendTo(this.$summary);
		}
		this.$grid.empty();
		for (let i = 0; i < 6; i++) {
			$('<div class="skeleton-block"></div>').css({ height: "120px", "border-radius": "8px", background: "var(--skeleton-bg)" }).appendTo(this.$grid);
		}
	}

	_render_severity_counters() {
		const sev = (this.alert_summary && this.alert_summary.by_severity) || {};
		const total = (this.alert_summary && this.alert_summary.total) || 0;
		if (!total) {
			$('<div class="fc-sev-counter fc-alert-clear"></div>')
				.attr("style", FC.alert_clear)
				.text(__("All clear — no open alerts"))
				.appendTo(this.$summary);
			return;
		}
		SEVERITY_ORDER.forEach((s) => {
			const n = sev[s] || 0;
			if (!n) return;
			const active = this.severity_filter === s;
			const $b = $('<button type="button" class="fc-sev-counter"></button>')
				.attr("style", FC.sev_counter + (active ? FC.sev_counter_pressed : ""))
				.attr("aria-pressed", active ? "true" : "false")
				.appendTo(this.$summary);
			$('<span class="fc-sev-dot"></span>')
				.addClass("fc-sev-" + s)
				.attr("style", FC.sev_dot + `background:${FC_SEV_COLOR[s] || "var(--gray-400)"};`)
				.appendTo($b);
			$('<span class="fc-sev-count"></span>').attr("style", FC.sev_count).text(n).appendTo($b);
			$('<span></span>').text(__(s)).appendTo($b);
			$b.on("click", () => {
				this.severity_filter = active ? "" : s;
				this._render_summary();
				this._render();
			});
		});
		this._ownership_counter("mine", __("Mine"), this.alert_summary.mine || 0);
		this._ownership_counter("unowned", __("Unowned"), this.alert_summary.unowned || 0);
	}

	_ownership_counter(key, label, n) {
		const active = this.ownership_filter === key;
		const $b = $('<button type="button" class="fc-sev-counter fc-own-counter"></button>')
			.attr("style", FC.sev_counter + "margin-inline-start:6px;" + (active ? FC.sev_counter_pressed : ""))
			.attr("aria-pressed", active ? "true" : "false")
			.appendTo(this.$summary);
		$('<span class="fc-sev-count"></span>').attr("style", FC.sev_count).text(n).appendTo($b);
		$('<span></span>').text(label).appendTo($b);
		$b.on("click", () => {
			this.ownership_filter = active ? "" : key;
			this._render_summary();
			this._render();
		});
	}

	_render_summary() {
		this.$summary.empty();
		const s = this.data.summary || { by_status: {}, total: 0, open_incidents: 0 };
		const CHIP_ACCENT = {
			"fc-chip-total": "var(--gray-600)", "fc-chip-green": "var(--green-500)",
			"fc-chip-orange": "var(--orange-500)", "fc-chip-red": "var(--red-500)", "fc-chip-gray": "var(--gray-400)",
		};
		const chip = (label, value, cls, on_click, pressed) => {
			const accent = CHIP_ACCENT[cls] || "var(--gray-400)";
			const $c = $('<div class="fc-chip"></div>')
				.addClass(cls || "")
				.attr("style", FC.chip + `border-block-start-color:${accent};` + (pressed ? FC.chip_pressed : "") + (on_click ? "cursor:pointer;" : ""))
				.appendTo(this.$summary);
			$('<div class="fc-chip-val"></div>').attr("style", FC.chip_val).text(value).appendTo($c);
			$('<div class="fc-chip-lbl"></div>').attr("style", FC.chip_lbl).text(label).appendTo($c);
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
			() => this._toggle_incidents(),
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
		this._render_severity_counters();
	}

	_toggle_status(st) {
		this.filters.status = this.filters.status === st ? "" : st;
		this._sync_controls();
		this.refresh();
	}
	_toggle_compliance_risk() {
		const on = this.filters.compliance === "Expired" || this.filters.compliance === "Expiring Soon";
		this.filters.compliance = on ? "" : "Expired";
		this._sync_controls();
		this.refresh();
	}
	_toggle_incidents() {
		this._incidents_only = !this._incidents_only;
		this._render();
	}

	toggle_view(target) {
		this.view = this.view === target ? "cards" : target;
		this._render();
	}

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

	_visible_vehicles() {
		let list = this.data.vehicles || [];
		if (this._incidents_only) list = list.filter((v) => v.open_incidents);
		if (this.severity_filter)
			list = list.filter((v) => this._vehicle_top_severity(v.name) === this.severity_filter);
		return this._sort_vehicles(list);
	}

	_render() {
		if (this.view === "queue") {
			this._update_count(this.alerts.length, true);
			this._render_queue();
			return;
		}
		this.$grid.empty();
		this.$grid.toggleClass("fc-grid-table", this.view === "table");
		this.$grid.css("display", this.view === "table" ? "block" : "grid");
		const vehicles = this._visible_vehicles();
		this._update_count(vehicles.length, false);
		if (!vehicles.length) {
			this._render_empty();
			return;
		}
		if (this.view === "table") this._render_table(vehicles);
		else vehicles.forEach((v) => this._render_card(v));
	}

	_update_count(n, is_alerts) {
		if (!this.$count) return;
		this.$count.text(is_alerts ? __("{0} alerts", [n]) : __("{0} vehicles", [n]));
	}

	_render_empty() {
		if (!this.data.unscoped && (this.data.projects || []).length === 0) {
			const $e = $('<div class="fc-empty fc-empty-scope"></div>').attr("style", FC.empty_scope).appendTo(this.$grid);
			$('<div class="fc-empty-title"></div>')
				.attr("style", FC.empty_title)
				.text(__("You have no fleet project assigned"))
				.appendTo($e);
			$('<div class="fc-empty-hint text-muted"></div>')
				.css("font-size", "var(--text-sm, 13px)")
				.text(__("Contact your Fleet Manager to be granted a project."))
				.appendTo($e);
			return;
		}
		const $e = $('<div class="fc-empty fc-empty-filtered text-muted"></div>').attr("style", FC.empty).appendTo(this.$grid);
		$('<div></div>').text(__("No vehicles match the current filters.")).appendTo($e);
		const $clear = $('<button class="btn btn-sm btn-default fc-clear-filters"></button>')
			.css("margin-block-start", "12px")
			.text(__("Clear filters"))
			.appendTo($e);
		$clear.on("click", () => this._clear_filters());
	}

	_clear_filters() {
		this.filters = _empty_filters();
		this.severity_filter = "";
		this.ownership_filter = "";
		this._incidents_only = false;
		this._sync_controls();
		this.refresh();
	}

	_drop_dead_filters() {
		const lists = {
			status: this.data.statuses,
			rental_office: this.data.offices,
			project: this.data.projects,
			compliance: COMPLIANCE_OPTIONS,
		};
		let dropped = false;
		Object.keys(lists).forEach((k) => {
			const value = this.filters[k];
			if (value && !(lists[k] || []).includes(value)) {
				this.filters[k] = "";
				dropped = true;
			}
		});
		if (!dropped) return false;
		frappe.show_alert({
			message: __("A saved filter no longer exists here and was cleared."),
			indicator: "orange",
		});
		this._sync_controls();
		this.refresh();
		return true;
	}

	_render_card(v) {
		const color = STATUS_COLOR[v.status] || "gray";
		const $c = $('<div class="fc-card"></div>')
			.addClass("fc-accent-" + color)
			.attr("style", FC.card + `border-inline-start-color:${FC_ACCENT[color] || "var(--gray-400)"};`);
		$c.on("click", () => this.open_detail(v));
		const top_sev = this._vehicle_top_severity(v.name);
		if (top_sev) {
			const n = (this.alerts_by_vehicle[v.name] || []).length;
			$('<span class="fc-card-sev"></span>')
				.addClass("fc-sev-" + top_sev)
				.attr("style", FC.card_sev + `background:${FC_SEV_COLOR[top_sev] || "var(--gray-500)"};`)
				.attr("title", __(top_sev))
				.text(n)
				.appendTo($c);
		}
		const $head = $('<div class="fc-card-head"></div>').attr("style", FC.card_head).appendTo($c);
		$('<div class="fc-plate"></div>').attr("style", FC.plate).html(_bdi(v.plate_number || v.name)).appendTo($head);
		$('<span class="indicator-pill"></span>').addClass(color).text(__(v.status || "")).appendTo($head);
		const $meta = $('<div class="fc-card-meta"></div>').attr("style", FC.card_meta).appendTo($c);
		$('<div></div>').text(v.vehicle_category || __("No category")).appendTo($meta);
		const $op = $('<div class="text-muted fc-sep-dot"></div>').attr("style", FC.sep_dot).appendTo($meta);
		const parts = [v.rental_office, v.project].filter(Boolean);
		if (!parts.length) $('<span></span>').text("—").appendTo($op);
		else parts.forEach((p) => $("<span></span>").text(p).appendTo($op));
		const $foot = $('<div class="fc-card-foot"></div>').attr("style", FC.card_foot).appendTo($c);
		const $driver = $('<div class="fc-driver"></div>').attr("style", FC.driver).appendTo($foot);
		$('<span class="fc-driver-icon"></span>')
			.attr("style", FC.driver_icon)
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
		const $t = $('<table class="table table-bordered fc-table"></table>').attr("style", FC.table).appendTo(this.$grid);
		const $hr = $("<tr></tr>").appendTo($("<thead></thead>").appendTo($t));
		cols.forEach((c) => $("<th></th>").text(__(c[0])).appendTo($hr));
		const $tb = $("<tbody></tbody>").appendTo($t);
		(vehicles || this.data.vehicles).forEach((v) => {
			const $r = $("<tr></tr>").appendTo($tb);
			$r.on("click", () => this.open_detail(v));
			cols.forEach((c) => $("<td></td>").text(v[c[1]] == null ? "" : String(v[c[1]])).appendTo($r));
		});
	}

	_alert_matches_facets(a) {
		if (this.severity_filter && a.severity !== this.severity_filter) return false;
		if (this.ownership_filter === "mine" && !(a.assignees || []).includes(this.current_user))
			return false;
		if (this.ownership_filter === "unowned" && (a.assignees || []).length) return false;
		return true;
	}

	_render_queue() {
		this.$grid.empty().removeClass("fc-grid-table").css("display", "block");
		const sorted = (this.alerts || [])
			.filter((a) => this._alert_matches_facets(a))
			.slice()
			.sort((a, b) => (SEVERITY_RANK[b.severity] || 0) - (SEVERITY_RANK[a.severity] || 0));
		if (!sorted.length) {
			const $e = $('<div class="fc-empty text-muted"></div>').attr("style", FC.empty).appendTo(this.$grid);
			$('<div></div>')
				.text(this.ownership_filter || this.severity_filter
					? __("No alerts match the current filters.")
					: __("All clear — no open alerts"))
				.appendTo($e);
			return;
		}
		const $bulk = $('<div class="fc-queue-bulk"></div>').attr("style", FC.queue_bulk).appendTo(this.$grid);
		const $all = $('<input type="checkbox">')
			.on("change", () => {
				this.selected_alerts = $all.prop("checked")
					? new Set(sorted.map((a) => a.name))
					: new Set();
				this._render_queue();
			})
			.appendTo($('<label class="fc-queue-bulk-all"></label>').appendTo($bulk));
		$('<span></span>').text(__("Select all")).appendTo($all.parent());
		const n = this.selected_alerts.size;
		$('<button class="btn btn-xs btn-default"></button>')
			.text(__("Acknowledge selected ({0})", [n]))
			.prop("disabled", !n)
			.on("click", () => this._bulk_acknowledge())
			.appendTo($bulk);
		$('<button class="btn btn-xs btn-default"></button>')
			.text(__("Assign to me ({0})", [n]))
			.prop("disabled", !n)
			.on("click", () => this._bulk_assign())
			.appendTo($bulk);
		$('<button class="btn btn-xs btn-default"></button>')
			.text(__("Snooze selected ({0})", [n]))
			.prop("disabled", !n)
			.on("click", () => this._bulk_snooze())
			.appendTo($bulk);

		const $wrap = $('<div class="fc-queue"></div>').attr("style", FC.queue).appendTo(this.$grid);
		sorted.forEach((a) => this._render_queue_row(a, $wrap));
	}

	_render_queue_row(a, $wrap) {
		const aging = this._alert_is_aging(a);
		const $row = $('<div class="fc-queue-row"></div>')
			.addClass("fc-sev-row-" + a.severity)
			.toggleClass("fc-queue-aging", aging)
			.attr("style", FC.queue_row + `border-inline-start-color:${FC_SEV_COLOR[a.severity] || "var(--gray-400)"};` + (aging ? FC.queue_aging : ""))
			.appendTo($wrap);
		$('<input type="checkbox" class="fc-queue-pick">')
			.prop("checked", this.selected_alerts.has(a.name))
			.on("change", (e) => {
				if (e.target.checked) this.selected_alerts.add(a.name);
				else this.selected_alerts.delete(a.name);
				this._render_queue();
			})
			.appendTo($row);
		const $main = $('<div class="fc-queue-main"></div>').attr("style", FC.queue_main).appendTo($row);
		$('<div class="fc-queue-msg"></div>').attr("style", FC.queue_msg).text(a.message || __(a.alert_type || "")).appendTo($main);
		const $meta = $('<div class="fc-queue-meta fc-sep-dot"></div>').attr("style", FC.queue_meta + FC.sep_dot).appendTo($main);
		if (a.vehicle_plate) $('<span></span>').html(_bdi(a.vehicle_plate)).appendTo($meta);
		$('<span></span>').text(__(a.alert_type || "")).appendTo($meta);
		if (a.raised_on)
			$('<span></span>').text(frappe.datetime.comment_when(a.raised_on)).appendTo($meta);
		$('<span></span>').text(__(a.status || "")).appendTo($meta);
		const owners = a.assignee_names || [];
		$('<span class="fc-queue-owner"></span>')
			.attr("style", owners.length ? FC.queue_owner : FC.unowned)
			.text(owners.length ? owners.join(", ") : __("Unowned"))
			.toggleClass("fc-unowned", !owners.length)
			.appendTo($meta);
		if (aging) {
			$('<span class="fc-queue-aging-pill"></span>')
				.attr("style", FC.queue_aging_pill)
				.text(a.status === "Acknowledged" ? __("Stale") : __("Overdue"))
				.appendTo($meta);
		}
		this._alert_actions(a, $('<div class="fc-queue-actions"></div>').attr("style", FC.queue_actions).appendTo($row));
	}

	_alert_actions(a, $into) {
		if (a.status === "Open") {
			const $ack = $('<button class="btn btn-xs btn-default"></button>')
				.text(__("Acknowledge"))
				.appendTo($into);
			$ack.on("click", (e) => {
				e.stopPropagation();
				this._alert_action("acknowledge_alert", { name: a.name }, __("Alert acknowledged"), $ack);
			});
		}
		const mine = (a.assignees || []).includes(this.current_user);
		const $own = $('<button class="btn btn-xs btn-default"></button>')
			.text(mine ? __("Release") : __("Assign to me"))
			.appendTo($into);
		$own.on("click", (e) => {
			e.stopPropagation();
			this._alert_action(
				mine ? "unassign_alert" : "assign_alert",
				{ name: a.name },
				mine ? __("Released") : __("Assigned to you"),
				$own
			);
		});
		this._snooze_button(a, $into);
		const $resolve = $('<button class="btn btn-xs btn-default"></button>')
			.text(__("Resolve"))
			.appendTo($into);
		$resolve.on("click", (e) => {
			e.stopPropagation();
			this._alert_action("resolve_alert", { name: a.name }, __("Alert resolved"), $resolve);
		});
	}

	_snooze_button(a, $into) {
		const $wrap = $('<span class="fc-snooze dropdown"></span>').appendTo($into);
		const $toggle = $('<button class="btn btn-xs btn-default dropdown-toggle" data-toggle="dropdown"></button>')
			.text(__("Snooze"))
			.appendTo($wrap);
		const $menu = $('<ul class="dropdown-menu fc-snooze-menu"></ul>').appendTo($wrap);
		SNOOZE_PRESETS.forEach(([key, label]) => {
			$('<li><a href="#"></a></li>')
				.find("a")
				.text(__(label))
				.on("click", (e) => {
					e.preventDefault();
					e.stopPropagation();
					this._alert_action("snooze_alert", { name: a.name, preset: key }, __("Snoozed"), $toggle);
				})
				.end()
				.appendTo($menu);
		});
		$('<li><a href="#"></a></li>')
			.find("a")
			.text(__("Custom…"))
			.on("click", (e) => {
				e.preventDefault();
				e.stopPropagation();
				this._snooze_custom(a, $toggle);
			})
			.end()
			.appendTo($menu);
	}

	_snooze_custom(a, $toggle) {
		frappe.prompt(
			[{ fieldname: "until", fieldtype: "Datetime", label: __("Snooze until"), reqd: 1 }],
			({ until }) =>
				this._alert_action("snooze_alert", { name: a.name, until }, __("Snoozed"), $toggle),
			__("Snooze alert"),
			__("Snooze")
		);
	}

	_alert_action(method, args, ok_msg, $btn) {
		if ($btn && $btn.length) {
			if ($btn.prop("disabled")) return;
			$btn.prop("disabled", true);
		}
		const release = () => {
			if ($btn && $btn.length) $btn.prop("disabled", false);
		};
		frappe.call({
			method: "apex.salis.api.operations_alerts." + method,
			args,
			callback: (r) => {
				if (this._call_failed(r, __("Could not complete the alert action."))) {
					release();
					return;
				}
				if (r && r.message && r.message.ok) {
					frappe.show_alert({ message: ok_msg, indicator: "green" });
					this._refresh_alerts();
					return;
				}
				release();
			},
			error: () => {
				release();
				frappe.show_alert({ message: __("Could not complete the alert action."), indicator: "red" });
			},
		});
	}

	_bulk_acknowledge() {
		const names = Array.from(this.selected_alerts);
		if (!names.length) return;
		frappe.call({
			method: "apex.salis.api.operations_alerts.bulk_acknowledge_alerts",
			args: { names },
			callback: (r) => {
				if (this._call_failed(r, __("Could not acknowledge the selected alerts."))) return;
				const n = (r && r.message && (r.message.acknowledged || []).length) || 0;
				frappe.show_alert({ message: __("{0} acknowledged", [n]), indicator: "green" });
				this.selected_alerts = new Set();
				this._refresh_alerts();
			},
			error: () => frappe.show_alert({ message: __("Could not acknowledge the selected alerts."), indicator: "red" }),
		});
	}

	_bulk_assign() {
		const names = Array.from(this.selected_alerts);
		if (!names.length) return;
		frappe.call({
			method: "apex.salis.api.operations_alerts.bulk_assign_alerts",
			args: { names },
			callback: (r) => {
				if (this._call_failed(r, __("Could not assign the selected alerts."))) return;
				const n = (r && r.message && (r.message.assigned || []).length) || 0;
				frappe.show_alert({ message: __("{0} assigned", [n]), indicator: "green" });
				this.selected_alerts = new Set();
				this._refresh_alerts();
			},
			error: () => frappe.show_alert({ message: __("Could not assign the selected alerts."), indicator: "red" }),
		});
	}

	_bulk_snooze() {
		const names = Array.from(this.selected_alerts);
		if (!names.length) return;
		frappe.prompt(
			[{ fieldname: "until", fieldtype: "Datetime", label: __("Snooze until"), reqd: 1 }],
			({ until }) => {
				frappe.call({
					method: "apex.salis.api.operations_alerts.bulk_snooze_alerts",
					args: { names, until },
					callback: (r) => {
						if (this._call_failed(r, __("Could not snooze the selected alerts."))) return;
						const n = (r && r.message && (r.message.snoozed || []).length) || 0;
						frappe.show_alert({ message: __("{0} snoozed", [n]), indicator: "green" });
						this.selected_alerts = new Set();
						this._refresh_alerts();
					},
					error: () => frappe.show_alert({ message: __("Could not snooze the selected alerts."), indicator: "red" }),
				});
			},
			__("Snooze alerts"),
			__("Snooze")
		);
	}

	open_detail(v) {
		this.$drawer.attr("style", FC.drawer).css("display", "block").empty();
		const $close = $('<button class="btn btn-xs btn-default fc-close"></button>').text(__("Close"));
		$close.on("click", () => this.$drawer.removeClass("fc-open").css("display", "none"));
		const $head = $('<div class="fc-drawer-head"></div>').attr("style", FC.drawer_head).appendTo(this.$drawer);
		$('<div class="fc-drawer-title"></div>').attr("style", FC.drawer_title).html(_bdi(v.plate_number || v.name)).appendTo($head);
		$close.appendTo($head);
		const $open = $('<a class="btn btn-xs btn-primary fc-form-link"></a>').text(__("Open Vehicle"));
		$open.attr("href", "/app/salis-vehicle/" + encodeURIComponent(v.name)).appendTo($head);

		const $reassign = $('<button class="btn btn-xs btn-default fc-action"></button>').text(
			__("Reassign driver")
		);
		$reassign.on("click", () => this.reassign_driver(v, $reassign));
		$reassign.appendTo($head);
		if (v.status === "Stopped") {
			const $rel = $('<button class="btn btn-xs btn-default fc-action fc-release"></button>').text(
				__("Release vehicle")
			);
			$rel.on("click", () => this.release_vehicle(v, $rel));
			$rel.appendTo($head);
		}
		["Vehicle Assignment", "Vehicle Suspension", "Vehicle Incident"].forEach((doctype) => {
			const $a = $('<button class="btn btn-xs btn-default fc-action"></button>').text("+ " + __(doctype));
			$a.on("click", () => {
				frappe.route_options = { vehicle: v.name };
				frappe.new_doc(doctype);
			});
			$a.appendTo($head);
		});
		this._render_drawer_alerts(v);
		const $body = $('<div class="fc-drawer-body"></div>').appendTo(this.$drawer);
		this._load_detail(v, $body);
	}

	_render_drawer_alerts(v) {
		const list = (this.alerts_by_vehicle[v.name] || [])
			.slice()
			.sort((a, b) => (SEVERITY_RANK[b.severity] || 0) - (SEVERITY_RANK[a.severity] || 0));
		if (!list.length) return;
		const $wrap = $('<div class="fc-drawer-alerts"></div>').attr("style", FC.drawer_alerts).appendTo(this.$drawer);
		$('<div class="fc-drawer-sub"></div>').attr("style", FC.drawer_sub).text(__("Alerts")).appendTo($wrap);
		list.forEach((a) => {
			const $a = $('<div class="fc-drawer-alert"></div>')
				.addClass("fc-sev-row-" + a.severity)
				.attr("style", FC.drawer_alert + `border-inline-start-color:${FC_SEV_COLOR[a.severity] || "var(--gray-400)"};`)
				.appendTo($wrap);
			const $top = $('<div class="fc-sep-dot"></div>').attr("style", FC.sep_dot).appendTo($a);
			$('<span></span>').text(__(a.severity)).appendTo($top);
			$('<span></span>').text(__(a.alert_type || "")).appendTo($top);
			$('<div class="small"></div>').css("margin-block", "4px").text(a.message || "").appendTo($a);
			this._alert_actions(a, $('<div class="fc-drawer-alert-actions"></div>').css({ display: "flex", gap: "6px", "flex-wrap": "wrap", "margin-block-start": "4px" }).appendTo($a));
		});
	}

	_load_detail(v, $body) {
		$body.empty().addClass("text-muted").text(__("Loading…"));
		frappe.call({
			method: "apex.salis.api.operations_control.get_vehicle_detail",
			args: { vehicle: v.name },
			callback: (r) => {
				if (!r || r.exc || !r.message) {
					this._render_error($body.removeClass("text-muted"), () => this._load_detail(v, $body));
					return;
				}
				$body.empty().removeClass("text-muted");
				this._detail_fields($body, r.message.vehicle);
				this._load_timeline(v, $body);
			},
			error: (r) =>
				this._render_error($body.removeClass("text-muted"), () => this._load_detail(v, $body), r),
		});
	}

	_load_timeline(v, $body) {
		const $section = $('<div class="fc-drawer-timeline"></div>').appendTo($body);
		$('<div class="fc-drawer-sub"></div>').attr("style", FC.drawer_sub).text(__("Timeline")).appendTo($section);
		const $loading = $('<div class="text-muted small"></div>').text(__("Loading…")).appendTo($section);
		frappe.call({
			method: "apex.salis.api.operations_control.get_vehicle_timeline",
			args: { vehicle: v.name },
			callback: (r) => {
				$loading.remove();
				if (this._call_failed(r, __("Could not load the timeline."))) return;
				const events = (r && r.message && r.message.events) || [];
				if (!events.length) {
					$('<div class="text-muted small"></div>').text(__("None.")).appendTo($section);
					return;
				}
				const $ul = $('<ul class="fc-list fc-timeline"></ul>').attr("style", FC.list).appendTo($section);
				events.forEach((e) => this._timeline_row(e, $("<li></li>").css("padding-block", "3px").appendTo($ul)));
			},
			error: (r) => {
				$loading.remove();
				this._render_error($section, () => { $section.remove(); this._load_timeline(v, $body); }, r);
			},
		});
	}

	_timeline_row(e, $li) {
		$li.addClass("fc-sep-dot").attr("style", FC.sep_dot);
		const KIND = { incident: "Incident", stop: "Stop", assignment: "Assignment", alert: "Alert" };
		$('<span class="fc-timeline-kind"></span>').attr("style", FC.timeline_kind).text(__(KIND[e.kind] || e.kind)).appendTo($li);
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
		const rows = [
			["Status", d.status], ["Category", d.vehicle_category], ["Driver", d.current_driver_name],
			["Office", d.rental_office], ["Project", d.project], ["Ownership", d.ownership],
			["Odometer", d.odometer, true], ["Planned Fuel", d.planned_fuel_grade],
			["Compliance", d.compliance_status], ["Next Expiry", d.next_expiry_date, true],
		];
		const $dl = $('<div class="fc-dl"></div>').attr("style", FC.dl).appendTo($body);
		rows.forEach(([k, val, ltr]) => {
			if (val == null || val === "") return;
			const $row = $('<div class="fc-dl-row"></div>').attr("style", FC.dl_row).appendTo($dl);
			$('<div class="fc-dl-k"></div>').attr("style", FC.dl_k).text(__(k)).appendTo($row);
			const $v = $('<div class="fc-dl-v"></div>').attr("style", FC.dl_v).appendTo($row);
			if (ltr) $v.html(_bdi(val));
			else $v.text(String(val));
		});
	}

	release_vehicle(v, $btn) {
		const d = frappe.confirm(__("Release {0} back to service?", [v.plate_number || v.name]), () => {
			d.disable_primary_action();
			$btn.prop("disabled", true);
			frappe.call({
				method: "apex.salis.api.operations_control.release_vehicle",
				args: { vehicle: v.name },
				callback: (r) => {
					if (this._call_failed(r, __("Could not release the vehicle."))) {
						$btn.prop("disabled", false);
						return;
					}
					if (r && r.message && r.message.ok) {
						frappe.show_alert({ message: __("Vehicle released"), indicator: "green" });
						this.$drawer.removeClass("fc-open").css("display", "none");
						this.refresh();
					}
				},
				error: () => $btn.prop("disabled", false),
			});
		});
	}

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
					method: "apex.salis.api.operations_control.reassign_driver",
					args: { vehicle: v.name, driver },
					callback: (r) => {
						if (this._call_failed(r, __("Could not reassign the driver."))) {
							$btn.prop("disabled", false);
							return;
						}
						if (r && r.message && r.message.ok) {
							frappe.show_alert({ message: __("Driver reassigned"), indicator: "green" });
							this.$drawer.removeClass("fc-open").css("display", "none");
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
