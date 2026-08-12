import { frappeRequest, setConfig } from "frappe-ui";

export function createPortalCall(request = frappeRequest) {
  return (method, params) => request({
    url: method,
    method: "POST",
    ...(params === undefined ? {} : { params }),
  });
}

export function configurePortalApi(request = frappeRequest) {
  setConfig("resourceFetcher", request);
  return createPortalCall(request);
}
