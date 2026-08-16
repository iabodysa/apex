// Copyright (c) 2026, afmcoltd

frappe.pages['telecom-control'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Telecom Control'),
		single_column: true,
	});
	wrapper.telecom_control = new TelecomControl(page);
};

// frappe.Chart needs real values, not var() strings, so the desk scale is read per render.
// Bidi moves a leading + to the end of an LTR number inside an Arabic page.
function TC_LTR(value) {
	return $('<bdi dir="ltr"></bdi>').text(value == null ? '' : String(value));
}

function TC_CHART_COLORS() {
	const root = getComputedStyle(document.documentElement);
	const pick = (name, fallback) => (root.getPropertyValue(name) || '').trim() || fallback;
	return [
		pick('--blue-500', '#5e64ff'),
		pick('--purple-500', '#743ee2'),
		pick('--red-500', '#ff5858'),
		pick('--orange-500', '#ffa00a'),
		pick('--green-500', '#28a745'),
	];
}

const TC_STATUS_COLOR = {
	Assigned: 'blue',
	Available: 'green',
	Suspended: 'orange',
	Lost: 'red',
	Terminated: 'gray',
};

const TC_SETTINGS_KEY = 'telecom-control';
const TC_ROUTE_FILTERS = ['company', 'supplier', 'telecom_contract', 'project', 'cost_center', 'status'];

const TC_RETIRE_FROM = {
	Lost: ['Available', 'Assigned', 'Suspended'],
	Terminated: ['Available', 'Assigned', 'Suspended', 'Lost'],
};

function _tc_cell_text(value) {
	return frappe.utils.escape_html(value == null ? '' : String(value));
}

// Mobile numbers are LTR digits; the bdi wrap keeps them left-to-right inside an
// Arabic row, matching the wrap TC_LTR already applies to the same field in the drawer.
function _tc_ltr_cell(value) {
	return `<bdi dir="ltr">${_tc_cell_text(value)}</bdi>`;
}

function _tc_status_pill(value) {
	const color = TC_STATUS_COLOR[value] || 'gray';
	return `<span class="indicator-pill no-indicator-dot ${color}">${_tc_cell_text(__(value || ''))}</span>`;
}

const TC_TABLE_COLUMNS = [
	{ id: 'mobile_number', label: 'Mobile Number', format: _tc_ltr_cell },
	{ id: 'status', label: 'Status', format: _tc_status_pill },
	{ id: 'custodian_display', label: 'Custodian' },
	{ id: 'telecom_contract', label: 'Contract' },
	{ id: 'current_cost_center', label: 'Cost Center' },
];

class TelecomControl {
	constructor(page) {
		this.page = page;
		this.state = { page: 1, page_size: 20 };
		this.charts = {};
		this.current_sim = null;
		this._gen = 0;
		this._restore_filters();
		this._build_skeleton();
		this.page.set_primary_action(__('Refresh'), () => this.refresh(), 'refresh');
		this.ready.then(() => {
			/* frappe.ui.form.make_control fires df.onchange asynchronously (via
			   frappe.run_serially) even for the control's own construction-time
			   set_value(), arriving well after this constructor returns. Until this
			   flag flips, _on_filter_change ignores that echo instead of persisting
			   an empty filter set over whatever this.ready is about to restore. */
			this._filters_ready = true;
			this._sync_controls();
			this.refresh();
		});
	}

	// A deep link (frappe.route_options) wins over the saved filter set; either way
	// `this.ready` gates the first refresh and the first control sync until it resolves.
	_restore_filters() {
		this.filters = {};
		const opts = frappe.route_options || {};
		let from_route = false;
		TC_ROUTE_FILTERS.forEach((k) => {
			if (opts[k] != null && opts[k] !== '') {
				this.filters[k] = String(opts[k]);
				from_route = true;
			}
		});
		frappe.route_options = null;
		this.ready = frappe.model.user_settings
			.get(TC_SETTINGS_KEY)
			.then((s) => {
				const saved = (s || {}).filters;
				if (!from_route && saved) {
					TC_ROUTE_FILTERS.forEach((k) => {
						if (saved[k]) this.filters[k] = saved[k];
					});
				}
			})
			.catch(() => {});
	}

	_sync_controls() {
		Object.keys(this.controls).forEach((field) => {
			this.controls[field].set_value(this.filters[field] || '');
		});
	}

