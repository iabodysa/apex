"""Seed the 'Apex My Work Center' Custom HTML Block.

Custom HTML Block is autonamed by user (naming_rule: Set by user), so it is NOT
a standard fixture file — it must be seeded programmatically.

This seeder tracks a SHA-256 hash of html+script in the block's ``description``
field. On every migrate it compares the current source hash to the stored hash
and updates the block when they differ — so source code changes propagate
automatically. The source file is the single source of truth for this block.

The block is kept public (private=0) so all desk users can see it. The HTML
scaffolding goes in the `html` field (no inline <script> tags — Frappe strips
them via frappe.dom.remove_script_and_style). All JavaScript goes in the
dedicated `script` field; it executes in the main window scope with access to
`root_element` (the shadow root's container element).

Called from both after_install and after_migrate hooks in hooks.py.
"""

from __future__ import annotations

import hashlib
import re

import frappe

_HASH_TAG = "apex-src-hash"

def _src_hash() -> str:
    """Short SHA-256 of html+script used to detect source changes."""
    return hashlib.sha256((_HTML + _SCRIPT).encode()).hexdigest()[:16]

def _tagged_html(html: str, h: str) -> str:
    """Prepend a hidden hash comment to html so future runs can detect changes."""
    return f"<!-- {_HASH_TAG}:{h} -->\n{html}"

def _stored_hash(html: str) -> str:
    """Extract the stored hash from a tagged html string, or '' if absent."""
    m = re.match(rf"<!-- {_HASH_TAG}:([0-9a-f]+) -->", html or "")
    return m.group(1) if m else ""

BLOCK_NAME = "Apex My Work Center"

# ---------------------------------------------------------------------------
# HTML scaffolding — NO <script> or <style> tags (Frappe strips them).
# All styling is done via Frappe desk CSS classes available in the shadow root.
# ---------------------------------------------------------------------------
_HTML = """<div id="mwc-root" style="padding:12px 0;">
  <div id="mwc-loading" class="text-muted" style="padding:8px 0;">Loading…</div>
  <div id="mwc-error" style="display:none;padding:8px 0;">
    <span class="text-muted">Could not load work center.</span>
    <button id="mwc-retry" class="btn btn-sm btn-default" style="margin-left:8px;">Retry</button>
  </div>
  <div id="mwc-body" style="display:none;">
    <ul id="mwc-tabs" class="nav nav-tabs" style="margin-bottom:12px;"></ul>
    <div id="mwc-panes"></div>
  </div>
</div>"""

