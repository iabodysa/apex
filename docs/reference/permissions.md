# Permissions and Role Reference

This page is the canonical public reference for Apex role charters and
operational DocType permissions.

DocPerm is one layer of access. Frappe workflows can limit available actions,
and Apex row-scope hooks can limit which records a user sees. Workspace, page,
or portal navigation never grants data rights. Do not assume that System
Manager has full rights on every DocType; derive effective access from shipped
DocPerm rows, workflow state, and row-scope rules.

## Reading the matrices

Cells list the standard document rights that the shipped permlevel-zero DocPerm
rows grant: Read, Write, Create, Submit, Cancel, Amend, and Delete. An em dash
means that the role has none of those rights. Report, Export, Print, Email, and
Share are described in notes only when relevant.

## Role charters

| Role | Module | Typical user |
|------|--------|--------------|
| **Accommodation Manager** | Habitat | Owns housing, custody, safety, and license records |
| **Resident Supervisor** | Habitat | On-site supervisor; raises and executes day-to-day records (building-scoped) |
| **Maintenance Technician** | Habitat | Field technician; reads requests and works **Maintenance Work Orders** |
| **Cleaning Supervisor** | Habitat | Records housekeeping on the **Cleaning Log** |
| **Safety Officer** | Habitat | Field safety operator; records inspections, executions, and incidents |
| **Resident Request Coordinator** | Habitat | Triages resident requests and raises/submits maintenance requests |
| **Procurement Supervisor** | Habitat | Receives and hands over building stock without delete authority |
| **Finance Manager** | Cross-module | Central finance control; approves payments and reconciles costs |
| **Internal Auditor** | Cross-module | Read-only oversight where explicitly granted |
| **Fleet Manager** | Salis | Owns the fleet; unscoped across all projects |
| **Fleet Project Manager** | Salis | Manages vehicles/drivers for assigned projects only |
| **Fleet Supervisor** | Salis | Field supervisor; creates operational records |
| **Government Relations Officer** | Salis | Compliance notification recipient + Compliance workspace viewer (no record-edit rights). It holds Read, Report, and Export on five vehicle and driver compliance records and on three registers, and is granted on the **Salis** root as well as on **Compliance and Rentals** |
| **Driver** | Salis | Field driver; uses the mobile Driver Portal only. The role has `desk_access = 0` and an owner-only permission set on five Salis DocTypes — it never opens the desk |
| **SIM Operations User** | Logistay | Manages telecom contracts, SIM inventory, and SIM custody for permitted Companies |

Maintenance Manager is supplied by ERPNext. Apex neither creates it nor grants
it a DocPerm.

## Row scope

Fleet Project Managers and Fleet Supervisors see only permitted projects.
Oversight roles (Fleet Manager, Finance Manager, Internal Auditor, Government Relations Officer) see all.
Grant project access with a User Permission on Project.

Resident Supervisors are scoped through User Permissions on Building.
Accommodation Manager, Finance Manager, and Internal Auditor are unscoped for
the Habitat building filter.

SIM Operations Users are scoped through User Permissions on Company. System
Manager, Finance Manager, and Internal Auditor are unscoped for the Logistay
company filter.

The built-in All role gives every signed-in user owner-scoped Maintenance
Request intake. Assigned technicians can also see their tickets.

## Accommodation permissions

| DocType | Accommodation Manager | Resident Supervisor | Resident Request Coordinator | Finance Manager |
|---------|----------------------|---------------------|------------------------------|-----------------|
| Site (master) | Read, Write, Create | — | — | — |
| Building (master) | Read, Write, Create | Read | — | — |
| Room (master) | Read, Write, Create | Read | — | — |
| Bed (master) | Read, Write, Create | Read | — | — |
| Facility Asset | Read, Write, Create | Read | — | — |
| **Housing Assignment** *(submittable)* | Read, Write, Create, Submit, Cancel, Amend | Read, Write, Create, Submit | — | — |
| **Housing Checkout** *(submittable)* | Read, Write, Create, Submit, Cancel, Amend | Read, Write, Create, Submit | — | — |
| **Room Bed Transfer** *(submittable)* | Read, Write, Create, Submit, Cancel, Amend | — | — | — |
| Resident Request | Read, Write, Create | Read, Write, Create | Read, Write, Create | — |

