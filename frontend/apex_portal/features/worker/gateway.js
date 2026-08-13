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

export function createWorkerGateway(call) {
  const mutate = mutationGate();
  return Object.freeze({
    home: () => unwrap(call, "apex.salis.api.masar.get_worker_home"),
    profile: () => unwrap(call, "apex.salis.api.masar.get_worker_context"),
    accommodation: () => unwrap(call, "apex.salis.api.masar.get_worker_accommodation"),
    custody: () => unwrap(call, "apex.salis.api.masar.get_worker_custody"),
    transport: () => unwrap(call, "apex.salis.api.masar.get_worker_transport"),
    boarding: () => unwrap(call, "apex.salis.api.boarding_flow.worker_trip_boarding"),
    boardingPass: (transportRequest) => unwrap(
      call,
      "apex.salis.api.masar.get_worker_boarding_pass",
      { transport_request: transportRequest },
    ),
    requestWait: () => mutate(
      "wait",
      () => unwrap(call, "apex.salis.api.boarding_flow.worker_request_wait"),
    ),
    claimBoarded: () => mutate(
      "boarded",
      () => unwrap(call, "apex.salis.api.boarding_flow.worker_claim_boarded"),
    ),
    requests: () => unwrap(call, "apex.salis.api.masar.list_worker_requests"),
    request: (name) => unwrap(call, "apex.salis.api.masar.get_worker_request_detail", { name }),
    createRequest: (values) => unwrap(call, "apex.salis.api.masar.create_worker_request", {
      category: values.request_type,
      subject: values.subject,
      body: values.description,
    }),
    createTransportRequest: (values) => unwrap(
      call,
      "apex.salis.api.masar.create_worker_transport_request",
      {
        service_line: "Site Transport",
        from_location: values.pickup_point,
        to_location: values.destination,
        pickup_datetime: values.travel_date,
        purpose: values.reason,
      },
    ),
  });
}
