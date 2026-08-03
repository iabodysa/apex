// Copyright (c) 2026, AFMCO and contributors
// Pull-to-refresh: a pull is armed only when the element the finger is on is already
// scrolled to its top, and only for a downward drag. onRefresh may return a Promise; the
// indicator stays "refreshing" until it settles (a rejection must still spring back, not
// hang).
//
// The top is read from the ELEMENT that actually scrolls, never from window.scrollY. The
// portal frame is one viewport tall and its column owns the overflow, so the document
// never scrolls at all: window.scrollY is permanently 0, every touch armed a pull, and the
// preventDefault below then blocked the column's own scrolling on every downward drag.
import { onMounted, onUnmounted, ref } from "vue";

// Past ~70px of pull, releasing triggers a refresh.
const THRESHOLD = 70;
// Hard cap on how far the indicator travels (keeps it from running away).
const MAX_PULL = 110;
// Drag resistance: the finger moves further than the indicator (a rubber-band
// feel) so a long over-pull is dampened.
const RESISTANCE = 0.5;

export function usePullToRefresh(onRefresh) {
  // How far the indicator is currently pulled down, in px (already resisted).
  const distance = ref(0);
  // True while onRefresh() is in flight — drives the continuous spin.
  const refreshing = ref(false);
  // True while a pull gesture is actively being tracked.
  const armed = ref(false);

  let startY = 0;
  // Whether THIS touch sequence began at the top with a downward intent. Only
  // such a sequence may grow `distance`; a normal scroll is ignored.
  let pulling = false;
  // The element the gesture would scroll, resolved once per sequence.
  let scroller = null;

  function scrollerFor(target) {
    let node = target instanceof Element ? target : null;
    while (node) {
      const overflow = getComputedStyle(node).overflowY;
      if (
        (overflow === "auto" || overflow === "scroll") &&
        node.scrollHeight > node.clientHeight
      ) {
        return node;
      }
      node = node.parentElement;
    }
    return null;
  }

  function scrollTop() {
    return scroller ? scroller.scrollTop : window.scrollY;
  }

  function onTouchStart(e) {
    // Never start a new pull while a refresh is still resolving, and only when
    // the scrolling element is at its very top.
    scroller = scrollerFor(e.target);
    if (refreshing.value || scrollTop() > 0 || e.touches.length !== 1) {
      pulling = false;
      return;
    }
    startY = e.touches[0].clientY;
    pulling = true;
  }

  function onTouchMove(e) {
    if (!pulling || refreshing.value) return;

    const delta = e.touches[0].clientY - startY;

    // Only a DOWNWARD drag is a pull. If the user scrolls up (or the column has
    // scrolled away from the top mid-gesture), abandon this pull.
    if (delta <= 0 || scrollTop() > 0) {
      armed.value = false;
      distance.value = 0;
      pulling = false;
      return;
    }

    // We are pulling the page past its top edge: take over the gesture so the
    // browser does not also bounce/scroll. (Listener is registered
    // non-passive precisely so this preventDefault is honored.)
    if (e.cancelable) e.preventDefault();

    armed.value = true;
    distance.value = Math.min(delta * RESISTANCE, MAX_PULL);
  }

  function onTouchEnd() {
    if (!pulling) return;
    pulling = false;

    if (!armed.value) {
      distance.value = 0;
      return;
    }
    armed.value = false;

    // Released past the threshold → refresh. Park the indicator at the
    // threshold mark while the spinner spins, then spring back when done.
    if (distance.value >= THRESHOLD) {
      refreshing.value = true;
      distance.value = THRESHOLD;
      Promise.resolve()
        .then(() => onRefresh && onRefresh())
        // A failed refresh must still release the indicator, not hang it.
        .catch(() => {})
        .finally(() => {
          refreshing.value = false;
          distance.value = 0;
        });
    } else {
      // Not far enough — just spring back.
      distance.value = 0;
    }
  }

  onMounted(() => {
    // touchstart/touchend stay passive (they never call preventDefault);
    // touchmove is non-passive so it can preventDefault the native bounce
    // while actively pulling.
    document.addEventListener("touchstart", onTouchStart, { passive: true });
    document.addEventListener("touchmove", onTouchMove, { passive: false });
    document.addEventListener("touchend", onTouchEnd, { passive: true });
    document.addEventListener("touchcancel", onTouchEnd, { passive: true });
  });

  onUnmounted(() => {
    document.removeEventListener("touchstart", onTouchStart);
    document.removeEventListener("touchmove", onTouchMove);
    document.removeEventListener("touchend", onTouchEnd);
    document.removeEventListener("touchcancel", onTouchEnd);
  });

  return { distance, refreshing, armed, THRESHOLD };
}