Site is manager-only. Resident Request Coordinator owns request triage.
Accommodation Manager, Resident Supervisor, and Resident Request Coordinator
hold Read and Write on the permlevel-one triage fields of Resident Request.
Internal Auditor has Read, Report, and Export on Facility Asset.

## Contingent worker permissions

| DocType | Accommodation Manager | Resident Supervisor | Finance Manager | Internal Auditor |
|---------|-----------------------|---------------------|-----------------|------------------|
| Temporary Worker | Read, Write, Create | Read, Write, Create | — | Read |
| Freelancer | Read, Write, Create, Delete | — | Read, Write, Create, Delete | Read |

Temporary Worker is an accommodation intake record. HR creates the native
Employee, but Apex grants no HR role on Temporary Worker or Freelancer.

## Custody permissions

| DocType | Accommodation Manager | Resident Supervisor | Cleaning Supervisor | Procurement Supervisor |
|---------|-----------------------|---------------------|---------------------|------------------------|
| Custody Article (master) | Read, Write, Create, Delete | Read, Write, Create | — | — |
| Custody Asset Category (master) | — | — | — | — |
| **Goods Receipt** *(submittable)* | Read | — | — | Read, Write, Create, Submit, Cancel, Amend |
| **Custody Handover** *(submittable)* | Read, Write, Create, Submit, Cancel, Amend | Read, Write | — | Read, Write, Create, Submit, Cancel, Amend |
| **Custody Issue** *(submittable)* | Read, Write, Create, Submit, Cancel, Amend, Delete | Read, Write, Create | — | — |
| **Custody Return** *(submittable)* | Read, Write, Create, Submit, Cancel, Amend, Delete | Read, Write, Create | — | — |
| **Custody Damage Assessment** *(submittable)* | Read, Write, Create, Submit, Cancel, Amend, Delete | Read, Write, Create | — | — |
| **Facility Asset Custody Assignment** *(submittable)* | Read, Write, Create, Submit, Cancel, Amend | Read, Write, Create, Submit | — | — |
| **Facility Asset Movement** *(submittable)* | Read, Write, Submit, Cancel | Read, Write | — | — |
| **Cleaning Log** *(submittable)* | Read, Write, Create | Read, Write, Create | Read, Write, Create, Submit | — |

Procurement Supervisor receives and hands over building stock. Resident
Supervisors prepare custody issues, returns, and damage assessments;
Accommodation Manager submits them. Resident Supervisor can submit Facility
Asset Custody Assignment. Cleaning Supervisor submits Cleaning Log. Custody
Asset Category has no operational-role grant.

Internal Auditor has Read, Report, and Export on Custody Issue, Custody Return,
Custody Damage Assessment, Facility Asset Custody Assignment, Facility Asset
Movement, and Cleaning Log. Finance Manager has Read on Facility Asset Movement.

## Safety permissions

| DocType | Accommodation Manager | Resident Supervisor | Safety Officer |
|---------|----------------------|---------------------|----------------|
| Safety Task Catalog (master) | Read, Write, Create | Read | Read |
| **Safety Round** *(submittable)* | Read, Write, Create, Submit, Cancel, Amend | Read, Write, Create, Submit | Read, Write, Create |
| **Safety Inspection Report** *(submittable)* | Read, Write, Create, Submit, Cancel, Amend | Read, Write, Create, Submit | Read, Write, Create |
| **Safety Task Execution** *(submittable)* | Read, Write, Create, Submit, Cancel, Amend | Read, Write, Create, Submit | Read, Write, Create |
| **Safety Incident** *(submittable)* | Read, Write, Create, Submit, Cancel, Amend | Read, Write, Create, Submit | Read, Write, Create |
| **Building License** *(submittable)* | Read, Write, Create, Submit, Cancel, Amend | Read | Read, Write, Create |
| **Audit Remediation Plan** *(submittable)* | Read, Write, Create, Submit, Cancel, Amend | — | — |

Safety Officer can prepare Building License; Accommodation Manager submits,
cancels, and amends it. Internal Auditor has Read and Report on Safety Incident
and read-only access to Audit Remediation Plan.

## Maintenance permissions

All is the built-in Frappe role held by every signed-in user.