# ---------------------------------------------------------------------------
# JavaScript — runs in window scope; root_element is injected by Frappe and
# points to the shadow root container. jQuery does NOT pierce the shadow root,
# so all DOM manipulation uses root_element.querySelector().
# ---------------------------------------------------------------------------
_SCRIPT = r"""
(function () {
  // root_element is provided by Frappe's shadow DOM runner and points at the
  // custom block's container inside the shadow root.
  var root = root_element;

  var $ = function (sel) { return root.querySelector(sel); };

  var elLoading = $('#mwc-loading');
  var elError   = $('#mwc-error');
  var elBody    = $('#mwc-body');
  var elTabs    = $('#mwc-tabs');
  var elPanes   = $('#mwc-panes');
  var retryBtn  = $('#mwc-retry');

  // Active tab tracking — survives refresh because it is in a closure.
  var activeTab = 'needs_action';

  // Tab definitions: id, label, empty-state message.
  var TAB_DEFS = [
    { id: 'needs_action',  label: 'Needs Action',   empty: 'No pending approvals' },
    { id: 'assigned',      label: 'Assigned',        empty: 'No open tasks'        },
    { id: 'my_documents',  label: 'My Documents',    empty: 'No active documents'  },
    { id: 'notifications', label: 'Notifications',   empty: 'No notifications'     },
  ];

  // Color map for indicator pills.
  var PILL_COLORS = {
    pending:  'blue',
    assigned: 'orange',
    active:   'green',
    closed:   'grey',
    read:     'grey',
    unread:   'blue',
    rejected: 'red',
  };

  // ---------------------------------------------------------------------------
  // Tab switching — manual active-class management; Bootstrap JS data-toggle
  // queries document and misses shadow-root elements.
  // ---------------------------------------------------------------------------
  function switch_tab(tabId) {
    activeTab = tabId;
    TAB_DEFS.forEach(function (t) {
      var li   = root.querySelector('#mwc-tab-li-' + t.id);
      var pane = root.querySelector('#mwc-pane-' + t.id);
      if (!li || !pane) return;
      if (t.id === tabId) {
        li.classList.add('active');
        pane.style.display = '';
      } else {
        li.classList.remove('active');
        pane.style.display = 'none';
      }
    });
  }

  // ---------------------------------------------------------------------------
  // Render helpers
  // ---------------------------------------------------------------------------
  function pill(color, text) {
    return '<span class="indicator-pill ' + (color || 'grey') + '" style="margin-right:6px;">'
           + frappe.utils.escape_html(text || '') + '</span>';
  }

  function row_html(opts) {
    // opts: { color, title, href, doctype_label, meta_text, action_html, sub_text }
    var line1 = pill(opts.color, opts.color.charAt(0).toUpperCase() + opts.color.slice(1));
    if (opts.href) {
      line1 += '<a href="' + opts.href + '" style="font-weight:500;">'
             + frappe.utils.escape_html(opts.title) + '</a>';
    } else {
      line1 += '<span style="font-weight:500;">' + frappe.utils.escape_html(opts.title) + '</span>';
    }
    line1 += '<span style="flex:1 1 auto;"></span>';
    if (opts.doctype_label) {
      line1 += '<span class="text-muted" style="font-size:11px;margin-right:8px;">'
             + frappe.utils.escape_html(opts.doctype_label) + '</span>';
    }
    if (opts.meta_text) {
      line1 += '<span class="text-muted" style="font-size:11px;margin-right:8px;">'
             + frappe.utils.escape_html(opts.meta_text) + '</span>';
    }
    if (opts.action_html) {
      line1 += opts.action_html;
    }
    var html = '<div style="display:flex;align-items:center;padding:6px 0;border-bottom:1px solid var(--border-color,#e8e8e8);">'
             + line1 + '</div>';
    if (opts.sub_text) {
      html += '<div class="text-muted" style="font-size:11px;padding:2px 0 4px 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'
            + frappe.utils.escape_html(opts.sub_text) + '</div>';
    }
    return html;
  }

  function empty_state(msg) {
    return '<div class="text-muted" style="padding:12px 0;">' + frappe.utils.escape_html(msg) + '</div>';
  }

  // ---------------------------------------------------------------------------
  // Transition buttons (Needs Action tab) — fetched lazily per workflow action.
  // ---------------------------------------------------------------------------
  function render_transition_buttons(wa, pane) {
    if (wa.source !== 'workflow') return;
    frappe.xcall('frappe.model.workflow.get_transitions', {
      doc: { doctype: wa.reference_doctype, name: wa.reference_name }
    }).then(function (transitions) {
      var btn_container = root.querySelector('#mwc-btns-' + wa.name);
      if (!btn_container) return;
      var btns = '';
      (transitions || []).forEach(function (t) {
        var color = (t.action || '').toLowerCase().indexOf('reject') >= 0 ? 'red' : 'primary';
        btns += '<button class="btn btn-sm btn-' + color + '"'
              + ' data-wa="' + frappe.utils.escape_html(wa.name) + '"'
              + ' data-doctype="' + frappe.utils.escape_html(wa.reference_doctype) + '"'
              + ' data-docname="' + frappe.utils.escape_html(wa.reference_name) + '"'
              + ' data-action="' + frappe.utils.escape_html(t.action) + '"'
              + ' style="margin-left:4px;">'
              + frappe.utils.escape_html(t.action) + '</button>';
      });
      btn_container.innerHTML = btns || '';
      // Attach click handlers
      btn_container.querySelectorAll('button').forEach(function (btn) {
        btn.addEventListener('click', function (e) {
          e.preventDefault();
          apply_transition(btn);
        });
      });
    }).catch(function () {
      // Silently skip — transitions unavailable (permissions or workflow state changed).
    });
  }

  function apply_transition(btn) {
    var doctype  = btn.dataset.doctype;
    var docname  = btn.dataset.docname;
    var action   = btn.dataset.action;
    frappe.dom.freeze('Applying…');
    frappe.xcall('frappe.model.workflow.apply_workflow', {
      doc: { doctype: doctype, name: docname },
      action: action,
    }).then(function () {
      frappe.dom.unfreeze();
      frappe.show_alert({ message: action + ': ' + docname, indicator: 'green' });
      load();
    }).catch(function (err) {
      frappe.dom.unfreeze();
      frappe.show_alert({ message: (err && err.message) || 'Action failed', indicator: 'red' });
    });
  }

  // ---------------------------------------------------------------------------
  // Close ToDo
  // ---------------------------------------------------------------------------
  function close_todo(todo_name, btn) {
    btn.disabled = true;
    frappe.call({
      method: 'frappe.client.set_value',
      args: { doctype: 'ToDo', name: todo_name, fieldname: 'status', value: 'Closed' },
      callback: function () {
        frappe.show_alert({ message: 'Task closed', indicator: 'green' });
        load();
      },
      error: function () {
        btn.disabled = false;
        frappe.show_alert({ message: 'Could not close task', indicator: 'red' });
      },
    });
  }

  // ---------------------------------------------------------------------------
  // Render tabs (build tab bar and pane list from current data)
  // ---------------------------------------------------------------------------
  function render(data) {
    var wa_list    = (data.needs_action && data.needs_action.workflow_actions) || [];
    var todo_list  = (data.needs_action && data.needs_action.todos) || [];
    var notif_list = data.notifications || [];
    var summary    = data.summary || {};

    // Count badges
    var counts = {
      needs_action:  summary.needs_action  || 0,
      assigned:      summary.assigned      || 0,
      my_documents:  0,   // placeholder (Number Cards already exist above)
      notifications: summary.notifications || 0,
    };

    // Build tab bar
    elTabs.innerHTML = TAB_DEFS.map(function (t) {
      var is_active = t.id === activeTab ? ' active' : '';
      var cnt = counts[t.id] || 0;
      var label_txt = t.label + (cnt > 0 ? ' (' + cnt + ')' : ' (0)');
      return '<li id="mwc-tab-li-' + t.id + '" class="' + is_active + '">'
           + '<a href="#" data-tab="' + t.id + '">' + label_txt + '</a></li>';
    }).join('');

    // Tab click handler
    elTabs.querySelectorAll('a[data-tab]').forEach(function (a) {
      a.addEventListener('click', function (e) {
        e.preventDefault();
        switch_tab(a.dataset.tab);
      });
    });

    // Build pane content for each tab
    var panes_html = '';

    // --- Needs Action ---
    var na_html = '';
    wa_list.forEach(function (wa) {
      var href = '/app/' + frappe.router.slug(wa.reference_doctype) + '/' + encodeURIComponent(wa.reference_name);
      na_html += row_html({
        color: 'blue',
        title: wa.reference_name,
        href:  href,
        doctype_label: wa.reference_doctype,
        meta_text: wa.workflow_state || '',
        action_html: '<span id="mwc-btns-' + frappe.utils.escape_html(wa.name) + '" style="display:inline-flex;align-items:center;"></span>',
      });
    });
    panes_html += '<div id="mwc-pane-needs_action" style="' + (activeTab === 'needs_action' ? '' : 'display:none;') + '">'
               + (na_html || empty_state('No pending approvals')) + '</div>';

    // --- Assigned (ToDos) ---
    var asgn_html = '';
    todo_list.forEach(function (td) {
      var href = td.reference_doctype && td.reference_name
        ? '/app/' + frappe.router.slug(td.reference_doctype) + '/' + encodeURIComponent(td.reference_name)
        : '';
      asgn_html += row_html({
        color: 'orange',
        title: td.reference_name || td.name,
        href:  href,
        doctype_label: td.reference_doctype || 'ToDo',
        meta_text: td.date ? frappe.datetime.str_to_user(td.date) : '',
        action_html: '<button class="btn btn-sm btn-default" data-todo="' + frappe.utils.escape_html(td.name) + '"'
                   + ' style="margin-left:4px;">Close</button>',
        sub_text: td.description || '',
      });
    });
    panes_html += '<div id="mwc-pane-assigned" style="' + (activeTab === 'assigned' ? '' : 'display:none;') + '">'
               + (asgn_html || empty_state('No open tasks')) + '</div>';

    // --- My Documents (placeholder — Number Cards above already serve this) ---
    panes_html += '<div id="mwc-pane-my_documents" style="' + (activeTab === 'my_documents' ? '' : 'display:none;') + '">'
               + empty_state('No active documents') + '</div>';

    // --- Notifications ---
    var notif_html = '';
    notif_list.forEach(function (n) {
      var color = n.read ? 'grey' : 'blue';
      var href  = n.document_type && n.document_name
        ? '/app/' + frappe.router.slug(n.document_type) + '/' + encodeURIComponent(n.document_name)
        : '';
      notif_html += row_html({
        color: color,
        title: n.subject || n.name,
        href:  href,
        doctype_label: n.type || '',
        meta_text: n.creation ? frappe.datetime.prettyDate(n.creation) : '',
      });
    });
    panes_html += '<div id="mwc-pane-notifications" style="' + (activeTab === 'notifications' ? '' : 'display:none;') + '">'
               + (notif_html || empty_state('No notifications')) + '</div>';

    elPanes.innerHTML = panes_html;

    // Attach close-todo handlers
    elPanes.querySelectorAll('button[data-todo]').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        close_todo(btn.dataset.todo, btn);
      });
    });

    // Fetch transitions for workflow action rows (lazy, one xcall each)
    wa_list.forEach(function (wa) {
      render_transition_buttons(wa, elPanes);
    });

    elLoading.style.display = 'none';
    elError.style.display   = 'none';
    elBody.style.display    = '';
  }

  // ---------------------------------------------------------------------------
  // Load — single API call
  // ---------------------------------------------------------------------------
  function load() {
    elLoading.style.display = '';
    elError.style.display   = 'none';
    elBody.style.display    = 'none';
    frappe.call({
      method: 'apex_habitat.apex_core.worklist.my_work_center.get_my_work',
      callback: function (r) {
        if (r && r.message) {
          render(r.message);
        } else {
          show_error();
        }
      },
      error: function () { show_error(); },
    });
  }

  function show_error() {
    elLoading.style.display = 'none';
    elError.style.display   = '';
    elBody.style.display    = 'none';
  }

  retryBtn.addEventListener('click', function (e) {
    e.preventDefault();
    load();
  });

  // Initial load
  load();
})();
"""

