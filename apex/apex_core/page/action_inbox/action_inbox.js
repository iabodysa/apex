// Copyright (c) 2026, AFMCO and contributors
// [#ns38m9]

frappe.pages['action-inbox'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('My Work Center'),
		single_column: true,
	});
	wrapper.action_inbox = new ActionInbox(page);
};

// Desk pages ship no stylesheet — structural layout is inline styles bound to
// native Desk CSS variables (theme/dark-mode aware). Status colour stays on
// native indicator-pills.
const AI_STYLE = {
	root: 'display:flex;flex-direction:column;gap:var(--margin-lg,20px);padding-block:var(--padding-md,15px);',
	section: 'display:flex;flex-direction:column;gap:var(--margin-sm,10px);',
	section_head:
		'font-size:var(--text-md,14px);font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.04em;',
	list: 'display:flex;flex-direction:column;gap:var(--margin-sm,10px);',
	card:
		'border:1px solid var(--border-color);border-radius:var(--border-radius-md,8px);background:var(--card-bg);padding:var(--padding-md,15px);display:flex;flex-direction:column;gap:8px;',
	card_head: 'display:flex;align-items:center;gap:8px;flex-wrap:wrap;',
	card_link: 'font-weight:600;color:var(--text-color);',
	card_meta: 'display:flex;gap:var(--margin-md,15px);font-size:var(--text-sm,12px);flex-wrap:wrap;',
	card_desc: 'font-size:var(--text-sm,12px);color:var(--text-color);',
	card_actions: 'display:flex;gap:8px;flex-wrap:wrap;',
	empty: 'padding-block:var(--padding-xl,30px);text-align:center;font-size:var(--text-md,14px);',
};

class ActionInbox {
	constructor(page) {
		this.page = page;
		// [#9y9w2i]
		this._build_skeleton();
		this.page.set_primary_action(__('Refresh'), () => this.refresh(), 'refresh');
		// [#4u0s03]
		frappe.realtime.on('notification', frappe.utils.debounce(() => this.refresh(), 5000));
		this.refresh();
	}

	_build_skeleton() {
		this.$root = $('<div class="action-inbox"></div>').attr('style', AI_STYLE.root).appendTo(this.page.main);

		this.$approvalsSection = this._section(__('Pending Approvals'));
		this.$approvals = this.$approvalsSection.find('.ai-list');
		this.$tasksSection = this._section(__('Assigned Tasks'));
		this.$tasks = this.$tasksSection.find('.ai-list');
		this.$submittedSection = this._section(__('My Open Submissions'));
		this.$submitted = this.$submittedSection.find('.ai-list');
		this.$closedSection = this._section(__('Closed in the Last 48h'));
		this.$closed = this.$closedSection.find('.ai-list');
		this.$notifsSection = this._section(__('Notifications'));
		this.$notifs = this.$notifsSection.find('.ai-list');

		// [#gqzws7]
		this.$empty = $('<div class="ai-empty text-muted"></div>').attr('style', AI_STYLE.empty).appendTo(this.$root);
		this._allSections = [
			this.$approvalsSection, this.$tasksSection, this.$submittedSection,
			this.$closedSection, this.$notifsSection,
		];
	}

	_section(title) {
		const $s = $('<section class="ai-section"></section>').attr('style', AI_STYLE.section).appendTo(this.$root);
		// Uppercasing + letter-spacing break Arabic shaping → drop both in RTL.
		const head = frappe.utils.is_rtl()
			? 'font-size:var(--text-md,14px);font-weight:600;color:var(--text-muted);'
			: AI_STYLE.section_head;
		$('<header class="ai-section-head"></header>').attr('style', head).text(title).appendTo($s);
		$('<div class="ai-list"></div>').attr('style', AI_STYLE.list).appendTo($s);
		return $s;
	}

	refresh() {
		this._render_loading();
		frappe
			.call('apex.apex_core.worklist.my_work_center.get_my_work')
			.then((r) => this._render((r && r.message) || {}))
			.catch(() => this._render_error());
	}