	// Saves the active filter set to this user's settings and pushes it into the URL so
	// the page's current view can be bookmarked or shared.
	_persist_filters() {
		const active = {};
		TC_ROUTE_FILTERS.forEach((k) => {
			if (this.filters[k]) active[k] = this.filters[k];
		});
		frappe.model.user_settings.save(TC_SETTINGS_KEY, 'filters', active);
		const route = frappe.get_route() || [];
		const qs = frappe.utils.make_query_string(active);
		frappe.router.push_state('/' + ['app', route[1] || 'telecom-control'].join('/') + qs);
	}

	_build_skeleton() {
		this.$root = $('<div class="telecom-control tc-root"></div>').appendTo(this.page.main);
		this.$filters = $('<div class="tc-filters"></div>').appendTo(this.$root);
		this.$cards = $('<div class="tc-cards"></div>').appendTo(this.$root);
		this.$charts = $('<div class="tc-charts"></div>').appendTo(this.$root);
		$('<div class="tc-section-head"></div>').text(__('SIM Cards')).appendTo(this.$root);
		this.$tableWrap = $('<div class="tc-table-wrap"></div>').appendTo(this.$root);
		this.$pager = $('<div class="tc-pager"></div>').appendTo(this.$root);
		this.$empty = $('<div class="tc-empty"></div>').appendTo(this.$root).hide();
		/* The overlay and the drawer sit on <body> so the fixed drawer is not trapped in
		   the page's stacking context; both carry the page root class so their rules in
		   telecom_control.css can be scoped like every other rule in that file. */
		this.$backdrop = $('<div class="telecom-control tc-backdrop"></div>').appendTo(document.body);
		this.$drawer = $('<div class="telecom-control tc-drawer" role="dialog" aria-modal="true"></div>')
			.attr('aria-label', __('SIM details'))
			.appendTo(document.body);
		this.$backdrop.on('click', () => this._close_drawer());
		this._build_filters();
	}

	_build_filters() {
		this.controls = {};
		const defs = [
			{ field: 'company', label: __('Company'), doctype: 'Company' },
			{ field: 'supplier', label: __('Supplier'), doctype: 'Supplier' },
			{ field: 'telecom_contract', label: __('Contract'), doctype: 'Telecom Contract' },
			{ field: 'project', label: __('Project'), doctype: 'Project' },
			{ field: 'cost_center', label: __('Cost Center'), doctype: 'Cost Center' },
		];
		defs.forEach((def) => {
			const control = frappe.ui.form.make_control({
				parent: $('<div></div>').appendTo(this.$filters).get(0),
				df: {
					fieldtype: 'Link',
					options: def.doctype,
					label: def.label,
					fieldname: def.field,
					onchange: () => this._on_filter_change(def.field, control.get_value()),
				},
				render_input: true,
			});
			control.set_value(this.filters[def.field] || '');
			this.controls[def.field] = control;
		});
		const status = frappe.ui.form.make_control({
			parent: $('<div></div>').appendTo(this.$filters).get(0),
			df: {
				fieldtype: 'Select',
				label: __('Status'),
				fieldname: 'status',
				options: ['', 'Available', 'Assigned', 'Suspended', 'Lost', 'Terminated'].join('\n'),
				onchange: () => this._on_filter_change('status', status.get_value()),
			},
			render_input: true,
		});
		status.set_value(this.filters.status || '');
		this.controls.status = status;
		$('<button class="btn btn-default btn-sm"></button>')
			.text(__('Clear'))
			.on('click', () => this._clear_filters())
			.appendTo($('<div class="tc-filter-action"></div>').appendTo(this.$filters));
	}

	_on_filter_change(field, value) {
		if (!this._filters_ready) return;
		if (value) {
			this.filters[field] = value;
		} else {
			delete this.filters[field];
		}
		this.state.page = 1;
		this.refresh();
	}

	_clear_filters() {
		this.filters = {};
		Object.values(this.controls).forEach((c) => c.set_value(''));
		this.state.page = 1;
		this.refresh();
	}

	refresh() {
		const newest = apex.desk.newest_only(this, "_gen");
		const page = this.state.page;
		this._render_loading();
		this._persist_filters();
		const args = { filters: this.filters };
		Promise.all([
			this._call('get_summary_cards', args),
			this._call('get_charts', args),
			this._call('get_sim_rows', { ...args, page, page_size: this.state.page_size }),
		])
			.then(([cards, charts, rows]) => {
				if (!newest()) return;
				this.$empty.hide();
				this._render_cards(cards || {});
				this._render_charts(charts || {});
				this._render_table(rows || { rows: [], total: 0 });
			})
			.catch(() => {
				if (newest()) this._render_error();
			});
	}

	_call(method, args) {
		return frappe
			.call({ method: `apex.logistay.api.telecom_control.${method}`, args, type: 'GET' })
			.then((r) => r && r.message);
	}

