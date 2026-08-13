import { describe, expect, it, vi } from "vitest";
import { createPortalPushController } from "./pushNotifications.js";

function setup() {
  const subscription = {
    endpoint: "https://web.push.apple.com/device",
    toJSON: () => ({ keys: { p256dh: "device-key", auth: "auth-key" } }),
    unsubscribe: vi.fn(async () => true),
  };
  const registration = {
    pushManager: {
      getSubscription: vi.fn(async () => null),
      subscribe: vi.fn(async () => subscription),
    },
  };
  const Notification = {
    permission: "default",
    requestPermission: vi.fn(async () => "granted"),
  };
  const call = vi.fn(async (method) => {
    if (method.endsWith("get_config")) {
      return { enabled: true, vapid_public_key: "AQID" };
    }
    return { subscribed: true };
  });
  const environment = {
    Notification,
    PushManager: function PushManager() {},
    navigator: { userAgent: "Mobile Safari" },
    atob: (value) => Buffer.from(value, "base64").toString("binary"),
  };
  return { subscription, registration, Notification, call, environment };
}

describe("portal background notifications", () => {
  it("subscribes only from a user gesture and saves the device against the portal entry", async () => {
    const fixture = setup();
    const controller = createPortalPushController({
      entry: "worker",
      registration: fixture.registration,
      call: fixture.call,
      environment: fixture.environment,
    });

    await controller.initialize();
    expect(controller.canOffer.value).toBe(true);
    expect(fixture.Notification.requestPermission).not.toHaveBeenCalled();

    expect(await controller.enable()).toBe(true);
    expect(fixture.registration.pushManager.subscribe).toHaveBeenCalledWith({
      userVisibleOnly: true,
      applicationServerKey: new Uint8Array([1, 2, 3]),
    });
    expect(fixture.call).toHaveBeenCalledWith(
      "apex.salis.api.portal_notifications.save_subscription",
      {
        entry: "worker",
        endpoint: fixture.subscription.endpoint,
        p256dh: "device-key",
        auth: "auth-key",
        user_agent: "Mobile Safari",
      },
    );
    expect(controller.subscribed.value).toBe(true);
  });

  it("keeps unsupported browsers silent instead of requesting permission", async () => {
    const fixture = setup();
    delete fixture.environment.PushManager;
    const controller = createPortalPushController({
      entry: "driver",
      registration: fixture.registration,
      call: fixture.call,
      environment: fixture.environment,
    });

    await controller.initialize();

    expect(controller.canOffer.value).toBe(false);
    expect(fixture.call).not.toHaveBeenCalled();
  });
});
