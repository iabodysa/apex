// Copyright (c) 2026, AFMCO and contributors

function communicationOrder(communication) {
  return [
    communication.communication_date || "",
    communication.creation || "",
    communication.name || "",
  ];
}

export function isCurrentTicketRequest(requested, active) {
  return (
    requested.ticket === active.ticket
    && requested.generation === active.generation
  );
}

export function mergeCommunicationPages(current, incoming) {
  const byName = new Map();
  for (const communication of [...current, ...incoming]) {
    byName.set(communication.name, communication);
  }
  return [...byName.values()].sort((left, right) => {
    const leftOrder = communicationOrder(left);
    const rightOrder = communicationOrder(right);
    for (let index = 0; index < leftOrder.length; index += 1) {
      const compared = leftOrder[index].localeCompare(rightOrder[index]);
      if (compared) return compared;
    }
    return 0;
  });
}