	_render_loading() {
		this.$empty.text(__('Loading…')).show();
	}

	_render_error() {
		this.$empty.empty().show();
		$('<div class="tc-error-msg"></div>').text(__('Could not load Telecom Control. Please retry.')).appendTo(this.$empty);
		$('<button class="btn btn-default btn-sm"></button>').text(__('Retry')).on('click', () => this.refresh()).appendTo(this.$empty);
	}

	_render_cards(data) {
		this.$cards.empty();
		const cards = [
			{ label: __('Total SIMs'), value: data.total_sims || 0 },
			{ label: __('Assigned'), value: data.assigned || 0 },
			{ label: __('Available'), value: data.available || 0 },
			{ label: __('Suspended / Lost'), value: data.suspended_lost || 0 },
			{ label: __('Active Contracts'), value: data.active_contracts || 0 },
			{ label: __('Expiring Soon'), value: data.expiring_soon || 0 },
			{ label: __('Monthly Commitment'), value: format_currency(data.monthly_commitment || 0) },
		];
		cards.forEach((c) => {
			const $card = $('<div class="tc-card"></div>').appendTo(this.$cards);
			$('<div class="tc-card-value"></div>').text(c.value).appendTo($card);
			$('<div class="tc-label"></div>').text(c.label).appendTo($card);
		});
	}

	_render_charts(data) {
		this.$charts.empty();
		if (!frappe.Chart) {
			return;
		}
		const specs = [
			{ key: 'by_status', title: __('By Status'), type: 'percentage' },
			{ key: 'by_supplier', title: __('By Supplier'), type: 'bar' },
			{ key: 'by_project', title: __('By Project'), type: 'bar' },
			{ key: 'by_cost_center', title: __('By Cost Center'), type: 'bar' },
		];
		specs.forEach((spec) => {
			const rows = data[spec.key] || [];
			const box = $('<div class="tc-chart-box"></div>').appendTo(this.$charts).get(0);
			if (!rows.length) {
				$(box).append($('<div class="tc-label"></div>').text(`${spec.title}: ${__('No data')}`));
				return;
			}
			this.charts[spec.key] = new frappe.Chart(box, {
				title: spec.title,
				data: { labels: rows.map((r) => r.label), datasets: [{ values: rows.map((r) => r.value) }] },
				type: spec.type,
				height: 200,
				colors: TC_CHART_COLORS(),
			});
		});
	}

	_render_table(payload) {
		const rows = payload.rows || [];
		this._clear_grid();
		if (!rows.length) {
			this.$tableWrap.append($('<div class="tc-empty"></div>').text(__('No SIM cards match these filters.')));
			this.$pager.empty();
			return;
		}
		// Custodian has no single backing field on SIM Card — it is the employee name,
		// falling back to the project, falling back to "Unassigned" — so it is resolved
		// once per row before the row reaches the grid, same as every other column value.
		rows.forEach((row) => {
			row.custodian_display = row.custodian_name || row.current_project || __('Unassigned');
		});
		this.table_rows = rows;
		const $mount = $('<div class="tc-table"></div>').appendTo(this.$tableWrap);
		this.datatable = new frappe.DataTable($mount.get(0), {
			columns: TC_TABLE_COLUMNS.map(({ id, label, format }) => ({
				id,
				name: __(label),
				editable: false,
				format: format || _tc_cell_text,
			})),
			data: rows,
			layout: 'fluid',
			serialNoColumn: false,
			checkboxColumn: false,
			/* The filter row ships an untranslatable English title on every box, and this
			   page already filters server-side within the operator's company scope. */
			inlineFilters: false,
			cellHeight: 35,
			language: frappe.boot.lang,
			translations: frappe.utils.datatable.get_translations(),
			direction: frappe.utils.is_rtl() ? 'rtl' : 'ltr',
		});
		/* The row is read from the data index stamped on the cell, not from its rendered
		   position: sorting a column reorders the view and leaves that index alone. */
		$mount.on('click', '.dt-scrollable .dt-cell', (e) => {
			const row = this.table_rows[cint($(e.currentTarget).attr('data-row-index'))];
			if (row) this._open_drawer(row.name);
		});
		this._render_pager(payload);
	}

	/* The table registers listeners on document, released only by destroy(); emptying the
	   wrap around it leaks one pair per render. */
	_clear_grid() {
		if (this.datatable) {
			this.datatable.destroy();
			this.datatable = null;
			this.table_rows = null;
		}
		this.$tableWrap.empty();
	}

