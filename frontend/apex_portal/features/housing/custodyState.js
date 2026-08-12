export function nextCustodySelection(state, change) {
  if (Object.hasOwn(change, "building") && change.building !== state.building) {
    return { building: change.building, holder: null, cart: [] };
  }
  if (Object.hasOwn(change, "holder")) {
    return { ...state, holder: change.holder, cart: [] };
  }
  return { ...state, ...change };
}
