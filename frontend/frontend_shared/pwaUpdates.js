// Copyright (c) 2026, AFMCO and contributors
// [#shared-pwa-updates]
// createPwaUpdates() builds the PWA new-build detection shared by the mobile
// SPAs (driver, worker/Masar). Both hand-rolled the same waiting-worker wiring —
// the SW (registered by the portal's www/<portal>.html at root scope) installs a
// new build as a WAITING worker (no auto-skipWaiting); we flip `updateReady` so
// the shell shows a reload banner, and `applyUpdate()` tells the waiting worker
// to take over and reloads. This factory holds that once; a portal supplies
// nothing (the behaviour is identical) and re-exports the returned handles so its
// App.vue keeps the same `updateReady` / `initPwaUpdates` / `applyUpdate` imports.
import { ref } from "vue";

// Re-check for a new build hourly and whenever the tab refocuses, so a deploy is
// surfaced without waiting for a manual reload.
const UPDATE_POLL_MS = 60 * 60 * 1000;

// createPwaUpdates() -> { updateReady, initPwaUpdates, applyUpdate }
//   updateReady    — reactive ref; true once a new build is waiting (banner gate)
//   initPwaUpdates — start detection; returns a teardown fn (call in onUnmounted)
//   applyUpdate    — arm the reload + tell the waiting worker to SKIP_WAITING
// Each call builds its own isolated module-scope state (one instance per portal).
export function createPwaUpdates() {
  const updateReady = ref(false);

  let waitingWorker = null;
  let reloading = false;
  // Reload on controllerchange ONLY after applyUpdate() armed it. A fresh SW
  // claiming a previously-uncontrolled page also fires controllerchange (first
  // load) — reloading then would be a spurious refresh. (This safer guard is the
  // one the worker/Masar portal already carried; the driver portal previously
  // reloaded on ANY controllerchange, a latent first-load-refresh bug now fixed.)
  let updateRequested = false;

  function trackInstalling(reg, worker) {
    if (!worker) return;
    worker.addEventListener("statechange", () => {
      // A worker reaching "installed" while one already controls the page means a
      // NEW build is ready (the first-ever install has no controller — not an
      // update). reg.waiting is the worker to activate on reload.
      if (worker.state === "installed" && navigator.serviceWorker.controller) {
        waitingWorker = reg.waiting || worker;
        updateReady.value = true;
      }
    });
  }

  // Returns a teardown fn that clears the interval and removes every listener it
  // added, so a caller can stop it in onUnmounted — this prevents a duplicate
  // poll/listener set from stacking on HMR re-init (the App root re-running setup).
  function initPwaUpdates() {
    if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) {
      return () => {};
    }

    let pollTimer = null;
    let onFocus = null;
    let onVisibility = null;

    navigator.serviceWorker.ready
      .then((reg) => {
        // A worker may already be waiting (installed before this tab loaded).
        if (reg.waiting && navigator.serviceWorker.controller) {
          waitingWorker = reg.waiting;
          updateReady.value = true;
        }
        reg.addEventListener("updatefound", () => trackInstalling(reg, reg.installing));

        const poll = () => reg.update().catch(() => {});
        pollTimer = setInterval(poll, UPDATE_POLL_MS);
        onFocus = poll;
        onVisibility = () => {
          if (document.visibilityState === "visible") poll();
        };
        window.addEventListener("focus", onFocus);
        document.addEventListener("visibilitychange", onVisibility);
      })
      .catch(() => {});

    // When the new worker takes control AFTER applyUpdate() armed the reload,
    // reload once so the page is served by the new build. Ignore the first-load
    // claim (updateRequested still false) to avoid a spurious refresh.
    const onControllerChange = () => {
      if (!updateRequested || reloading) return;
      reloading = true;
      window.location.reload();
    };
    navigator.serviceWorker.addEventListener("controllerchange", onControllerChange);

    return () => {
      if (pollTimer) clearInterval(pollTimer);
      if (onFocus) window.removeEventListener("focus", onFocus);
      if (onVisibility) document.removeEventListener("visibilitychange", onVisibility);
      navigator.serviceWorker.removeEventListener("controllerchange", onControllerChange);
    };
  }

  function applyUpdate() {
    updateRequested = true;
    if (!waitingWorker) {
      // No tracked waiting worker (e.g. it activated already) — a reload still
      // lands the latest build under the network-first shell.
      window.location.reload();
      return;
    }
    waitingWorker.postMessage({ type: "SKIP_WAITING" });
  }

  return { updateReady, initPwaUpdates, applyUpdate };
}