	_render_pager(payload) {
		this.$pager.empty();
		const total = payload.total || 0;
		const pages = Math.max(1, Math.ceil(total / this.state.page_size));
		$('<span class="tc-label"></span>').text(__('Page {0} of {1} · {2} SIMs', [this.state.page, pages, total])).appendTo(this.$pager);
		$('<button class="btn btn-default btn-sm"></button>')
			.text(__('Previous'))
			.prop('disabled', this.state.page <= 1)
			.on('click', () => { this.state.page -= 1; this.refresh(); })
			.appendTo(this.$pager);
		$('<button class="btn btn-default btn-sm"></button>')
			.text(__('Next'))
			.prop('disabled', this.state.page >= pages)
			.on('click', () => { this.state.page += 1; this.refresh(); })
			.appendTo(this.$pager);
	}

	_open_drawer(sim_card) {
		this.current_sim = sim_card;
		this.$backdrop.show();
		this.$drawer.empty().show();
		$(document).on('keydown.tc-drawer', (e) => {
			if (e.key === 'Escape') this._close_drawer();
		});
		$('<div class="tc-section-head"></div>').text(__('Loading…')).appendTo(this.$drawer);
		frappe
			.call({ method: 'apex.logistay.api.telecom_control.get_sim_detail', args: { sim_card }, type: 'GET' })
			.then((r) => {
				if (this.current_sim !== sim_card) return;
				this._render_drawer(r && r.message);
			})
			.catch(() => {
				if (this.current_sim !== sim_card) return;
				this.$drawer.empty().append($('<div class="tc-empty"></div>').text(__('Could not load SIM.')));
			});
	}

	_close_drawer() {
		this.current_sim = null;
		$(document).off('keydown.tc-drawer');
		this.$backdrop.hide();
		this.$drawer.hide().empty();
	}

	_render_drawer(detail) {
		if (!detail) {
			return;
		}
		this.$drawer.empty();
		const $head = $('<div class="tc-drawer-head"></div>').appendTo(this.$drawer);
		$('<h4 class="tc-drawer-title"></h4>').append(TC_LTR(detail.mobile_number || detail.name)).appendTo($head);
		$('<button class="btn btn-default btn-sm tc-drawer-close">✕</button>')
			.attr('aria-label', __('Close'))
			.on('click', () => this._close_drawer())
			.appendTo($head);

		this._render_action_bar(detail);

		const fields = [
			[__('Status'), __(detail.status || '')],
			[__('Custodian'), detail.custodian_name || detail.current_project || __('Unassigned')],
			[__('Contract'), detail.telecom_contract || ''],
			[__('Supplier'), detail.supplier || ''],
			[__('Cost Center'), detail.current_cost_center || ''],
			[__('ICCID'), detail.iccid || ''],
			[__('Plan'), detail.plan_name || ''],
			[__('Assigned On'), detail.assigned_on || ''],
		];
		fields.forEach(([label, value]) => {
			const $row = $('<div class="tc-drawer-row"></div>').appendTo(this.$drawer);
			$('<span class="tc-label"></span>').text(label).appendTo($row);
			$('<span></span>').text(value).appendTo($row);
		});

		$('<div class="tc-section-head tc-section-head--spaced"></div>')
			.text(__('Custody History'))
			.appendTo(this.$drawer);
		(detail.history || []).forEach((h) => {
			const $row = $('<div class="tc-drawer-row"></div>').appendTo(this.$drawer);
			$('<span></span>').text(`${__(h.action)} · ${h.assignment_date || ''}`).appendTo($row);
			$('<span class="tc-label"></span>').text(h.employee_name || h.project || '').appendTo($row);
		});
	}

	_render_action_bar(detail) {
		const $bar = $('<div class="tc-actions"></div>').appendTo(this.$drawer);
		const status = detail.status;
		const btn = (label, handler, cls) =>
			$(`<button class="btn btn-sm ${cls || 'btn-default'}"></button>`).text(label).on('click', handler).appendTo($bar);

		if (status === 'Available') {
			btn(__('Assign'), () => this._custody_dialog(detail, 'Assign'), 'btn-primary');
		}
		if (status === 'Assigned') {
			btn(__('Transfer'), () => this._custody_dialog(detail, 'Transfer'), 'btn-primary');
			btn(__('Return'), () => this._custody_dialog(detail, 'Return'));
		}
		if (status === 'Available' || status === 'Assigned') {
			btn(__('Suspend'), () => this._custody_dialog(detail, 'Suspend'), 'btn-warning');
		}
		if (status === 'Suspended') {
			btn(__('Reactivate'), () => this._custody_dialog(detail, 'Reactivate'), 'btn-primary');
		}
		if (TC_RETIRE_FROM.Lost.includes(status)) {
			btn(__('Mark Lost'), () => this._custody_dialog(detail, 'Lost'), 'btn-danger');
		}
		if (TC_RETIRE_FROM.Terminated.includes(status)) {
			btn(__('Terminate'), () => this._custody_dialog(detail, 'Terminated'), 'btn-danger');
		}
		btn(__('Edit Mobile Number'), () => this._edit_mobile_dialog(detail));
		btn(__('Move to Contract'), () => this._move_contract_dialog(detail));
		btn(__('Open SIM'), () => frappe.set_route('Form', 'SIM Card', detail.name));
		if (detail.telecom_contract) {
			btn(__('Open Contract'), () => frappe.set_route('Form', 'Telecom Contract', detail.telecom_contract));
		}
	}

