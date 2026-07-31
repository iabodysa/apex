// Copyright (c) 2026, AFMCO and contributors
// The one foreground-poll lifecycle for every portal: paused while the tab is
// hidden, refetch immediately on refocus, never two fetches in flight at once.
//
// Two different portals need it for two different reasons, which is why it lives
// here rather than in either of them. The guest worker portal has no Desk session
// (its identity is the URL token) so it cannot join Frappe's permission-gated
// Socket.IO rooms and polling is its ONLY channel; the route supervisor console
// does have realtime and treats the poll as the fallback the shared realtime
// factory's swallow-everything contract requires — if the socket never connects,
// the screen must still refresh.
//
// The hidden-tab pause is what a hand-rolled `setInterval` with an inline
// `!document.hidden` check inside the callback does NOT buy: that shape keeps the
// timer running in a backgrounded tab and, worse, shows a stale snapshot for up to
// a full interval after the operator comes back.
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
      // Visible again: refetch now so the operator sees current data immediately,
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
