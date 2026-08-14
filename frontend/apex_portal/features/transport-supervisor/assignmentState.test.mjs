import { describe, expect, it } from "vitest";
import {
  buildAdHocRequest,
  buildTripAssignments,
  meaningfulRequestTitle,
} from "./assignmentState.js";

describe("transport request assignment state", () => {
  it("builds one atomic payload for multiple requests with independent actual stops", () => {
    const assignments = buildTripAssignments(
      ["REQ-A", "REQ-B"],
      {
        "REQ-A": { pickup_stop: "HOME-A", dropoff_stop: "SITE-A" },
        "REQ-B": { pickup_stop: "HOME-B", dropoff_stop: "SITE-B" },
      },
      ["HOME-A", "SITE-A", "HOME-B", "SITE-B"],
    );
    expect(assignments).toEqual([
      { transport_request: "REQ-A", pickup_stop: "HOME-A", dropoff_stop: "SITE-A" },
      { transport_request: "REQ-B", pickup_stop: "HOME-B", dropoff_stop: "SITE-B" },
    ]);
    expect(() => buildTripAssignments(
      ["REQ-A"],
      { "REQ-A": { pickup_stop: "MADE-UP", dropoff_stop: "SITE-A" } },
      ["HOME-A", "SITE-A"],
    )).toThrow("نقطة التوقف");
  });

  it("creates an ad-hoc trip with concrete pickup and destination stops", () => {
    const payload = buildAdHocRequest(
      {
        name: "REQ-9",
        project: "PROJ-1",
        from_location: "سكن الشمال",
        to_location: "مشروع المطار",
        accommodation_building: "BLD-1",
        pickup_datetime: "2026-08-15 06:00:00",
      },
      {
        trip_date: "2026-08-15",
        planned_start: "2026-08-15 06:00:00",
        planned_end: "2026-08-15 07:00:00",
      },
    );

    expect(payload.trip).toMatchObject({
      project: "PROJ-1",
      trip_date: "2026-08-15",
      stops: [
        expect.objectContaining({ stop_key: "pickup", stop_name: "سكن الشمال", planned_time: "06:00:00" }),
        expect.objectContaining({ stop_key: "dropoff", stop_name: "مشروع المطار", planned_time: "07:00:00" }),
      ],
    });
    expect(payload.transport_requests).toEqual([
      { transport_request: "REQ-9", pickup_stop: "pickup", dropoff_stop: "dropoff" },
    ]);
    expect(meaningfulRequestTitle({ from_location: "أ", to_location: "ب" })).toBe("من أ إلى ب");
    expect(meaningfulRequestTitle({
      accommodation_building: "BLD-0001",
      accommodation_building_label: "سكن الشمال",
      to_location: "المطار",
    })).toBe("من سكن الشمال إلى المطار");
  });
});
