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
    requestWait: () => mutate("wait", () => unwrap(call, "apex.salis.api.boarding_flow.worker_request_wait")),
    claimBoarded: () => mutate("boarded", () => unwrap(call, "apex.salis.api.boarding_flow.worker_claim_boarded")),
    createRequest: (values) =>
      unwrap(call, "apex.salis.api.masar.create_worker_request", {
        category: values.request_type,
        subject: values.subject,
        body: values.description,
      }),
    createTransportRequest: (values) =>
      unwrap(call, "apex.salis.api.masar.create_worker_transport_request", {
        service_line: "Site Transport",
        from_location: values.pickup_point,
        to_location: values.destination,
        pickup_datetime: values.travel_date,
        purpose: values.reason,
      }),
  });
}
