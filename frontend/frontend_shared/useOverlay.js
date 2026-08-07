// Copyright (c) 2026, afmcoltd
import { onScopeDispose, watch } from "vue";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]),' +
  ' textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function tabbable(root) {
  if (!root) return [];
  return Array.from(root.querySelectorAll(FOCUSABLE)).filter(
    (el) => el.offsetParent !== null || el.getClientRects().length > 0,
  );
}

function unref(v) {
  return typeof v === "function" ? v() : v && typeof v === "object" && "value" in v ? v.value : v;
}

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
        Promise.resolve().then(focusFirst);
        return;
      }
      unbind();
      if (returnFocusTo && returnFocusTo.isConnected && returnFocusTo.focus) {
        returnFocusTo.focus();
      }
      returnFocusTo = null;
    },
    { flush: "post" },
  );

  onScopeDispose(unbind);
}
