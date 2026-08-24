import { ref } from "vue";

const LEGACY_APEX_WORKER_PATHS = Object.freeze(["/driver-sw.js", "/masar-sw.js"]);

export async function reconcileServiceWorker(serviceWorker, shell) {
  if (!shell?.service_worker_url) return null;
  if (!shell.service_worker_scope?.endsWith("/")) throw new TypeError("Service worker scope must end with a slash");
  const expected = new URL(shell.service_worker_url, globalThis.location.origin).pathname;
  const registrations = await serviceWorker.getRegistrations();
  for (const registration of registrations) {
    const script = registration.active?.scriptURL || registration.waiting?.scriptURL || registration.installing?.scriptURL;
    if (!script) continue;
    const pathname = new URL(script).pathname;
    const wrongScope = registration.scope !== new URL(shell.service_worker_scope, globalThis.location.origin).href;
    if (LEGACY_APEX_WORKER_PATHS.includes(pathname) || (pathname === expected && wrongScope)) {
      await registration.unregister();
    }
  }
  return serviceWorker.register(shell.service_worker_url, { scope: shell.service_worker_scope });
}

export async function registerPortalWorker(shell = globalThis.window?.apex_portal_shell) {
  if (!shell?.service_worker_url || !globalThis.navigator?.serviceWorker) return null;
  return reconcileServiceWorker(globalThis.navigator.serviceWorker, shell);
}

export function createPortalUpdateController({ container = globalThis.navigator?.serviceWorker, reload } = {}) {
  const ready = ref(false);
  const busy = ref(false);
  let waiting = null;
  let requested = false;

  // A worker reaching `installed` while another one is already active is the new version held
  // back; the same state with no active worker is the first install, which nobody is waiting for.
  function offer(worker, registration) {
    if (!worker) return;
    const settle = () => {
      if (worker.state !== "installed" || !registration.active) return;
      waiting = worker;
      ready.value = true;
    };
    worker.addEventListener("statechange", settle);
    settle();
  }

  container?.addEventListener?.("controllerchange", () => {
    if (!requested) return;
    (reload || (() => globalThis.location?.reload()))();
  });

  function attach(registration) {
    if (!registration) return;
    offer(registration.waiting || registration.installing, registration);
    registration.addEventListener?.("updatefound", () => offer(registration.installing, registration));
  }

  function apply() {
    if (!waiting || busy.value) return;
    busy.value = true;
    requested = true;
    waiting.postMessage({ type: "SKIP_WAITING" });
  }

  return { ready, busy, attach, apply };
}
