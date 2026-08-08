// Copyright (c) 2026, afmcoltd
import { ENTRY, hasSection } from "./portal.js";

export const SECTIONS = [
  { id: "beds", path: "/beds", icon: "bed", labelKey: "nav.beds" },
  { id: "arrivals", path: "/arrivals", icon: "user", labelKey: "nav.arrivals" },
  { id: "custody", path: "/custody", icon: "box", labelKey: "nav.custody" },
  { id: "transfer", path: "/transfer", icon: "route", labelKey: "nav.transfer" },
  { id: "count", path: "/count", icon: "clipboard-check", labelKey: "nav.count" },
  { id: "delivery", path: "/delivery", icon: "truck", labelKey: "nav.delivery" },
  { id: "safety", path: "/safety", icon: "shield-check", labelKey: "nav.safety" },
];

export function allowedSections() {
  return SECTIONS.filter((section) => hasSection(section.id));
}

export function landingPath() {
  const preferred = ENTRY === "safety" ? "safety" : "count";
  if (hasSection(preferred)) return SECTIONS.find((s) => s.id === preferred).path;
  const first = allowedSections()[0];
  return first ? first.path : "/no-access";
}