	// [#fltkjy]
	_render(data) {
		const awaiting = data.awaiting_action || {};
		const workflow_actions = awaiting.workflow_actions || [];
		const todos = awaiting.todos || [];
		const submitted = data.my_open_submitted || [];
		const closed = data.my_recent_closed || [];
		const notifs = data.my_notifications || [];

		[this.$approvals, this.$tasks, this.$submitted, this.$closed, this.$notifs].forEach(($l) => $l.empty());

		this.$approvalsSection.toggle(workflow_actions.length > 0);
		this.$tasksSection.toggle(todos.length > 0);
		this.$submittedSection.toggle(submitted.length > 0);
		this.$closedSection.toggle(closed.length > 0);
		this.$notifsSection.toggle(notifs.length > 0);

		const anything = workflow_actions.length || todos.length || submitted.length || closed.length || notifs.length;
		if (!anything) {
			this.$empty.text(__('Nothing on your work center right now.')).show();
			return;
		}
		this.$empty.empty().hide();

		workflow_actions.forEach((row) => this._workflow_card(row));
		todos.forEach((row) => this._todo_card(row));
		submitted.forEach((row) => this._doc_card(this.$submitted, row, 'green'));
		closed.forEach((row) => this._doc_card(this.$closed, row, 'gray'));
		notifs.forEach((row) => this._notification_card(row));
	}

	_render_loading() {
		this._allSections.forEach(($s) => $s.hide());
		this.$empty.text(__('Loading…')).show();
	}

	_render_error() {
		this._allSections.forEach(($s) => $s.hide());
		this.$empty.empty().show();
		$('<div class="ai-error-msg"></div>')
			.css('margin-block-end', 'var(--margin-sm, 10px)')
			.text(__('Could not load your work center. Please retry.'))
			.appendTo(this.$empty);
		$('<button class="btn btn-default btn-sm"></button>')
			.text(__('Retry'))
			.on('click', () => this.refresh())
			.appendTo(this.$empty);
	}

	// [#ml5epr]
	_workflow_card(row) {
		const $card = $('<div class="ai-card ai-card--workflow"></div>').attr('style', AI_STYLE.card).appendTo(this.$approvals);
		const $head = $('<div class="ai-card-head"></div>').attr('style', AI_STYLE.card_head).appendTo($card);
		$('<span class="indicator-pill no-indicator-dot blue"></span>').text(row.reference_doctype || '').appendTo($head);
		$('<a class="ai-card-link" href="#"></a>')
			.attr('style', AI_STYLE.card_link)
			.text(row.reference_name || '')
			.on('click', (e) => {
				e.preventDefault();
				frappe.set_route('Form', row.reference_doctype, row.reference_name);
			})
			.appendTo($head);

		const $meta = $('<div class="ai-card-meta text-muted"></div>').attr('style', AI_STYLE.card_meta).appendTo($card);
		$('<span class="ai-card-state"></span>').text(__('State: {0}', [row.workflow_state || ''])).appendTo($meta);

		const $actions = $('<div class="ai-card-actions"></div>').attr('style', AI_STYLE.card_actions).appendTo($card);
		$('<span class="ai-actions-load text-muted"></span>').text(__('Loading actions…')).appendTo($actions);
		frappe
			.xcall('frappe.model.workflow.get_transitions', {
				doc: { doctype: row.reference_doctype, name: row.reference_name },
			})
			.then((transitions) => this._render_transitions($actions, $card, row, transitions || []))
			.catch(() => {
				$actions.empty();
				$('<span class="ai-actions-none text-muted"></span>').text(__('No actions available.')).appendTo($actions);
			});
	}

	_render_transitions($actions, $card, row, transitions) {
		$actions.empty();
		if (!transitions.length) {
			$('<span class="ai-actions-none text-muted"></span>').text(__('No actions available.')).appendTo($actions);
			return;
		}
		transitions.forEach((t) => {
			const action = t.action || '';
			const danger = /reject|cancel/i.test(action);
			const cls = danger ? 'btn-danger' : 'btn-primary';
			$(`<button class="btn btn-sm ${cls} ai-action-btn"></button>`)
				.text(__(action))
				.on('click', () => this._apply_workflow($card, row, action))
				.appendTo($actions);
		});
	}

	_apply_workflow($card, row, action) {
		frappe.dom.freeze(__('Applying…'));
		frappe
			.xcall('frappe.model.workflow.apply_workflow', {
				doc: { doctype: row.reference_doctype, name: row.reference_name },
				action,
			})
			.then((doc) => {
				frappe.show_alert({ message: __('{0} applied', [__(action)]), indicator: 'green' });
				this.refresh();
			})
			.catch(() => {
				frappe.show_alert({ message: __('Could not apply {0}', [__(action)]), indicator: 'red' });
				this.refresh();
			})
			.finally(() => frappe.dom.unfreeze());
	}