| DocType | Accommodation Manager | Resident Supervisor | Resident Request Coordinator | Maintenance Technician | All |
|---------|----------------------|---------------------|------------------------------|------------------------|--------------------------|
| **Maintenance Request** *(submittable)* | Read, Write, Create, Submit | Read, Write, Create, Submit | Read, Write, Create, Submit | Read | Read, Create *(own only)* |
| **Maintenance Inspection Report** *(submittable)* | — | — | — | — | — |
| **Maintenance Work Order** *(submittable)* | — | — | — | **Read, Write** | — |
| Maintenance Material (master) | Read, Write, Create | — | — | **Read, Write, Create** | — |
| Maintenance Material Template (master) | Read, Write, Create | — | — | **Read, Write, Create** | — |
| **Subcontractor Service Contract** *(submittable)* | Read, Write, Create, Submit, Cancel, Amend | — | — | — | — |
| **Subcontractor Service Order** *(submittable)* | Read, Write, Create, Submit | — | — | — | — |

Maintenance Inspection Report has no operational-role grant. Accommodation
Manager owns the subcontractor records. Maintenance Technician and
Accommodation Manager maintain the material masters.

## Cost and leasing permissions

| DocType | Accommodation Manager | Finance Manager | Internal Auditor |
|---------|----------------------|-----------------|------------------|
| Utility Account (master) | Read, Write, Create | Read | — |
| **Utility Bill Entry** *(submittable)* | Read, Write, Create, Submit | Read, Write, Create, Submit, Cancel | Read |
| Operational Depreciation Policy (master) | — | — | — |
| **Lease** *(submittable)* | Read, Write, Create, Submit | **Read, Write, Create, Submit, Cancel** | Read |
| **Rent Payment Schedule** *(child table)* | — | — | — |

Operational Depreciation Policy has no operational-role grant. Internal Auditor
has read-only oversight across the related cost records.

## Telecom permissions

| DocType | SIM Operations User | Finance Manager | Internal Auditor | System Manager |
|---------|---------------------|-----------------|------------------|----------------|
| **Telecom Contract** *(submittable)* | Read, Write, Create, Submit, Cancel, Amend | Read | Read | Read, Write, Create, Submit, Cancel, Amend, Delete |
| SIM Card (master) | Read, Write, Create | Read | Read | Read, Write, Create, Delete |
| **SIM Custody Assignment** *(submittable)* | Read, Write, Create, Submit, Cancel, Amend | Read | Read | Read, Write, Create, Submit, Cancel, Amend, Delete |

SIM Operations User has Report, Export, and Print on all three records. Finance
Manager and Internal Auditor have reporting and export access. Only System
Manager has Delete; operational users preserve the contract and custody
history.

## Settings permissions

These settings are Frappe Singles. A settings form affects the whole site.

| DocType | System Manager | Accommodation Manager | Fleet Manager | Fleet Project Manager | Finance Manager | Internal Auditor |
|---------|----------------|-----------------------|---------------|-----------------------|-----------------|------------------|
| Apex Settings | Read, Write, Create, Delete | — | — | — | Read | — |
| Habitat Settings | Read, Write, Create, Delete | — | — | — | — | — |
| Salis Settings | Read, Write, Create, Delete | — | Read, Write, Create, Delete | — | Read | Read |
| Apex Integration Settings | Read, Write, Create, Delete | Read | Read | — | — | — |
| Payment Routing Settings | Read, Write, Create, Delete | — | — | — | Read | — |
| Salary Deduction Policy | Read, Write, Create, Delete | — | — | — | Read, Write | Read |
| Driver Portal Theme | Read, Write, Create, Delete | — | Read, Write, Create, Delete | Read | — | Read |

Read access does not grant a settings change. Record the previous value and
test changes on a non-production site.

## Personal portal credential permissions

HR User is supplied by HRMS.

| DocType | System Manager | Accommodation Manager | Resident Supervisor | HR User | Fleet Manager | Fleet Project Manager | Fleet Supervisor |
|---------|----------------|-----------------------|---------------------|---------|---------------|-----------------------|------------------|
| Masar Worker Token | Read, Write, Create, Delete | Read, Write, Create | Read, Write, Create | Read, Write, Create | Read, Write, Create | Read, Write, Create | Read, Write, Create |

