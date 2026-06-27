// Guest worker portal has no Desk session (identity is the URL token), so it
// cannot join Frappe's permission-gated Socket.IO rooms; substitute a cheap
// visible-only foreground poll (paused while hidden, refetch-on-show, no overlap).
import { onMounted, onUnmounted } from "vue";

// ~45s: live-ish for "driver arrived"/upcoming-trip changes without hammering
// the token-scoped read endpoints.
const DEFAULT_INTERVAL = 45000;

// refetch: a function that triggers the refetch(es) and returns a Promise (or
// anything Promise.resolve can wrap) so we can detect in-flight overlap.
export function usePoll(refetch, interval = DEFAULT_INTERVAL) {
  let timer = null;
  // True while a poll-driven refetch is unresolved — prevents overlapping ticks.
  let inFlight = false;

  function tick() {
    // Never poll a hidden tab, and never stack a second fetch on an unsettled one.
    if (document.hidden || inFlight) return;
    inFlight = true;
    Promise.resolve()
      .then(() => refetch && refetch())
      // A failed refetch must not wedge the poll; the next tick retries.
      .catch(() => {})
      .finally(() => {
        inFlight = false;
      });
  }

  function start() {
    if (timer) return;
    timer = setInterval(tick, interval);
  }

  function stop() {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
  }

  function onVisibility() {
    if (document.hidden) {
      // Hidden: stop the timer so a backgrounded tab is fully silent.
      stop();
    } else {
      // Visible again: refetch now so the worker sees current data immediately,
      // then resume the interval.
      tick();
      start();
    }
  }

  onMounted(() => {
    document.addEventListener("visibilitychange", onVisibility);
    // Arm only if the tab is currently visible (the common first-load case).
    if (!document.hidden) start();
  });

  onUnmounted(() => {
    document.removeEventListener("visibilitychange", onVisibility);
    stop();
  });

  return { stop, start };
}
