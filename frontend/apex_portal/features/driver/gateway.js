async function unwrap(call, method, params) {
  const response = params === undefined ? await call(method) : await call(method, params);
  return response?.message ?? response;
}

function mutationGate() {
  const pending = new Map();
  return (key, action) => {
    if (pending.has(key)) return pending.get(key);
    const request = Promise.resolve().then(action);
    pending.set(key, request);
    request.then(
      () => pending.delete(key),
      () => pending.delete(key),
    );
    return request;
  };
}

export function createDriverGateway(call) {
  const mutate = mutationGate();
  const submit = (key, method, params) => mutate(key, () => unwrap(call, method, params));
  return Object.freeze({
    startTrip: (dispatchTrip) =>
      submit(`start:${dispatchTrip}`, "apex.salis.api.driver_portal.start_my_trip", {
        dispatch_trip: dispatchTrip,
      }),
    finishTrip: (dispatchTrip) =>
      submit(`finish:${dispatchTrip}`, "apex.salis.api.driver_portal.complete_my_trip", {
        dispatch_trip: dispatchTrip,
      }),
    setStopProgress: (dispatchTrip, routeStop, done) => submit(`stop:${dispatchTrip}:${routeStop}`, "apex.salis.api.driver_portal.mark_stop_progress", { dispatch_trip: dispatchTrip, route_stop: routeStop, done: done ? 1 : 0 }),
    arriveAtStop: (dispatchTrip, routeStop) => submit(`arrive:${dispatchTrip}:${routeStop}`, "apex.salis.api.driver_portal.mark_arrived", { dispatch_trip: dispatchTrip, route_stop: routeStop }),
    scanPass: (passToken) =>
      submit(`scan:${passToken}`, "apex.salis.api.boarding.scan_boarding_pass", {
        pass_token: passToken,
      }),
    manualBoard: (dispatchTrip, employee) => submit(`manual:${dispatchTrip}:${employee}`, "apex.salis.api.manual_boarding.board_worker", { dispatch_trip: dispatchTrip, employee }),
    notifyPassengers: (dispatchTrip) => submit(`notify:${dispatchTrip}`, "apex.salis.api.boarding_flow.notify_remaining_passengers", { dispatch_trip: dispatchTrip }),
    markNotBoarded: (dispatchTrip, employee) => submit(`unmark:${dispatchTrip}:${employee}`, "apex.salis.api.boarding_flow.driver_mark_not_boarded", { dispatch_trip: dispatchTrip, employee }),
    depart: (dispatchTrip) =>
      submit(`depart:${dispatchTrip}`, "apex.salis.api.boarding_flow.depart_and_finalize", {
        dispatch_trip: dispatchTrip,
      }),
    chooseLanguage: (language) =>
      submit(`language:${language}`, "apex.apex_core.api.portal_device.choose_driver_language", {
        language,
      }),
    finishOnboarding: () =>
      submit("onboarding", "apex.apex_core.api.portal_device.finish_driver_onboarding"),
  });
}
