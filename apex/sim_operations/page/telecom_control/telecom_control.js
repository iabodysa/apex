// Copyright (c) 2026, AFMCO and contributors
// Telecom Control — a native Frappe Desk page (frappe.ui.make_app_page). It ships
// NO stylesheet: every rule below is an inline style bound to a native Desk CSS
// variable, so light/dark theming and RTL come from the framework. Data is read
// from apex.sim_operations.api.telecom_control; custody actions POST to
// apex.sim_operations.api.sim_actions and re-render only the affected pieces.

frappe.pages['telecom-control'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Telecom Control'),
		single_column: true,
	});
	wrapper.telecom_control = new TelecomControl(page);
};

const TC_STYLE = {
	root: 'display:flex;flex-direction:column;gap:var(--margin-lg,20px);padding-block:var(--padding-md,15px);',
	filters: 'display:flex;flex-wrap:wrap;gap:var(--margin-sm,10px);align-items:flex-end;',
	cards: 'display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:var(--margin-sm,10px);',
	card: 'border:1px solid var(--border-color);border-radius:var(--border-radius-md,8px);background:var(--card-bg);padding:var(--padding-md,15px);display:flex;flex-direction:column;gap:4px;',
	card_value: 'font-size:var(--text-2xl,22px);font-weight:700;color:var(--text-color);',
	card_label: 'font-size:var(--text-sm,12px);color:var(--text-muted);',
	charts: 'display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:var(--margin-md,15px);',
	chart_box: 'border:1px solid var(--border-color);border-radius:var(--border-radius-md,8px);background:var(--card-bg);padding:var(--padding-sm,10px);min-height:220px;',
	section_head: 'font-size:var(--text-md,14px);font-weight:600;color:var(--text-muted);',
	table_wrap: 'overflow-x:auto;border:1px solid var(--border-color);border-radius:var(--border-radius-md,8px);',
	pager: 'display:flex;gap:var(--margin-sm,10px);align-items:center;justify-content:flex-end;padding-block-start:var(--padding-sm,10px);',
	empty: 'padding-block:var(--padding-xl,30px);text-align:center;color:var(--text-muted);',
	drawer: 'position:fixed;inset-block:0;inset-inline-end:0;inline-size:min(420px,92vw);background:var(--fg-color,var(--card-bg));border-inline-start:1px solid var(--border-color);box-shadow:var(--shadow-lg);padding:var(--padding-lg,20px);overflow-y:auto;z-index:1030;display:none;',
	drawer_row: 'display:flex;justify-content:space-between;gap:var(--margin-sm,10px);padding-block:6px;border-block-end:1px solid var(--border-color);font-size:var(--text-sm,12px);',
	actions: 'display:flex;flex-wrap:wrap;gap:8px;margin-block:var(--margin-sm,10px);',
};

const TC_STATUS_COLOR = {
	Assigned: 'blue',
	Available: 'green',
	Suspended: 'orange',
	Lost: 'red',
	Terminated: 'gray',
};

const TC_FILTER_KEY = 'telecom_control_filters';

class TelecomControl {
	constructor(page) {
		this.page = page;
		this.filters = this._load_filters();
		this.state = { page: 1, page_size: 20 };
		this.charts = {};
		this._build_skeleton();
		this.page.set_primary_action(__('Refresh'), () => this.refresh(), 'refresh');
		this.refresh();
	}

	// --- persistence ---------------------------------------------------------
	_load_filters() {
		try {
			return JSON.parse(localStorage.getItem(TC_FILTER_KEY)) || {};
		} catch (e) {
			return {};
		}
	}

	_save_filters() {
		localStorage.setItem(TC_FILTER_KEY, JSON.stringify(this.filters));
	}

	// --- skeleton ------------------------------------------------------------
	_build_skeleton() {
		this.$root = $('<div class="telecom-control"></div>').attr('style', TC_STYLE.root).appendTo(this.page.main);
		this.$filters = $('<div class="tc-filters"></div>').attr('style', TC_STYLE.filters).appendTo(this.$root);
		this.$cards = $('<div class="tc-cards"></div>').attr('style', TC_STYLE.cards).appendTo(this.$root);
		this.$charts = $('<div class="tc-charts"></div>').attr('style', TC_STYLE.charts).appendTo(this.$root);
		$('<div></div>').attr('style', TC_STYLE.section_head).text(__('SIM Cards')).appendTo(this.$root);
		this.$tableWrap = $('<div class="tc-table-wrap"></div>').attr('style', TC_STYLE.table_wrap).appendTo(this.$root);
		this.$pager = $('<div class="tc-pager"></div>').attr('style', TC_STYLE.pager).appendTo(this.$root);
		this.$empty = $('<div class="tc-empty"></div>').attr('style', TC_STYLE.empty).appendTo(this.$root).hide();
		this.$drawer = $('<div class="tc-drawer"></div>').attr('style', TC_STYLE.drawer).appendTo(document.body);
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
			.appendTo($('<div></div>').attr('style', 'align-self:flex-end;').appendTo(this.$filters));
	}