These DocPerms allow record handling only. Holder type, issuer action, row
scope, expiry, rotation, and server-side token validation still apply.

## System-written record permissions

These records are engine output. Read them for traceability; do not create,
edit, or delete them to repair an operational source record.

### Habitat engines

| DocType | System Manager | Accommodation Manager | Resident Supervisor | Safety Officer | Finance Manager | Internal Auditor |
|---------|----------------|-----------------------|---------------------|----------------|-----------------|------------------|
| Accommodation Ledger | Read | — | — | — | Read | Read |
| Accommodation Stock Ledger | Read, Delete | Read | — | — | Read | Read |
| Maintenance Cost Ledger | Read | Read | — | — | Read | Read |
| Occupancy Snapshot | Read, Delete | Read | Read | — | Read | Read |
| **Operational Depreciation Snapshot** *(submittable)* | Read, Write, Submit, Cancel, Delete | Read, Write, Submit, Cancel, Amend, Delete | Read, Write | — | Read | Read |
| Safety Finding Ledger | Read | Read | — | Read | — | Read |

Operational Depreciation Snapshot currently has broader DocPerms than the
other engine records. Treat that as an application control boundary, not an
instruction for manual correction.

### Salis engines

| DocType | System Manager | Fleet Manager | Finance Manager | Internal Auditor |
|---------|----------------|---------------|-----------------|------------------|
| Trip Fulfilment Ledger | Read | Read | Read | Read |
| Fuel Consumption Ledger | Read | Read | Read | Read |
| Rental Accrual Ledger | Read | Read | Read | Read |

## Fleet master permissions

| DocType | Fleet Manager | Fleet Project Manager | Fleet Supervisor | Driver | Finance Manager | Internal Auditor |
|---------|---------------|-----------------------|------------------|--------|-----------------|------------------|
| **Salis Vehicle** | Read, Write, Create, Delete | Read, Write, Create | Read, Write, Create | — | Read | Read |
| **Salis Driver** | Read, Write, Create, Delete | Read, Write, Create | Read, Write, Create | Read | Read | Read |
| Vehicle Category (master) | Read, Write, Create, Delete | Read, Write, Create | Read, Write, Create | — | Read | Read |
| **Salis Vehicle Compliance** *(child table)* | — | — | — | — | — | — |
| **Driver Clearance** *(submittable)* | Read, Write, Create, Submit, Cancel, Delete | — | Read, Write, Create | — | Read | Read |

Salis Vehicle Compliance is a child table and inherits access through its parent.
Government Relations Officer has Read, Report, and Export on Salis Vehicle,
Salis Driver, Driver Clearance, and Driver Suspension.

## Vehicle control permissions

| DocType | Fleet Manager | Fleet Project Manager | Fleet Supervisor | Finance Manager | Internal Auditor | Government Relations Officer |
|---------|---------------|-----------------------|------------------|-----------------|------------------|--------------------------------|
| **Vehicle Suspension** *(submittable)* | Read, Write, Create, Submit, Cancel, Delete | Read, Write, Create, Submit, Cancel, Amend | Read, Write, Create | Read | Read | — |
| **Driver Suspension** *(submittable)* | Read, Write, Create, Submit, Cancel, Delete | Read, Write, Create, Submit | Read, Write, Create | Read | Read | Read |
| **Vehicle Incident** *(submittable)* | Read, Write, Create, Submit, Cancel, Delete | Read, Write, Create | Read, Write, Create | — | Read | Read |
| **Vehicle Damage Write-Off** *(workflow)* | Read, Write, Create, Submit, Cancel, Delete | — | Read, Write, Create, Submit | Read | Read | — |
| **Vehicle Handover** *(submittable)* | Read, Write, Create, Submit, Cancel, Delete | Read, Write, Create, Submit, Cancel, Amend | Read, Write, Create | Read | Read | — |

Project scope applies to Fleet Project Manager and Fleet Supervisor. The
Government Relations Officer grant is read-only and limited to the two rows
shown.

## Dispatch and transport permissions

