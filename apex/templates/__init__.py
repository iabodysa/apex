# Copyright (c) 2026, AFMCO and contributors
"""Jinja template package — AUDIT RECORD (A-105 clause 7.13).

The clause asks that this directory be "formally audited to ensure Jinja-injected
components are cleanly integrated". Coverage existed by sink — a bootstrap test
reaches the one partial through its context key — but no audit was ever written
down, so the clause stayed unproven. This is that record.

Re-derive the whole thing with two commands:
``find apex/templates -type f`` and ``grep -rn portal_accent apex/``.

INVENTORY — three files, exactly one of which is a template:

  ``__init__.py``                  this record; an empty package marker otherwise.
  ``pages/__init__.py``            empty package marker, ships NO template. Every
                                   served route is a ``www/`` file-convention page,
                                   so nothing in the app resolves through
                                   ``templates/pages`` at all.
  ``includes/portal_accent.html``  the only Jinja partial in the app.

WHAT INCLUDES IT — four shells, and exactly the four that supply its variable:

  ``www/driver.html:17``   ``www/housing.html:17``
  ``www/masar.html:24``    ``www/safety.html:17``

  Each is ``{%- include "apex/templates/includes/portal_accent.html" %}`` in the
  document ``<head>``. Placement differs by page authorization, deliberately:
  housing and safety are role-gated portals and include it INSIDE their
  ``{%- if has_*_role %}`` head branch, so the no-role branch emits no style;
  driver and masar have no role gate at all (any authenticated worker reaches
  them, guests are bounced by ``guest_redirect``), so there is no branch for the
  include to sit in and it is unconditional. Both shapes are correct for their
  page; neither leaks a style to a viewer who cannot see the portal.

THE INTEGRATION INVARIANT — producer and consumer match one-for-one:

  ``apex_core/utils/portal_bootstrap.apply_portal_appearance`` is the only writer
  of ``context.portal_accent``. Its callers are ``www/driver.py:60``,
  ``www/housing.py:62``, ``www/masar.py:64`` and ``www/safety.py:54`` — the same
  four pages, no more and no fewer. No shell includes the partial without its
  controller supplying the value, and no controller projects the value into a
  shell that never renders it. That bidirectional match is the audit's core claim.

NO LAYOUT LEAKS ACROSS ARCHETYPES — the eight ``www`` shells split three ways:

  themed portals (4)    driver, housing, masar, safety — carry
                        ``<html ... data-theme="{{ portal_theme or 'afmco' }}">``,
                        call ``apply_portal_appearance``, include the partial.
  fixed palette (3)     fleet, fleet-os, masar-supervisor — no ``data-theme``
                        attribute at all, import only ``guest_redirect``, and
                        correctly do NOT include the partial. The partial's sole
                        selector is ``html[data-theme]``, so an include here would
                        be dead CSS even before its ``{%- if portal_accent %}``
                        guard suppressed the output entirely.
  redirect marker (1)   housing-count — not a portal shell: no SPA mount, no
                        bundle. ``get_context`` raises ``frappe.Redirect`` before
                        the template is ever sourced.

  The partial carries NO layout: no box model, no typography, no positioning. It
  emits two custom properties (``--c-accent``, ``--c-primary``) scoped to
  ``html[data-theme]``. There is nothing that structurally COULD leak between
  archetypes, and the one thing it does emit is keyed to an attribute the other
  two archetypes never set.

VERDICT — CLEANLY INTEGRATED. One partial, one producer, four consumers, an exact
producer/consumer match, an attribute-scoped effect, and guarded empty output when
unconfigured. No orphan template, no shell including a partial it cannot feed, no
cross-archetype bleed, no dead directory except the two package markers.

The one genuine risk here is interpolation, not layout: the ``www`` renderer runs
with autoescape OFF, so ``{{ portal_accent }}`` lands inside a ``<style>`` block
unescaped. That is handled at the source rather than the sink —
``driver_portal_theme.py:58-59`` rejects any ``accent_color`` that fails
``_CSS_COLOR_RE`` on save — which is the correct guard, because CSS does not
decode HTML entities and escaping at render would not help.

STANDING GUARDS — this record is checked, not merely asserted:
``apex_core/utils/test_portal_bootstrap.py:26`` pins the four appearance keys with
``portal_accent`` among them, and ``www/test_www_controller_has_template.py``
fails any ``www`` controller that has no template beside it.
"""