	_custody_dialog(detail, action) {
		const needs_custodian = action === 'Assign' || action === 'Transfer';
		const retiring = Object.prototype.hasOwnProperty.call(TC_RETIRE_FROM, action);
		const fields = [];
		if (retiring) {
			fields.push({
				fieldtype: 'HTML',
				fieldname: 'retire_warning',
				options: `<div class="text-muted">${frappe.utils.escape_html(
					__('This ends the current custody and retires the SIM. The SIM and its history are kept; the action can be undone by cancelling the custody record.'),
				)}</div>`,
			});
		}
		if (needs_custodian) {
			fields.push({ fieldname: 'custodian_type', label: __('Custodian Type'), fieldtype: 'Select', options: 'Employee\nProject', reqd: 1, default: 'Employee' });
			fields.push({ fieldname: 'employee', label: __('Employee'), fieldtype: 'Link', options: 'Employee', depends_on: "eval:doc.custodian_type=='Employee'", get_query: () => ({ filters: { status: 'Active', company: detail.company } }) });
			fields.push({ fieldname: 'project', label: __('Project'), fieldtype: 'Link', options: 'Project', depends_on: "eval:doc.custodian_type=='Project'" });
		}
		fields.push({ fieldname: 'assignment_date', label: __('Action Date'), fieldtype: 'Date', reqd: 1, default: frappe.datetime.get_today() });
		fields.push({ fieldname: 'reason', label: __('Reason'), fieldtype: 'Small Text', reqd: retiring ? 1 : 0 });

		const verb = { Lost: __('Mark Lost'), Terminated: __('Terminate') }[action] || __(action);
		const dialog = new frappe.ui.Dialog({
			title: __('{0} SIM {1}', [verb, detail.mobile_number || detail.name]),
			fields,
			primary_action_label: verb,
			primary_action: (values) => {
				dialog.hide();
				this._run_action(
					'perform_custody_action',
					{
						sim_card: detail.name,
						action,
						custodian_type: values.custodian_type,
						employee: values.employee,
						project: values.project,
						assignment_date: values.assignment_date,
						reason: values.reason,
					},
					detail.name,
				);
			},
		});
		dialog.show();
	}

	_edit_mobile_dialog(detail) {
		frappe.prompt(
			[{ fieldname: 'mobile_number', label: __('Mobile Number'), fieldtype: 'Data', reqd: 1, default: detail.mobile_number }],
			(values) =>
				this._run_action(
					'edit_mobile_number',
					{ sim_card: detail.name, mobile_number: values.mobile_number },
					detail.name,
				),
			__('Edit Mobile Number'),
			__('Save'),
		);
	}

	_move_contract_dialog(detail) {
		frappe.prompt(
			[{ fieldname: 'telecom_contract', label: __('New Contract'), fieldtype: 'Link', options: 'Telecom Contract', reqd: 1, get_query: () => ({ filters: { docstatus: 1 } }) }],
			(values) =>
				this._run_action(
					'move_to_contract',
					{ sim_card: detail.name, telecom_contract: values.telecom_contract },
					detail.name,
				),
			__('Move to Contract'),
			__('Move'),
		);
	}

	_run_action(method, args, sim_card) {
		frappe.dom.freeze(__('Working…'));
		frappe
			.call({ method: `apex.logistay.api.sim_actions.${method}`, args })
			.then((r) => {
				if (r && r.exc) {
					frappe.show_alert({ message: __('That did not go through.'), indicator: 'red' });
					return;
				}
				frappe.show_alert({ message: __('Done'), indicator: 'green' });
				this.refresh();
				if (sim_card && this.current_sim === sim_card) {
					this._open_drawer(sim_card);
				}
			})
			.catch(() => frappe.show_alert({ message: __('That did not go through.'), indicator: 'red' }))
			.always(() => frappe.dom.unfreeze());
	}
}
