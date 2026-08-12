export const LEGACY_APEX_WORKER_PATHS = Object.freeze([
  "/driver-sw.js",
  "/masar-sw.js",
]);

function scriptPath(registration) {
  const worker = registration.active || registration.waiting || registration.installing;
  if (!worker?.scriptURL) return null;
  try {
    return new URL(worker.scriptURL).pathname;
  } catch (error) {
    return null;
  }
}

function scopePath(registration) {
  if (!registration.scope) return null;
  try {
    return new URL(registration.scope).pathname;
  } catch (error) {
    return null;
  }
}

export async function reconcileServiceWorker(serviceWorker, { script, scope }) {
  if (!scope.endsWith("/")) throw new Error("service worker requires a canonical trailing-slash scope");
  const registrations = await serviceWorker.getRegistrations();
  await Promise.all(registrations.map(async (registration) => {
    const legacyScope = ["/masar", "/driver"].includes(scopePath(registration));
    if (LEGACY_APEX_WORKER_PATHS.includes(scriptPath(registration)) || legacyScope) {
      await registration.unregister();
    }
  }));
  return serviceWorker.register(script, { scope });
}