	_on_filter_change(field, value) {
		if (value) {
			this.filters[field] = value;
		} else {
			delete this.filters[field];
		}
		this.state.page = 1;
		this._save_filters();
		this.refresh();
	}

	_clear_filters() {
		this.filters = {};
		this._save_filters();
		Object.values(this.controls).forEach((c) => c.set_value(''));
		this.state.page = 1;
		this.refresh();
	}

	// --- data ----------------------------------------------------------------
	refresh() {
		this._render_loading();
		const args = { filters: this.filters };
		Promise.all([
			this._call('get_summary_cards', args),
			this._call('get_charts', args),
			this._call('get_sim_rows', { ...args, page: this.state.page, page_size: this.state.page_size }),
		])
			.then(([cards, charts, rows]) => {
				this.$empty.hide();
				this._render_cards(cards || {});
				this._render_charts(charts || {});
				this._render_table(rows || { rows: [], total: 0 });
			})
			.catch(() => this._render_error());
	}

	_call(method, args) {
		return frappe
			.call({ method: `apex.sim_operations.api.telecom_control.${method}`, args, type: 'GET' })
			.then((r) => r && r.message);
	}

	// --- render --------------------------------------------------------------
	_render_loading() {
		this.$empty.text(__('Loading…')).show();
	}

