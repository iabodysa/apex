// Copyright (c) 2026, AFMCO and contributors
//
// useOverlay(options) — the one modal-overlay keyboard contract for every portal.
//
// An overlay that only PAINTS over the page still leaves the whole page reachable:
// Tab walks straight out of the dialog onto controls the user cannot see or click,
// because a scrim intercepts the pointer but not the tab order. Each overlay in the
// tree had answered that on its own (i.e. not at all), so this composable owns the
// three rules once and every overlay opts in:
//
//   1. opening moves focus INTO the overlay;
//   2. Tab / Shift+Tab cycle inside it and never reach the page behind;
//   3. Escape closes it and focus returns to whatever opened it.
//
// The listener is registered in the CAPTURE phase on `document` so it wins before a
// child's own key handling, and it is bound only while the overlay is active — a
// drawer that is a plain sidebar at desktop width must not trap anything.
import { onScopeDispose, watch } from "vue";

// Tabbable candidates. `:not([tabindex="-1"])` drops programmatically-focusable
// nodes; `details > summary` and contenteditable are omitted deliberately — no
// portal overlay uses them, and a shorter selector is a cheaper query per Tab.
const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]),' +
  ' textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function tabbable(root) {
  if (!root) return [];
  return Array.from(root.querySelectorAll(FOCUSABLE)).filter(
    // offsetParent is null for display:none subtrees; a fixed-position element has
    // none either, hence the client-rect fallback.
    (el) => el.offsetParent !== null || el.getClientRects().length > 0,
  );
}

function unref(v) {
  return typeof v === "function" ? v() : v && typeof v === "object" && "value" in v ? v.value : v;
}

// options:
//   active    — ref/getter: true while the overlay is modal (required)
//   container — ref/getter resolving to the overlay's root element (required)
//   close     — called on Escape (required)
export function useOverlay({ active, container, close }) {
  let returnFocusTo = null;
  let bound = false;

  const root = () => unref(container);

  function focusFirst() {
    const el = root();
    if (!el) return;
    const items = tabbable(el);
    if (items.length) {
      items[0].focus();
      return;
    }
    // An overlay with nothing tabbable still must not leave focus outside it.
    if (!el.hasAttribute("tabindex")) el.setAttribute("tabindex", "-1");
    el.focus();
  }

  function onKeydown(e) {
    if (e.key === "Escape") {
      e.preventDefault();
      close();
      return;
    }
    if (e.key !== "Tab") return;
    const el = root();
    if (!el) return;
    const items = tabbable(el);
    if (!items.length) {
      // Nothing to cycle through: hold focus on the overlay itself.
      e.preventDefault();
      el.focus();
      return;
    }
    const first = items[0];
    const last = items[items.length - 1];
    const current = document.activeElement;
    const inside = el.contains(current);
    if (e.shiftKey && (current === first || !inside)) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && (current === last || !inside)) {
      e.preventDefault();
      first.focus();
    }
  }

  function bind() {
    if (bound || typeof document === "undefined") return;
    document.addEventListener("keydown", onKeydown, true);
    bound = true;
  }

  function unbind() {
    if (!bound) return;
    document.removeEventListener("keydown", onKeydown, true);
    bound = false;
  }

  watch(
    () => !!unref(active),
    (on) => {
      if (on) {
        returnFocusTo = typeof document !== "undefined" ? document.activeElement : null;
        bind();
        // The container is rendered by the same state change that opened the
        // overlay, so wait for the DOM before reaching for it.
        Promise.resolve().then(focusFirst);
        return;
      }
      unbind();
      // Only restore to a node still in the document: the trigger may itself have
      // been removed by whatever the overlay did.
      if (returnFocusTo && returnFocusTo.isConnected && returnFocusTo.focus) {
        returnFocusTo.focus();
      }
      returnFocusTo = null;
    },
    { flush: "post" },
  );

  onScopeDispose(unbind);
}
