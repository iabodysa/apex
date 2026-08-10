// Copyright (c) 2026, afmcoltd
import { ENTRY, grantedSections, hasSection } from "./portal.js";

export const SECTIONS = [
  { id: "beds", domain: "residents", path: "/beds", icon: "bed", labelKey: "nav.beds" },
  {
    id: "arrivals",
    domain: "residents",
    path: "/arrivals",
    icon: "user",
    labelKey: "nav.arrivals",
  },
  {
    id: "transfer",
    domain: "residents",
    path: "/transfer",
    icon: "route",
    labelKey: "nav.transfer",
  },
  { id: "custody", domain: "custody", path: "/custody", icon: "box", labelKey: "nav.custody" },
  {
    id: "count",
    domain: "count",
    path: "/count",
    icon: "clipboard-check",
    labelKey: "nav.count",
  },
  {
    id: "delivery",
    domain: "delivery",
    path: "/delivery",
    icon: "truck",
    labelKey: "nav.delivery",
  },
  {
    id: "safety",
    domain: "safety",
    path: "/safety",
    icon: "shield-check",
    labelKey: "nav.safety",
  },
];

export const DOMAINS = [
  {
    id: "today",
    path: "/today",
    icon: "calendar",
    labelKey: "nav.today",
    sectionIds: ["beds", "arrivals", "transfer", "custody", "count", "safety"],
  },
  {
    id: "residents",
    path: "/beds",
    icon: "user",
    labelKey: "nav.residents",
    sectionIds: ["beds", "arrivals", "transfer"],
  },
  {
    id: "custody",
    path: "/custody",
    icon: "box",
    labelKey: "nav.custody",
    sectionIds: ["custody"],
  },
  {
    id: "count",
    path: "/count",
    icon: "clipboard-check",
    labelKey: "nav.count",
    sectionIds: ["count"],
  },
  {
    id: "delivery",
    path: "/delivery",
    icon: "truck",
    labelKey: "nav.delivery",
    sectionIds: ["delivery"],
  },
  {
    id: "safety",
    path: "/safety",
    icon: "shield-check",
    labelKey: "nav.safety",
    sectionIds: ["safety"],
  },
];

function asSet(granted) {
  return granted instanceof Set ? granted : new Set(granted || []);
}

export function domainForSection(sectionId) {
  const section = SECTIONS.find((entry) => entry.id === sectionId);
  return section ? section.domain : sectionId === "today" ? "today" : "";
}

export function sectionsForDomain(domainId, granted = grantedSections()) {
  const allowed = asSet(granted);
  return SECTIONS.filter((section) => section.domain === domainId && allowed.has(section.id));
}

export function visibleDomains(granted = grantedSections()) {
  const allowed = asSet(granted);
  return DOMAINS.filter((domain) => domain.sectionIds.some((id) => allowed.has(id))).map((domain) => {
    if (domain.sectionIds.length === 1) return domain;
    if (domain.id === "today") return domain;
    const first = sectionsForDomain(domain.id, allowed)[0];
    return first ? { ...domain, path: first.path } : domain;
  });
}

export function chooseLanding(entry = ENTRY, granted = grantedSections()) {
  const allowed = asSet(granted);
  if (entry === "safety" && allowed.has("safety")) return "/safety";
  if (["beds", "arrivals", "transfer", "custody", "count", "safety"].some((id) => allowed.has(id))) {
    return "/today";
  }
  const first = SECTIONS.find((section) => allowed.has(section.id));
  return first ? first.path : "/no-access";
}

export function allowedSections() {
  return SECTIONS.filter((section) => hasSection(section.id));
}

export function allowedDomains() {
  return visibleDomains();
}

export function landingPath() {
  return chooseLanding();
}
