import { computed, ref } from "vue";

const CONFIG_METHOD = "apex.salis.api.portal_notifications.get_config";
const SAVE_METHOD = "apex.salis.api.portal_notifications.save_subscription";
const DELETE_METHOD = "apex.salis.api.portal_notifications.delete_subscription";

function base64UrlBytes(value, atob) {
  const padded = `${value}${"=".repeat((4 - (value.length % 4)) % 4)}`
    .replace(/-/g, "+")
    .replace(/_/g, "/");
  return Uint8Array.from(atob(padded), (character) => character.charCodeAt(0));
}

function subscriptionKeys(subscription) {
  const json = subscription.toJSON?.() || {};
  return json.keys || {};
}

export function createPortalPushController({
  entry,
  registration = null,
  call,
  environment = globalThis,
} = {}) {
  const supported = ref(false);
  const subscribed = ref(false);
  const busy = ref(false);
  const error = ref("");
  const canOffer = computed(() => supported.value && !subscribed.value && !busy.value);
  let currentRegistration = registration;
  let publicKey = "";

  function canUsePush() {
    return Boolean(
      currentRegistration?.pushManager
      && environment.Notification
      && environment.PushManager,
    );
  }

  async function save(subscription) {
    const keys = subscriptionKeys(subscription);
    if (!subscription.endpoint || !keys.p256dh || !keys.auth) {
      throw new Error("بيانات اشتراك التنبيهات غير مكتملة.");
    }
    await call(SAVE_METHOD, {
      entry,
      endpoint: subscription.endpoint,
      p256dh: keys.p256dh,
      auth: keys.auth,
      user_agent: environment.navigator?.userAgent || "",
    });
  }

  async function initialize(nextRegistration = currentRegistration) {
    currentRegistration = nextRegistration;
    error.value = "";
    supported.value = canUsePush();
    if (!supported.value) return false;

    const config = await call(CONFIG_METHOD, { entry });
    publicKey = config?.enabled ? (config.vapid_public_key || "") : "";
    supported.value = Boolean(publicKey);
    if (!supported.value) return false;

    const existing = await currentRegistration.pushManager.getSubscription();
    if (existing) {
      await save(existing);
      subscribed.value = true;
    } else if (environment.Notification.permission === "denied") {
      supported.value = false;
      error.value = "التنبيهات محظورة من إعدادات الجهاز.";
    }
    return supported.value;
  }

  async function enable() {
    if (!supported.value || busy.value) return false;
    busy.value = true;
    error.value = "";
    try {
      let permission = environment.Notification.permission;
      if (permission === "default") {
        permission = await environment.Notification.requestPermission();
      }
      if (permission !== "granted") {
        supported.value = false;
        error.value = "لم تُفعّل التنبيهات. يمكنك السماح بها من إعدادات الجهاز.";
        return false;
      }
      const existing = await currentRegistration.pushManager.getSubscription();
      const subscription = existing || await currentRegistration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: base64UrlBytes(publicKey, environment.atob),
      });
      await save(subscription);
      subscribed.value = true;
      return true;
    } catch (reason) {
      error.value = reason?.message || "تعذّر تفعيل التنبيهات.";
      return false;
    } finally {
      busy.value = false;
    }
  }

  async function disable() {
    const subscription = await currentRegistration?.pushManager?.getSubscription();
    if (subscription) {
      await call(DELETE_METHOD, { entry, endpoint: subscription.endpoint });
      await subscription.unsubscribe();
    }
    subscribed.value = false;
    return true;
  }

  return Object.freeze({ supported, subscribed, busy, error, canOffer, initialize, enable, disable });
}
