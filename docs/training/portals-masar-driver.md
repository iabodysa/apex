# Run Masar Worker, Driver, and Supervisor Journeys

[Back to the training index](README.md)

## Outcome

Complete one journey from a planned trip through worker boarding and driver execution,
while the supervisor follows requests, stops, passengers, and live status. Keep every
personal link private and every action bound to the correct person or trip.

## Intended role

- An active **Employee** uses **Masar** through a personal worker link.
- An active **Salis Driver** uses **Salis Driver** through a separate personal
  driver link.
- A signed-in **Fleet Supervisor**, **Fleet Project Manager**, or **Fleet Manager** uses
  **Masar Supervisor** for transport requests, recurring assignments, planned and active
  trips, the live map, and movement history within their scope.
- Accommodation or HR roles issue worker links within their Building authority;
  fleet roles issue driver links within their Project authority.

## Before starting

- Use fictional records on a non-production site.
- Prepare an Active Employee with a submitted housing assignment and an approved
  Transport Request assigned to a planned Dispatch Trip.
- Prepare an Active driver with a submitted vehicle assignment, an enabled driver
  portal, and that Dispatch Trip.
- For a recurring trip, approve a Route Assignment built from an active Work Shift and
  Route Template. For a one-off trip, use an Ad Hoc Dispatch Trip with explicit stops.
- Give the worker and driver separate private browser sessions. Never paste a
  link or QR into a ticket, screenshot, chat room, training note, or test output.

## End-to-end exercise

1. From the worker's `Housing Assignment`, an authorized issuer uses **Issue
   Masar Link** and delivers it through the approved private channel.
2. From `Salis Driver`, an authorized fleet issuer uses **Driver Portal > Show
   Portal Link** and delivers that link separately. Use **Rotate Portal Link**
   only when a fresh credential is intended; it invalidates the previous link.
3. The supervisor signs in at **Masar Supervisor** and checks the request queue,
   recurring assignment, generated trip, ordered stops, vehicle, driver, and passenger
   count. The Fleet Supervisor dispatches the trip only when those facts agree.
4. The worker opens Masar and confirms their name, accommodation, next ride, pickup stop,
   and destination. They open the boarding pass. When the driver reports arrival, the
   worker may use **Wait for me**, then **I'm on the bus** within the boarding window.
5. The driver opens Salis Driver, confirms their profile, vehicle, route, stops, and
   passenger list, then uses **Start trip**. At each stop they report arrival, scan or
   record boarding, notify remaining passengers, and report departure.
6. The worker's claim appears to the driver as a claim, not final proof. The driver may
   confirm it or return the worker to the waiting list when the person is not on board.
7. While the trip page remains active and the device grants location permission, the
   supervisor checks live boarding and driver position. A missing or stale position is a
   valid no-location state, not permission to enter a location manually.
8. The driver uses **End trip** to close driver execution. A Fleet Supervisor, Fleet
   Project Manager, or Fleet Manager then completes the staff-owned Dispatch Trip. The
   worker rates that trip once.

## Decisions and exceptions

- A personal link is a bearer credential. The person opening it is not asked to
  choose an Employee, driver, trip, or Project; the link determines the identity.
  A worker link cannot be reused as a driver link or vice versa.
- Worker access is available only to an Active Employee. A `Temporary Worker`
  must first be linked to a permanent Employee. Driver access is available only
  while the `Salis Driver` is Active and the portal is enabled.
- If a driver link is exposed or a device is lost, use **Revoke Portal Link** on
  `Salis Driver` immediately. Suspension, clearance, or changing the driver to a
  non-Active status also revokes it. Reissue only after the incident is closed.
- There is no equivalent worker **Revoke Portal Link** action in the current Desk
  UI. Rotate an exposed worker link so the old one fails, and involve the site
  administrator when all access must end while the Employee remains Active.
  Making the Employee non-Active revokes the worker link automatically.
- Workers can view their profile, accommodation, custody, transport, boarding,
  resident requests, and completed-trip rating. They can request Site Transport
  or Inter-City Relocation, but not an Administrative Trip.
- Drivers can view their profile, accommodation, custody, requests, assigned trips, stops,
  and passenger boarding. Vehicle receipt, fuel, incidents, and support belong to the
  separate Salis representative portal, not the driver journey.
- A Route Assignment defines recurring operation and generates planned trips. A Dispatch
  Trip is the actual journey and may group several Transport Requests with different
  pickup and drop-off stops.
- The driver's **End trip** action sets the `Trip Start Log` to Completed and stamps its
  end time; it does not complete the `Dispatch Trip` workflow.
- Driver location begins after **Start trip** only when the browser grants location
  access and the trip page remains active. The supervisor view marks an old fix
  as stale; worker ETA and the map cannot promise a current position without a
  recent fix.

## Evidence of completion

- Masar displays only the intended Employee; Salis Driver displays only the
  intended driver and assigned vehicle.
- The approved Route Assignment and generated Dispatch Trip carry the expected shift,
  route template, supervisor, driver, vehicle, and stops.
- `Driver Attendance` records the training check-in and check-out.
- `Trip Start Log` records Started and Completed execution, and boarding evidence
  identifies the training worker without duplication.
- The worker's wait and boarding claim reach the driver, and the driver's decision reaches
  the worker without a manual refresh while the application is open.
- The staff-owned `Dispatch Trip`, not the driver action, ends in `Completed`.
- The worker's rating links to that completed trip.
- No personal link, QR, token, or cookie value appears in the retained evidence.

## Related links

- [Fleet and movement](fleet-movement.md)
- [Fuel operations](fuel.md)
- [Trainer setup and reset](trainer-setup.md)
- [Training map](README.md)
