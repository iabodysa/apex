# Driver and Worker Portals

[Back to training](README.md)

## Audience

Workers, drivers, supervisors who issue worker access links, and support staff
who troubleshoot the mobile experience.

## Outcome

Use the worker portal for one person, explain what the worker and driver
experiences share, and protect every issued personal link.

## Prerequisites

- A non-production training site.
- One active Employee and one active Salis Driver created for training.
- A trainer-issued worker access link. A driver link is optional until a
  reviewed Desk issuance action is available.
- A demo housing assignment, transport request, and driver trip where the
  exercise needs them.
- [Portal routes](../reference/routes-workspaces.md#served-portal-routes) and
  [permissions](../reference/permissions.md).

## One build, two experiences

The Worker and Driver entry pages load the same built mobile package. The entry
type selects either the worker screens or the driver screens:

- **Worker** opens the Masar experience.
- **Driver** opens the driver experience.

The shared package does not merge their authority. Worker and driver links are
bound to different subject types, and each server call resolves that subject
before reading or writing records. The browser does not choose an Employee or
driver identifier.

A visible tab, route, or button is navigation only. The server still checks the
personal identity, active status, record ownership, and applicable business
state.

## Worker path

An active Employee can use Masar to:

- view their profile and document-expiry notices;
- view their current accommodation and custody;
- view transport, route, boarding, and trip history;
- request transport and confirm boarding where the trip state allows it;
- raise and track resident requests, including an optional photo;
- rate a completed trip; and
- notify HR when the Iqama-expiry action is available.

A Temporary Worker cannot receive a worker portal link. Complete the
[Temporary Worker linking flow](contingent-workers.md) first.

## Driver path

An active Salis Driver can use the driver experience to:

- view their profile, assigned vehicle, compliance dates, and clearance state;
- check in and out, with an optional shift photo;
- view, start, board, navigate, and complete assigned trips;
- view route stops and report stop progress;
- submit a fuel request and review their own requests;
- raise, read, and reply to support tickets;
- report a vehicle problem or request licence renewal when due; and
- download a clearance certificate after clearance is issued.

Actions remain limited to the driver resolved from the personal link. A driver
cannot select another driver or trip outside that identity.

## Issuing and supporting access

1. Confirm that the Employee is Active.
2. Create a new **Masar Worker Token**.
3. Set **Holder Type** to **Worker**, **Worker Type** to **Employee**, and
   **Worker** to the intended Employee, then Save.
4. Use whichever **Issue Link and QR** or **Rotate Link and QR** action is
   displayed. Either action generates a fresh link and invalidates any previous
   link. The label depends on whether the user's form can read the
   permission-level-one token field, not on lifecycle state.
5. **Enabled**, **Expires On**, and the credential fields are read-only. Do not
   edit them or the database to change access.
6. The current Desk UI has no reviewed driver-link issuance action. Do not work
   around it with direct API calls or hand-built URLs.
7. Share the worker link only through the approved private channel.
8. Ask the person to open the link on their own device and confirm their name.
9. If the link is exposed or the device changes hands, close the affected
   session, generate a fresh link with the displayed action, and notify the site
   administrator or security owner through your organization's
   credential-incident procedure. Confirm that the old link is rejected and the
   incident is recorded without the credential.
10. If access must end, escalate to the site administrator. This release has no
    reviewed Disable or Set Expiry action on the form; revocation follows the
    approved administrative process.
11. Do not copy links into tickets, screenshots, chat rooms, or training notes.

Worker issuance can be restricted by Building. Use the
[permissions reference](../reference/permissions.md) for the current role and
row-scope rules.

## Exercise

1. Open the training worker link in a private browser window.
2. Confirm the expected Employee name, accommodation, and next transport.
3. Create one low-priority resident request with `TRAINING` in the subject.
4. Confirm that driver-only actions are absent from the worker experience.

When a later release provides reviewed Desk issuance, the trainer may extend
the exercise:

1. Open the training driver link in a new private window.
2. Confirm the expected driver, vehicle, and assigned trip.
3. Raise one `TRAINING` support ticket without starting or completing a trip.
4. Verify that worker-only actions are absent from the driver experience.

## Verification

The learner can show that:

- both entry paths use one visual foundation but different screen sets;
- the displayed worker matches the issued link;
- worker requests are stamped to the correct identity;
- changing navigation does not change record authority; and
- no personal link appears in notes, screenshots, or logs.

When the optional driver exercise is available, also verify the displayed
driver and the identity stamped on the support ticket.

## Cleanup and data safety

Use fictional training records only. Close the training request and any
optional ticket through their normal lifecycle, close private browser sessions,
then follow the pre-token baseline reset in
[Trainer Setup and Reset](trainer-setup.md). The form has no reviewed Disable or
Set Expiry action; escalate to the site administrator for approved revocation
when access must end. If a link was exposed before reset, use the incident flow
above. Do not test another person's link, copy a link between worker and driver
entry paths, or use production attendance, boarding, fuel, or clearance actions
for practice.
