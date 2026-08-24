import { humanLabel } from "../../core/displayLabels.js";
import { __ } from "../../core/i18n.js";

function text(value) {
  return String(value ?? "").trim();
}

function timePart(value) {
  const normalized = text(value).replace("T", " ");
  const time = normalized.includes(" ") ? normalized.split(" ").at(-1) : normalized;
  return /^\d{2}:\d{2}(?::\d{2})?$/.test(time) ? time : undefined;
}

export function meaningfulRequestTitle(request, fallback = __("Transport Request")) {
  const pickup = text(request?.from_location || request?.pickup_point || humanLabel(
    request,
    "accommodation_building",
    "accommodation_building_label",
  ));
  const destination = text(request?.to_location || request?.destination);
  if (pickup && destination) return __("From {0} to {1}", [pickup, destination]);
  if (destination) return __("To {0}", [destination]);
  return text(request?.request_type || request?.service_line || request?.requester_name) || fallback;
}

export function buildTripAssignments(selectedNames, selections, stopKeys) {
  const validStops = new Set(stopKeys || []);
  const names = [...new Set(selectedNames || [])].filter(Boolean);
  if (!names.length) throw new Error(__("Select at least one transport request."));
  return names.map((name) => {
    const selection = selections?.[name] || {};
    const pickupStop = text(selection.pickup_stop);
    const dropoffStop = text(selection.dropoff_stop);
    if (!validStops.has(pickupStop) || !validStops.has(dropoffStop)) {
      throw new Error(__("Select the actual pickup and dropoff stop for request {0}.", [name]));
    }
    if (pickupStop === dropoffStop) {
      throw new Error(__("The pickup stop must differ from the dropoff stop for request {0}.", [name]));
    }
    return {
      transport_request: name,
      pickup_stop: pickupStop,
      dropoff_stop: dropoffStop,
    };
  });
}

export function buildAdHocRequest(request, form) {
  const requestName = text(request?.name);
  const pickup = text(request?.from_location || request?.pickup_point || humanLabel(
    request,
    "accommodation_building",
    "accommodation_building_label",
  ));
  const destination = text(request?.to_location || request?.destination);
  if (!requestName || !pickup || !destination) {
    throw new Error(__("Complete the origin location and destination in the transport request before creating a custom trip."));
  }
  if (!text(form?.trip_date) || !text(form?.planned_start) || !text(form?.planned_end)) {
    throw new Error(__("Enter the trip date and the start and end times."));
  }
  return {
    trip: {
      project: text(request?.project) || undefined,
      trip_date: text(form.trip_date),
      planned_start: text(form.planned_start),
      planned_end: text(form.planned_end),
      stops: [
        {
          stop_key: "pickup",
          stop_name: pickup,
          accommodation_building: text(request?.accommodation_building) || undefined,
          location: pickup,
          planned_time: timePart(form.planned_start),
        },
        {
          stop_key: "dropoff",
          stop_name: destination,
          location: destination,
          planned_time: timePart(form.planned_end),
        },
      ],
    },
    transport_requests: [
      {
        transport_request: requestName,
        pickup_stop: "pickup",
        dropoff_stop: "dropoff",
      },
    ],
  };
}
