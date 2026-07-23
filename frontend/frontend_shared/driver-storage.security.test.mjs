// Copyright (c) 2026, AFMCO and contributors
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

import { purgeDriverPayloadStorage } from "./driverStorage.js";

const ROOT = path.resolve(import.meta.dirname, "../..");
const DRIVER = path.join(ROOT, "frontend/driver/src");

class MemoryStorage {
  constructor(entries = {}) {
    this.entries = new Map(Object.entries(entries));
  }
  get length() { return this.entries.size; }
  key(index) { return [...this.entries.keys()][index] ?? null; }
  getItem(key) { return this.entries.get(key) ?? null; }
  setItem(key, value) { this.entries.set(key, String(value)); }
  removeItem(key) { this.entries.delete(key); }
}

test("driver boot purges every legacy credential payload before a token switch failure", () => {
  const driverA = JSON.stringify({
    attendance: "Driver A checked in",
    trips: ["Driver A trip"],
    routes: [{ worker_name: "Worker A", phone: "+966500000001" }],
  });
  const storage = new MemoryStorage({
    "salis_portal_cache:today": driverA,
    "salis_portal_cache:route": driverA,
    "salis_portal_cache:trip:TRIP-A": driverA,
    fleet_portal_lang: "en",
  });

  purgeDriverPayloadStorage(storage);

  // Driver B's credential is now active and its API request fails. With no
  // persistent or in-memory data fallback, no Driver A payload can render.
  const renderedAfterDriverBFailure = [...storage.entries.values()].join(" ");
  assert.equal(
    [...storage.entries.keys()].filter((key) => key.startsWith("salis_portal_cache:")).length,
    0,
  );
  for (const secret of ["Driver A", "Worker A", "+966500000001"]) {
    assert.doesNotMatch(renderedAfterDriverBFailure, new RegExp(secret.replace("+", "\\+")));
  }
  assert.equal(storage.getItem("fleet_portal_lang"), "en");
});

test("driver pages have no credential payload cache or stale API fallback", () => {
  const cache = fs.readFileSync(path.join(DRIVER, "cache.js"), "utf8");
  const home = fs.readFileSync(path.join(DRIVER, "pages/Home.vue"), "utf8");
  const route = fs.readFileSync(path.join(DRIVER, "pages/Route.vue"), "utf8");
  assert.match(cache, /purgeDriverPayloadStorage/);
  for (const source of [cache, home, route]) {
    assert.doesNotMatch(source, /cache(?:Get|Set)|staleToday|staleRoute|staleTrip/);
  }
});

test("clearance print key is requested only by an explicit POST click", () => {
  const profile = fs.readFileSync(path.join(DRIVER, "pages/Profile.vue"), "utf8");
  assert.match(profile, /get_my_clearance_certificate/);
  assert.match(profile, /method:\s*"POST"/);
  assert.match(profile, /@click="downloadClearanceCertificate"/);
  assert.doesNotMatch(profile, /:href="clearanceRow\.certificate_url"/);
});

test("driver updates opt into automatic activation without a reload banner action", () => {
  const updates = fs.readFileSync(path.join(DRIVER, "pwa-updates.js"), "utf8");
  assert.match(updates, /autoActivate:\s*true/);
});
