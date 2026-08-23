# IT Operations Track

[Back to training](../README.md)

## Outcome

Restore service for one scoped Desk persona and one personal portal user without
broadening access, exposing a credential, or editing protected state directly.

## Roles

Use separate **System Manager**, affected-persona, and portal-user sessions on a
disposable training site. Add a security or integration reviewer when the selected
case crosses that boundary.

## Guide sequence

1. Prepare and restore the site with [Trainer Setup and Reset](../trainer-setup.md).
2. Review role, scope, and supported settings in
   [Follow Work from Request to Proof](../foundations.md) and [Settings](../settings.md).
3. Rehearse safe personal-link handling in
   [Worker and Driver Portals](../portals-masar-driver.md).
4. Check the **Error Log** for diagnosis.
5. Use the **Scheduled Job Type** and **Scheduled Job Log** screens to identify the
   source and result of the selected background operation.

## Capstone

1. Confirm maintenance mode is off before opening Desk or issuing, rotating, or
   testing a personal token.
2. Reproduce one missing-page or missing-record report with the affected fictional
   persona. Compare the expected route, role, and Building, Project, or Company
   scope, including one expected denial.
3. Correct only the verified configuration error and repeat the same checks.
4. In Desk, rotate the fictional user's personal portal link. Prove that the old
   link is rejected and the new link resolves only to its intended holder without
   recording either credential.
5. Trace one scheduled Apex follow-up from its source record to the job log and
   result without creating the output manually.

## Passing evidence

Show the cause and minimal correction for the Desk case, the expected scope and
denial, safe link rotation, and the source-to-job-to-result chain. Stop and isolate
the site if production data, real recipients, credential leakage, or unexplained
cross-scope access appears.

## Related links

- [Trainer Setup and Reset](../trainer-setup.md)
