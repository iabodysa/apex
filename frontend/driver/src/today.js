// Copyright (c) 2026, AFMCO and contributors
import { computed } from "vue";
import { createResource } from "frappe-ui";

let resource = null;

export function useToday() {
  if (!resource) {
    resource = createResource({
      url: "apex.salis.api.driver_portal.get_my_today",
      auto: true,
    });
  }
  return resource;
}

export function todayData() {
  return computed(() => useToday().data || {});
}

export function shiftStep(today) {
  const attendance = today.attendance || {};
  if (attendance.checked_out) return "done";
  if (attendance.checked_in) return "working";
  return "notCheckedIn";
}

export function nextStep(today) {
  const step = shiftStep(today);
  if (step === "done") return { key: "done", to: null };
  if (step === "notCheckedIn") return { key: "checkIn", to: "/attendance" };
  const trip = today.next_trip;
  if (trip) {
    return {
      key: trip.started ? "resumeTrip" : "openTrip",
      to: "/route/" + encodeURIComponent(trip.name),
    };
  }
  return { key: "checkOut", to: "/attendance" };
}