# ---------------------------------------------------------------------------
# Seeder
# ---------------------------------------------------------------------------

def seed_my_work_center_block():
    """Create or update 'Apex My Work Center' Custom HTML Block.

    Uses a short hash stored in ``description`` to detect source changes.
    On every migrate: if the hash differs, html+script are updated so browser
    always reflects the source file. Source code is the single source of truth.
    """
    try:
        if not frappe.db.exists("DocType", "Custom HTML Block"):
            frappe.logger().warning(
                "my_work_center_block_seed: 'Custom HTML Block' DocType not found — skipping."
            )
            return

        current_hash = _src_hash()

        if frappe.db.exists("Custom HTML Block", BLOCK_NAME):
            doc = frappe.get_doc("Custom HTML Block", BLOCK_NAME)
            if _stored_hash(doc.html) == current_hash:
                return  # source unchanged — nothing to do
            doc.html = _tagged_html(_HTML, current_hash)
            doc.script = _SCRIPT
            doc.save(ignore_permissions=True)
            frappe.db.commit()
            frappe.logger().info(f"my_work_center_block_seed: updated '{BLOCK_NAME}' (hash {current_hash}).")
            return

        doc = frappe.get_doc({
            "doctype": "Custom HTML Block",
            "name": BLOCK_NAME,
            "html": _tagged_html(_HTML, current_hash),
            "script": _SCRIPT,
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        frappe.logger().info(f"my_work_center_block_seed: created '{BLOCK_NAME}'.")
    except Exception:
        frappe.log_error(
            title="seed_my_work_center_block failed",
            message=frappe.get_traceback(),
        )
