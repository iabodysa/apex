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