	// [#jwf4jo]
	_todo_card(row) {
		const $card = $('<div class="ai-card ai-card--todo"></div>').attr('style', AI_STYLE.card).appendTo(this.$tasks);
		const $head = $('<div class="ai-card-head"></div>').attr('style', AI_STYLE.card_head).appendTo($card);
		$('<span class="indicator-pill no-indicator-dot orange"></span>').text(__('Task')).appendTo($head);
		$('<a class="ai-card-link" href="#"></a>')
			.attr('style', AI_STYLE.card_link)
			.text(`${row.reference_doctype || ''}: ${row.reference_name || ''}`)
			.on('click', (e) => {
				e.preventDefault();
				frappe.set_route('Form', row.reference_doctype, row.reference_name);
			})
			.appendTo($head);

		if (row.description) {
			$('<div class="ai-card-desc"></div>').attr('style', AI_STYLE.card_desc).html(frappe.utils.escape_html(row.description)).appendTo($card);
		}
		const $meta = $('<div class="ai-card-meta text-muted"></div>').attr('style', AI_STYLE.card_meta).appendTo($card);
		if (row.priority) {
			$('<span class="ai-card-priority"></span>').text(__('Priority: {0}', [row.priority])).appendTo($meta);
		}
		if (row.date) {
			$('<span class="ai-card-date"></span>').text(__('Due: {0}', [row.date])).appendTo($meta);
		}
		const $actions = $('<div class="ai-card-actions"></div>').attr('style', AI_STYLE.card_actions).appendTo($card);
		$('<button class="btn btn-sm btn-default ai-action-btn"></button>')
			.text(__('Open'))
			.on('click', () => frappe.set_route('Form', row.reference_doctype, row.reference_name))
			.appendTo($actions);
		$('<button class="btn btn-sm btn-primary ai-action-btn"></button>')
			.text(__('Close'))
			.on('click', () => this._close_todo($card, row))
			.appendTo($actions);
	}

	_close_todo($card, row) {
		frappe.dom.freeze(__('Closing…'));
		frappe
			.xcall('frappe.client.set_value', { doctype: 'ToDo', name: row.name, fieldname: 'status', value: 'Closed' })
			.then(() => {
				frappe.show_alert({ message: __('Task closed'), indicator: 'green' });
				this.refresh();
			})
			.catch(() => {
				frappe.show_alert({ message: __('Could not close the task'), indicator: 'red' });
				this.refresh();
			})
			.finally(() => frappe.dom.unfreeze());
	}

	// [#sexmnv]
	_doc_card($list, row, color) {
		const $card = $('<div class="ai-card ai-card--doc"></div>').attr('style', AI_STYLE.card).appendTo($list);
		const $head = $('<div class="ai-card-head"></div>').attr('style', AI_STYLE.card_head).appendTo($card);
		$(`<span class="indicator-pill no-indicator-dot ${color}"></span>`).text(row.doctype || '').appendTo($head);
		$('<a class="ai-card-link" href="#"></a>')
			.attr('style', AI_STYLE.card_link)
			.text(row.name || '')
			.on('click', (e) => {
				e.preventDefault();
				frappe.set_route('Form', row.doctype, row.name);
			})
			.appendTo($head);
		const $meta = $('<div class="ai-card-meta text-muted"></div>').attr('style', AI_STYLE.card_meta).appendTo($card);
		$('<span class="ai-card-state"></span>').text(__('Status: {0}', [row.status || ''])).appendTo($meta);
	}

	// [#7e345x]
	_notification_card(row) {
		const $card = $('<div class="ai-card ai-card--notif"></div>').attr('style', AI_STYLE.card).appendTo(this.$notifs);
		const $head = $('<div class="ai-card-head"></div>').attr('style', AI_STYLE.card_head).appendTo($card);
		$(`<span class="indicator-pill no-indicator-dot ${row.read ? 'gray' : 'blue'}"></span>`)
			.text(row.type || __('Notification'))
			.appendTo($head);
		$('<span class="ai-card-subject"></span>').css('font-weight', '600').text(row.subject || '').appendTo($head);
		if (row.document_type && row.document_name) {
			$('<a class="ai-card-link" href="#"></a>')
				.attr('style', AI_STYLE.card_link)
				.text(`${row.document_type}: ${row.document_name}`)
				.on('click', (e) => {
					e.preventDefault();
					frappe.set_route('Form', row.document_type, row.document_name);
				})
				.appendTo($card);
		}
	}
}