	_render_error() {
		this.$empty.empty().show();
		$('<div></div>').css('margin-block-end', '10px').text(__('Could not load Telecom Control. Please retry.')).appendTo(this.$empty);
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
			const $card = $('<div></div>').attr('style', TC_STYLE.card).appendTo(this.$cards);
			$('<div></div>').attr('style', TC_STYLE.card_value).text(c.value).appendTo($card);
			$('<div></div>').attr('style', TC_STYLE.card_label).text(c.label).appendTo($card);
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
			const box = $('<div></div>').attr('style', TC_STYLE.chart_box).appendTo(this.$charts).get(0);
			if (!rows.length) {
				$(box).append($('<div></div>').attr('style', TC_STYLE.card_label).text(`${spec.title}: ${__('No data')}`));
				return;
			}
			this.charts[spec.key] = new frappe.Chart(box, {
				title: spec.title,
				data: { labels: rows.map((r) => r.label), datasets: [{ values: rows.map((r) => r.value) }] },
				type: spec.type,
				height: 200,
				colors: ['#5e64ff', '#743ee2', '#ff5858', '#ffa00a', '#28a745'],
			});
		});
	}

	_render_table(payload) {
		const rows = payload.rows || [];
		this.$tableWrap.empty();
		if (!rows.length) {
			this.$tableWrap.append($('<div></div>').attr('style', TC_STYLE.empty).text(__('No SIM cards match these filters.')));
			this.$pager.empty();
			return;
		}
		const $table = $('<table class="table table-hover" style="margin:0;"></table>').appendTo(this.$tableWrap);
		const heads = [__('Mobile Number'), __('Status'), __('Custodian'), __('Contract'), __('Cost Center')];
		const $tr = $('<tr></tr>').appendTo($('<thead></thead>').appendTo($table));
		heads.forEach((h) => $('<th></th>').text(h).appendTo($tr));
		const $tbody = $('<tbody></tbody>').appendTo($table);
		rows.forEach((row) => {
			const $r = $('<tr style="cursor:pointer;"></tr>').on('click', () => this._open_drawer(row.name)).appendTo($tbody);
			$('<td></td>').text(row.mobile_number || '').appendTo($r);
			const $st = $('<td></td>').appendTo($r);
			$(`<span class="indicator-pill no-indicator-dot ${TC_STATUS_COLOR[row.status] || 'gray'}"></span>`).text(__(row.status || '')).appendTo($st);
			$('<td></td>').text(row.custodian_name || row.current_project || __('Unassigned')).appendTo($r);
			$('<td></td>').text(row.telecom_contract || '').appendTo($r);
			$('<td></td>').text(row.current_cost_center || '').appendTo($r);
		});
		this._render_pager(payload);
	}

	_render_pager(payload) {
		this.$pager.empty();
		const total = payload.total || 0;
		const pages = Math.max(1, Math.ceil(total / this.state.page_size));
		$('<span></span>').attr('style', TC_STYLE.card_label).text(__('Page {0} of {1} · {2} SIMs', [this.state.page, pages, total])).appendTo(this.$pager);
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

	// --- drawer + actions ----------------------------------------------------
	_open_drawer(sim_card) {
		this.current_sim = sim_card;
		this.$drawer.empty().show();
		$('<div></div>').attr('style', TC_STYLE.section_head).text(__('Loading…')).appendTo(this.$drawer);
		frappe
			.call({ method: 'apex.sim_operations.api.telecom_control.get_sim_detail', args: { sim_card }, type: 'GET' })
			.then((r) => this._render_drawer(r && r.message))
			.catch(() => this.$drawer.empty().append($('<div></div>').attr('style', TC_STYLE.empty).text(__('Could not load SIM.'))));
	}

	_render_drawer(detail) {
		if (!detail) {
			return;
		}
		this.$drawer.empty();
		const $head = $('<div style="display:flex;justify-content:space-between;align-items:center;"></div>').appendTo(this.$drawer);
		$('<h4 style="margin:0;"></h4>').text(detail.mobile_number || detail.name).appendTo($head);
		$('<button class="btn btn-default btn-sm">✕</button>').on('click', () => this.$drawer.hide()).appendTo($head);

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
			const $row = $('<div></div>').attr('style', TC_STYLE.drawer_row).appendTo(this.$drawer);
			$('<span></span>').attr('style', TC_STYLE.card_label).text(label).appendTo($row);
			$('<span></span>').text(value).appendTo($row);
		});

		$('<div></div>').attr('style', TC_STYLE.section_head).css('margin-block-start', '12px').text(__('Custody History')).appendTo(this.$drawer);
		(detail.history || []).forEach((h) => {
			const $row = $('<div></div>').attr('style', TC_STYLE.drawer_row).appendTo(this.$drawer);
			$('<span></span>').text(`${__(h.action)} · ${h.assignment_date || ''}`).appendTo($row);
			$('<span></span>').attr('style', TC_STYLE.card_label).text(h.employee_name || h.project || '').appendTo($row);
		});
	}

	_render_action_bar(detail) {
		const $bar = $('<div></div>').attr('style', TC_STYLE.actions).appendTo(this.$drawer);
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
		btn(__('Edit Mobile Number'), () => this._edit_mobile_dialog(detail));
		btn(__('Move to Contract'), () => this._move_contract_dialog(detail));
		btn(__('Open SIM'), () => frappe.set_route('Form', 'SIM Card', detail.name));
		if (detail.telecom_contract) {
			btn(__('Open Contract'), () => frappe.set_route('Form', 'Telecom Contract', detail.telecom_contract));
		}
	}

	_custody_dialog(detail, action) {
		const needs_custodian = action === 'Assign' || action === 'Transfer';
		const fields = [];
		if (needs_custodian) {
			fields.push({ fieldname: 'custodian_type', label: __('Custodian Type'), fieldtype: 'Select', options: 'Employee\nProject', reqd: 1, default: 'Employee' });
			fields.push({ fieldname: 'employee', label: __('Employee'), fieldtype: 'Link', options: 'Employee', depends_on: "eval:doc.custodian_type=='Employee'", get_query: () => ({ filters: { status: 'Active', company: detail.company } }) });
			fields.push({ fieldname: 'project', label: __('Project'), fieldtype: 'Link', options: 'Project', depends_on: "eval:doc.custodian_type=='Project'" });
		}
		fields.push({ fieldname: 'assignment_date', label: __('Action Date'), fieldtype: 'Date', reqd: 1, default: frappe.datetime.get_today() });
		fields.push({ fieldname: 'reason', label: __('Reason'), fieldtype: 'Small Text' });

		const dialog = new frappe.ui.Dialog({
			title: __('{0} SIM {1}', [__(action), detail.mobile_number || detail.name]),
			fields,
			primary_action_label: __(action),
			primary_action: (values) => {
				dialog.hide();
				this._run_action('perform_custody_action', {
					sim_card: detail.name,
					action,
					custodian_type: values.custodian_type,
					employee: values.employee,
					project: values.project,
					assignment_date: values.assignment_date,
					reason: values.reason,
				});
			},
		});
		dialog.show();
	}

	_edit_mobile_dialog(detail) {
		frappe.prompt(
			[{ fieldname: 'mobile_number', label: __('Mobile Number'), fieldtype: 'Data', reqd: 1, default: detail.mobile_number }],
			(values) => this._run_action('edit_mobile_number', { sim_card: detail.name, mobile_number: values.mobile_number }),
			__('Edit Mobile Number'),
			__('Save'),
		);
	}

	_move_contract_dialog(detail) {
		frappe.prompt(
			[{ fieldname: 'telecom_contract', label: __('New Contract'), fieldtype: 'Link', options: 'Telecom Contract', reqd: 1, get_query: () => ({ filters: { docstatus: 1 } }) }],
			(values) => this._run_action('move_to_contract', { sim_card: detail.name, telecom_contract: values.telecom_contract }),
			__('Move to Contract'),
			__('Move'),
		);
	}

	_run_action(method, args) {
		frappe.dom.freeze(__('Working…'));
		frappe
			.call({ method: `apex.sim_operations.api.sim_actions.${method}`, args })
			.then((r) => {
				frappe.show_alert({ message: __('Done'), indicator: 'green' });
				// Refresh cards + rows, and the open drawer, without a full page reload.
				this.refresh();
				if (this.current_sim) {
					this._open_drawer(this.current_sim);
				}
			})
			.finally(() => frappe.dom.unfreeze());
	}
}