| DocType | Fleet Manager | Fleet Project Manager | Fleet Supervisor | Driver |
|---------|---------------|-----------------------|------------------|--------|
| **Vehicle Assignment** *(submittable)* | Read, Write, Create, Submit, Cancel, Delete | Read, Write, Create, Submit, Cancel, Amend | Read, Write, Create | — |
| **Transport Request** *(workflow)* | Read, Write, Create, Submit, Cancel, Delete | Read, Write, Create, Submit | Read, Write, Create, Submit | — |
| **Dispatch Trip** *(workflow)* | Read, Write, Create, Submit, Cancel, Delete | Read, Write, Create, Submit | Read, Write, Create | — |
| **Route Plan** *(submittable)* | Read, Write, Create, Submit, Cancel, Delete | Read, Write, Create, Submit | Read, Write, Create | — |
| **Passenger Manifest** *(submittable)* | Read, Write, Create, Submit, Cancel, Delete | Read, Write, Create, Submit | Read, Write, Create | — |
| **Issue** (field support) | — | — | — | — |

The Driver portal reads trip, manifest, and Issue data on the driver's behalf
after resolving the personal token. Apex adds no Issue DocPerm.

## Fuel permissions

| DocType | Fleet Manager | Fleet Project Manager | Fleet Supervisor | Finance Manager |
|---------|---------------|-----------------------|------------------|-----------------|
| **Fuel Quota** *(submittable)* | Read, Write, Create, Submit, Cancel, Delete | Read, Write, Create, Submit | Read, Write, Create | Read |
| **Fuel Request** *(submittable)* | Read, Write, Create, Submit, Cancel, Delete | Read, Write, Create, Submit | Read, Write, Create | Read |
| **Fuel Claim** *(workflow)* | Read, Write, Create, Submit, Cancel, Delete | Read, Write, Create | Read, Write, Create | Read, Write |
| **Fuel Exception Case** *(workflow)* | Read, Write, Create, Submit, Cancel, Amend, Delete | Read, Write, Create | Read, Write, Create | Read |
| Fuel Platform (master) | Read, Write, Create, Delete | Read, Write, Create | Read, Write, Create | Read |
| Fuel Daily Log | Read, Write, Create, Delete | Read, Write, Create | Read, Write, Create | Read, Write |

Project scope applies to Fleet Project Manager and Fleet Supervisor. Internal
Auditor has Read, Report, and Export on all records in this matrix.

## Rental permissions

| DocType | Fleet Manager | Fleet Project Manager | Fleet Supervisor | Finance Manager |
|---------|---------------|-----------------------|------------------|-----------------|
| Rental Office (master) | Read, Write, Create, Delete | Read, Write, Create | Read, Write, Create | Read |
| **Rental Vehicle Movement** *(submittable)* | Read, Write, Create, Submit, Cancel, Delete | Read, Write, Create | Read, Write, Create | Read |
| **Rental Settlement** *(workflow)* | Read, Write, Create, Submit, Cancel, Delete | Read, Write, Create | — | Read, Write |

Internal Auditor has read-only oversight on these records and Rental Accrual
Ledger.

## Payment and approval permissions

| DocType | Fleet Manager | Fleet Project Manager | Fleet Supervisor | Finance Manager |
|---------|---------------|-----------------------|------------------|-----------------|
| **Salis Payment Request** *(workflow)* | Read, Write, Create, Submit, Cancel, Delete | Read, Write, Create | Read, Write, Create | Read, Write, Submit, Cancel |
| **Movement Cost Recovery** *(workflow)* | Read, Write, Create, Submit, Cancel, Delete | — | Read, Write, Create, Submit | Read, Write |
| **Movement Cost Transfer** *(workflow)* | Read, Write, Create, Submit, Cancel, Delete | Read, Write, Create | — | Read, Write |

Internal Auditor has read-only oversight on these records.

## Driver permissions

Driver has no Desk access. Each DocPerm row below carries `if_owner`; the
personal-link portal applies additional server-side identity scope.

| DocType | Driver |
|---------|--------|
| Salis Driver | Read |
| Boarding Scan Log | Read |
| Driver Attendance | Read, Create, Submit |
| Driver Suspension | Read |
| Trip Start Log | Read, Write, Create, Submit |

Salis Vehicle and Issue are not part of the Driver grant. The portal reads or
creates those records on the driver's behalf after resolving identity.
