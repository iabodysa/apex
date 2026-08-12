async function unwrap(call, method, params) {
  const response = params === undefined ? await call(method) : await call(method, params);
  return response?.message ?? response;
}

export function createDriverGateway(call) {
  return Object.freeze({
    today: () => unwrap(call, "apex.salis.api.driver_portal.personal.get_masar_today"),
    profile: () => unwrap(call, "apex.salis.api.driver_portal.get_driver_profile"),
    accommodation: () => unwrap(call, "apex.salis.api.driver_portal.personal.get_my_accommodation"),
    custody: () => unwrap(call, "apex.salis.api.driver_portal.personal.get_my_custody"),
    requests: () => unwrap(call, "apex.salis.api.driver_portal.personal.get_my_resident_requests"),
    route: () => unwrap(call, "apex.salis.api.driver_portal.my_worker_route_today"),
    trip: (dispatchTrip) => unwrap(call, "apex.salis.api.driver_portal.my_trip_route", { dispatch_trip: dispatchTrip }),
    trips: () => unwrap(call, "apex.salis.api.driver_portal.my_trips_recent"),
    startTrip: (dispatchTrip) => unwrap(call, "apex.salis.api.driver_portal.start_my_trip", { dispatch_trip: dispatchTrip }),
    finishTrip: (dispatchTrip) => unwrap(call, "apex.salis.api.driver_portal.complete_my_trip", { dispatch_trip: dispatchTrip }),
    markStop: (dispatchTrip, routeStop) => unwrap(call, "apex.salis.api.driver_portal.mark_stop_progress", { dispatch_trip: dispatchTrip, route_stop: routeStop }),
  });
}
