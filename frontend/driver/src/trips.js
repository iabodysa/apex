// Copyright (c) 2026, AFMCO and contributors
import { TRIP, TRIP_LOG } from "@shared/statusVocabularies";

// `trip_log_status` is the DRIVER's own record (Trip Start Log) and `status` is the
// vehicle's journey (Dispatch Trip). They are separate vocabularies that happen to
// share the words Completed and Cancelled, so each side is named here rather than
// compared to a bare string that reads the same for both.
export function tripTone(trip) {
  if (!trip) return "planned";
  if (trip.trip_log_status === TRIP_LOG.COMPLETED || trip.status === TRIP.COMPLETED) return "done";
  if (trip.status === TRIP.CANCELLED || trip.trip_log_status === TRIP_LOG.CANCELLED) {
    return "cancelled";
  }
  if (trip.started) return "running";
  return "planned";
}

export function tripStateLabel(trip, t, te) {
  const tone = tripTone(trip);
  if (tone === "done") return t("trips.completed");
  if (tone === "running") return t("trips.started");
  return te("tripStatus", trip.status);
}

export function isActionable(trip) {
  const tone = tripTone(trip);
  return tone === "planned" || tone === "running";
}

export function dockStep(rows, selected, live) {
  if (!live) return { key: "readOnly", trip: null };
  if (!rows.length) return { key: "none", trip: null };
  const focus =
    selected && isActionable(selected) ? selected : rows.find(isActionable) || null;
  if (!focus) return { key: "done", trip: null };
  if (tripTone(focus) === "planned") return { key: "start", trip: focus };
  const expected = focus.expected_count || 0;
  if (expected && (focus.boarded_count || 0) < expected) return { key: "board", trip: focus };
  return { key: "complete", trip: focus };
}

export const STEP_ICONS = {
  start: "route",
  board: "user",
  complete: "badge",
  done: "badge",
  none: "calendar",
  readOnly: "layers",
};
