# Run Masar, Driver, and Route Supervisor Journeys

[Back to the training index](README.md)

## Outcome

Complete one training journey from route-supervisor sign-off through worker
boarding and driver execution while keeping every personal link private and every
action bound to the correct person or assigned route.

## Intended role

- An active **Employee** uses **Masar** through a personal worker link.
- An active **Salis Driver** uses **Salis Driver** through a separate personal
  driver link.
- A signed-in **Fleet Supervisor**, **Fleet Project Manager**, or **Fleet Manager**
  uses **Masar Supervisor**, but sees and acts only on submitted `Route Plan`
  records assigned to their User.
- Accommodation or HR roles issue worker links within their Building authority;
  fleet roles issue driver links within their Project authority.

## Before starting

- Use fictional records on a non-production site.
- Prepare an Active Employee with a submitted housing assignment and a scheduled
  training transport request.
- Prepare an Active driver with a submitted vehicle assignment, an enabled driver
  portal, and a training trip. Submit its Route Plan with the supervisor account
  in **Route Supervisor**.
- Give the worker and driver separate private browser sessions. Never paste a
  link or QR into a ticket, screenshot, chat room, training note, or test output.

## End-to-end exercise

1. From the worker's `Housing Assignment`, an authorized issuer uses **Issue
   Masar Link** and delivers it through the approved private channel.
2. From `Salis Driver`, an authorized fleet issuer uses **Driver Portal > Show
   Portal Link** and delivers that link separately. Use **Rotate Portal Link**
   only when a fresh credential is intended; it invalidates the previous link.
3. The assigned route supervisor signs in at **Masar Supervisor**, reviews the
   route, vehicle, driver, and ordered stops, then approves the submitted plan.
4. The worker opens Masar and confirms their own name, bed, next ride, and route.
   They open their boarding pass. When the vehicle is at their pickup stop, they
   may use **I'm at the pickup** to confirm boarding.
5. The driver opens Salis Driver, confirms their own profile and assigned vehicle,
   and checks in. On the assigned dispatched trip, they use **Start**, board the
   training worker by scanning the pass or using the manual list, mark each stop,
   then use **Complete** and check out.
6. While the trip page remains active and the device grants location permission,
   the route supervisor checks the live boarding count and driver position. A
   missing position is a valid no-location state, not permission to enter a
   location manually.
7. A Fleet Project Manager or Fleet Manager completes the `Dispatch Trip` in
   Desk. The worker then rates that completed trip once.

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
- Drivers can record attendance and their own trip execution, boarding, stops,
  fuel requests, vehicle problems, support conversations, licence-renewal
  requests when due, and clearance status. Their **Complete** action closes the
  `Trip Start Log`; it does not complete the `Dispatch Trip` workflow.
- Route-supervisor approval is a one-time sign-off on a submitted plan. It does
  not schedule, dispatch, or complete the trip. A rejection requires a reason and
  returns the plan to operations for correction.
- Driver location begins after **Start** only when the browser grants location
  access and the trip page remains active. The supervisor view marks an old fix
  as stale; worker ETA and the map cannot promise a current position without a
  recent fix.

## Evidence of completion

- Masar displays only the intended Employee; Salis Driver displays only the
  intended driver and assigned vehicle.
- The submitted Route Plan records `Approved`, the assigned supervisor, and the
  decision time.
- `Driver Attendance` records the training check-in and check-out.
- `Trip Start Log` records Started and Completed execution, and boarding evidence
  identifies the training worker without duplication.
- The staff-owned `Dispatch Trip`, not the driver action, ends in `Completed`.
- The worker's rating links to that completed trip.
- No personal link, QR, token, or cookie value appears in the retained evidence.

## Related links

- [Fleet and movement](fleet-movement.md)
- [Fuel operations](fuel.md)
- [Trainer setup and reset](trainer-setup.md)
- [Portal routes and audiences](../reference/routes-workspaces.md#served-portal-routes)
