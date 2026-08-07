# Permissions reference

<!-- Generated from the DocPerm rows in the shipped DocType JSON. Do not edit by
     hand; edit the DocType and regenerate. -->

Every DocPerm row apex ships, one row per grant. This page is derived from the
same JSON a site installs, so it cannot disagree with the running permissions.

## DocPerm is not effective access

A DocPerm row is the widest a role can act; three other layers narrow it.

- A **Frappe Workflow** decides which transitions a role may make on a document
  that is otherwise writable.
- **Row scope** decides which records come back. Fleet Project Manager and Fleet
  Supervisor are scoped by User Permission on Project; Resident Supervisor is
  scoped by User Permission on Building. `apex/habitat/permissions.py` and the
  Salis scope modules own that side.
- **Permlevel** splits a document into field bands. A permlevel-1 row grants
  nothing on the ordinary fields; it opens the fields tagged at that level.

Workspace, desk page and portal navigation grant no data rights at all. A role
that reaches a screen still resolves every record through the rows below.

Who each role is written for is a judgement rather than a schema fact, so the
role charters stay in [the training index](../training/README.md).

## Two grants are not in this table

Both are Custom DocPerm rows written at install and migrate time against core
DocTypes apex does not own, so no shipped JSON carries them:

- `apex/apex_core/setup/seeders/habitat_core_link_perms_seed.py` grants Habitat
  roles `select` on Employee, Project and Cost Center so their own Link fields
  and register reports resolve.
- `apex/apex_core/setup/seeders/salis_issue_seed.py` does the same for Issue.

## Reading a row

**Document rights** and **Data rights** list only what the row actually grants;
`—` means none of that group. **Level** is the permlevel — `0` is the
document itself, a higher number is a field band. **Row filter** reads
`Own records only` when the row carries `if_owner`.

DocTypes that ship no DocPerm row of their own are listed under each module. A
child table takes its access from the parent document it sits in.

## Coverage

| Measure | Count |
| --- | --- |
| DocTypes shipped | 152 |
| DocTypes granting at least one role | 113 |
| DocPerm rows | 540 |
| Roles granted | 18 |

## Roles

| Role | DocTypes | DocPerm rows |
| --- | --- | --- |
| Accommodation Manager | 54 | 68 |
| All | 1 | 1 |
| Cleaning Supervisor | 2 | 2 |
| Driver | 5 | 5 |
| Finance Manager | 58 | 63 |
| Fleet Manager | 46 | 50 |
| Fleet Project Manager | 35 | 38 |
| Fleet Supervisor | 35 | 38 |
| Government Relations Officer | 5 | 5 |
| HR User | 1 | 1 |
| Internal Auditor | 71 | 74 |
| Maintenance Technician | 4 | 4 |
| Procurement Supervisor | 3 | 5 |
| Resident Request Coordinator | 2 | 3 |
| Resident Supervisor | 32 | 39 |
| SIM Operations User | 3 | 3 |
| Safety Officer | 7 | 7 |
| System Manager | 113 | 134 |

## Modules

- [Apex Core](#apex-core)
- [Habitat](#habitat)
- [Logistay](#logistay)
- [Salis](#salis)

## Apex Core

| DocType | Role | Level | Document rights | Data rights | Row filter |
| --- | --- | --- | --- | --- | --- |
| Apex Integration Settings | Accommodation Manager | 0 | Read | — | — |
| Apex Integration Settings | Fleet Manager | 0 | Read | — | — |
| Apex Integration Settings | System Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Apex Settings | Finance Manager | 0 | Read | — | — |
| Apex Settings | System Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Habitat Settings | System Manager | 0 | Read, Write, Create, Delete | Print, Email, Share | — |
| Masar Worker Token | Accommodation Manager | 0 | Read, Write, Create | Report, Print, Share | — |
| Masar Worker Token | Fleet Manager | 0 | Read, Write, Create | Report, Print | — |
| Masar Worker Token | Fleet Project Manager | 0 | Read, Write, Create | Report, Print | — |
| Masar Worker Token | Fleet Supervisor | 0 | Read, Write, Create | Report, Print | — |
| Masar Worker Token | HR User | 0 | Read, Write, Create | Report, Print | — |
| Masar Worker Token | Resident Supervisor | 0 | Read, Write, Create | Report, Print | — |
| Masar Worker Token | System Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Masar Worker Token | System Manager | 1 | Read, Write | — | — |
| Payment Routing Settings | Finance Manager | 0 | Read | — | — |
| Payment Routing Settings | System Manager | 0 | Read, Write, Create, Delete | Print, Email, Share | — |
| Salary Deduction Policy | Finance Manager | 0 | Read, Write | — | — |
| Salary Deduction Policy | Internal Auditor | 0 | Read | Report | — |
| Salary Deduction Policy | System Manager | 0 | Read, Write, Create, Delete | Print, Email, Share | — |
| Salis Settings | Finance Manager | 0 | Read | — | — |
| Salis Settings | Fleet Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Salis Settings | Internal Auditor | 0 | Read | Report, Export | — |
| Salis Settings | System Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |

No DocPerm row of its own: Payment Routing Field Map (child table), Salary Deduction Type Rule (child table).

## Habitat

| DocType | Role | Level | Document rights | Data rights | Row filter |
| --- | --- | --- | --- | --- | --- |
| Accommodation Ledger | Finance Manager | 0 | Read | Report | — |
| Accommodation Ledger | Internal Auditor | 0 | Read | Report, Export | — |
| Accommodation Ledger | System Manager | 0 | Read | Report | — |
| Accommodation Stock Ledger | Accommodation Manager | 0 | Read | Report, Export, Print, Email, Share | — |
| Accommodation Stock Ledger | Finance Manager | 0 | Read | Report, Export, Print, Email, Share | — |
| Accommodation Stock Ledger | Internal Auditor | 0 | Read | Report, Export, Print, Email, Share | — |
| Accommodation Stock Ledger | System Manager | 0 | Read, Delete | Report, Export, Print, Email, Share | — |
| Arrival Batch | Accommodation Manager | 0 | Read, Write, Create, Delete | Report, Export, Share | — |
| Arrival Batch | Internal Auditor | 0 | Read | Report, Export | — |
| Arrival Batch | Resident Supervisor | 0 | Read, Write, Create | Report | — |
| Arrival Batch | System Manager | 0 | Read, Write, Create, Delete | Report, Export, Share | — |
| Arrival Batch | Accommodation Manager | 1 | Read, Write | — | — |
| Arrival Batch | Internal Auditor | 1 | Read | — | — |
| Arrival Batch | Resident Supervisor | 1 | Read, Write | — | — |
| Arrival Batch | System Manager | 1 | Read, Write | — | — |
| Audit Remediation Plan (submittable) | Accommodation Manager | 0 | Read, Write, Create, Submit, Cancel, Amend | Report | — |
| Audit Remediation Plan (submittable) | Internal Auditor | 0 | Read | Report, Export | — |
| Audit Remediation Plan (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Amend, Delete | Report, Export, Print, Email, Share | — |
| Bed | Accommodation Manager | 0 | Read, Write, Create | — | — |
| Bed | Resident Supervisor | 0 | Read | — | — |
| Bed | System Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Building | Accommodation Manager | 0 | Read, Write, Create | Report | — |
| Building | Resident Supervisor | 0 | Read | Report | — |
| Building | System Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Building License (submittable) | Accommodation Manager | 0 | Read, Write, Create, Submit, Cancel, Amend | — | — |
| Building License (submittable) | Resident Supervisor | 0 | Read | — | — |
| Building License (submittable) | Safety Officer | 0 | Read, Write, Create | — | — |
| Building License (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Amend, Delete | Report, Export, Print, Email, Share | — |
| Camera Access Grant (submittable) | Accommodation Manager | 0 | Read, Write, Create, Submit, Cancel, Amend | — | — |
| Camera Access Grant (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Amend, Delete | Report, Export, Print, Email, Share | — |
| City | System Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Cleaning Compliance Ledger | Accommodation Manager | 0 | Read | Report, Export, Print, Email, Share | — |
| Cleaning Compliance Ledger | Cleaning Supervisor | 0 | Read | Report, Export, Print, Email, Share | — |
| Cleaning Compliance Ledger | Internal Auditor | 0 | Read | Report, Export, Print, Email, Share | — |
| Cleaning Compliance Ledger | System Manager | 0 | Read, Delete | Report, Export, Print, Email, Share | — |
| Cleaning Log (submittable) | Accommodation Manager | 0 | Read, Write, Create | Report | — |
| Cleaning Log (submittable) | Cleaning Supervisor | 0 | Read, Write, Create, Submit | Report | — |
| Cleaning Log (submittable) | Internal Auditor | 0 | Read | Report, Export | — |
| Cleaning Log (submittable) | Resident Supervisor | 0 | Read, Write, Create | Report | — |
| Cleaning Log (submittable) | System Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Custody Acknowledgment | Accommodation Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Custody Acknowledgment | Internal Auditor | 0 | Read | Report, Export | — |
| Custody Acknowledgment | Resident Supervisor | 0 | Read, Write, Create | Report, Print | — |
| Custody Acknowledgment | System Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Custody Acknowledgment | Accommodation Manager | 1 | Read, Write | — | — |
| Custody Acknowledgment | Resident Supervisor | 1 | Read, Write | — | — |
| Custody Acknowledgment | System Manager | 1 | Read, Write | — | — |
| Custody Article | Accommodation Manager | 0 | Read, Write, Create, Delete | — | — |
| Custody Article | Resident Supervisor | 0 | Read, Write, Create | — | — |
| Custody Article | System Manager | 0 | Read, Write, Create, Delete | — | — |
| Custody Asset Category | System Manager | 0 | Read, Write, Create, Delete | — | — |
| Custody Damage Assessment (submittable) | Accommodation Manager | 0 | Read, Write, Create, Submit, Cancel, Amend, Delete | Report | — |
| Custody Damage Assessment (submittable) | Finance Manager | 0 | Read | Report | — |
| Custody Damage Assessment (submittable) | Internal Auditor | 0 | Read | Report, Export | — |
| Custody Damage Assessment (submittable) | Resident Supervisor | 0 | Read, Write, Create | — | — |
| Custody Damage Assessment (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report | — |
| Custody Damage Assessment (submittable) | Accommodation Manager | 1 | Read, Write | — | — |
| Custody Damage Assessment (submittable) | Finance Manager | 1 | Read, Write | — | — |
| Custody Damage Assessment (submittable) | System Manager | 1 | Read, Write | — | — |
| Custody Handover (submittable) | Accommodation Manager | 0 | Read, Write, Create, Submit, Cancel, Amend | Report, Print, Share | — |
| Custody Handover (submittable) | Procurement Supervisor | 0 | Read, Write, Create, Submit, Cancel, Amend | Report, Print, Share | — |
| Custody Handover (submittable) | Resident Supervisor | 0 | Read, Write | Report | — |
| Custody Handover (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Amend, Delete | Report, Export, Print, Email, Share | — |
| Custody Handover (submittable) | Accommodation Manager | 1 | Read | — | — |
| Custody Handover (submittable) | Procurement Supervisor | 1 | Read | — | — |
| Custody Handover (submittable) | System Manager | 1 | Read | — | — |
| Custody Issue (submittable) | Accommodation Manager | 0 | Read, Write, Create, Submit, Cancel, Amend, Delete | — | — |
| Custody Issue (submittable) | Internal Auditor | 0 | Read | Report, Export | — |
| Custody Issue (submittable) | Resident Supervisor | 0 | Read, Write, Create | — | — |
| Custody Issue (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | — | — |
| Custody Issue (submittable) | Accommodation Manager | 1 | Read, Write | — | — |
| Custody Issue (submittable) | Resident Supervisor | 1 | Read, Write | — | — |
| Custody Issue (submittable) | System Manager | 1 | Read, Write | — | — |
| Custody Return (submittable) | Accommodation Manager | 0 | Read, Write, Create, Submit, Cancel, Amend, Delete | — | — |
| Custody Return (submittable) | Internal Auditor | 0 | Read | Report, Export | — |
| Custody Return (submittable) | Resident Supervisor | 0 | Read, Write, Create | — | — |
| Custody Return (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | — | — |
| Facility Asset | Accommodation Manager | 0 | Read, Write, Create | — | — |
| Facility Asset | Internal Auditor | 0 | Read | Report, Export | — |
| Facility Asset | Resident Supervisor | 0 | Read | — | — |
| Facility Asset | System Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Facility Asset Custody Assignment (submittable) | Accommodation Manager | 0 | Read, Write, Create, Submit, Cancel, Amend | — | — |
| Facility Asset Custody Assignment (submittable) | Internal Auditor | 0 | Read | Report, Export | — |
| Facility Asset Custody Assignment (submittable) | Resident Supervisor | 0 | Read, Write, Create, Submit | — | — |
| Facility Asset Custody Assignment (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Amend, Delete | Report, Export, Print, Email, Share | — |
| Facility Asset Custody Assignment (submittable) | Accommodation Manager | 1 | Read, Write | — | — |
| Facility Asset Custody Assignment (submittable) | Resident Supervisor | 1 | Read, Write | — | — |
| Facility Asset Custody Assignment (submittable) | System Manager | 1 | Read, Write | — | — |
| Facility Asset Delivery (submittable) | Accommodation Manager | 0 | Read, Write, Create, Submit, Cancel, Amend | Report, Print, Share | — |
| Facility Asset Delivery (submittable) | Internal Auditor | 0 | Read | Report, Export | — |
| Facility Asset Delivery (submittable) | Procurement Supervisor | 0 | Read, Write, Create, Submit, Cancel, Amend | Report, Print, Share | — |
| Facility Asset Delivery (submittable) | Resident Supervisor | 0 | Read, Write | Report | — |
| Facility Asset Delivery (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Amend, Delete | Report, Export, Print, Email, Share | — |
| Facility Asset Delivery (submittable) | Accommodation Manager | 1 | Read | — | — |
| Facility Asset Delivery (submittable) | Procurement Supervisor | 1 | Read | — | — |
| Facility Asset Delivery (submittable) | System Manager | 1 | Read | — | — |
| Facility Asset Movement (submittable) | Accommodation Manager | 0 | Read, Write, Create, Submit, Cancel | Report | — |
| Facility Asset Movement (submittable) | Finance Manager | 0 | Read | Report | — |
| Facility Asset Movement (submittable) | Internal Auditor | 0 | Read | Report, Export | — |
| Facility Asset Movement (submittable) | Resident Supervisor | 0 | Read, Write, Create | — | — |
| Facility Asset Movement (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report | — |
| Facility Asset Movement (submittable) | Finance Manager | 1 | Read, Write | — | — |
| Facility Asset Movement Ledger | Accommodation Manager | 0 | Read | Report, Export | — |
| Facility Asset Movement Ledger | Internal Auditor | 0 | Read | Report, Export | — |
| Facility Asset Movement Ledger | System Manager | 0 | Read | — | — |
| Goods Receipt (submittable) | Accommodation Manager | 0 | Read | Report | — |
| Goods Receipt (submittable) | Procurement Supervisor | 0 | Read, Write, Create, Submit, Cancel, Amend | Report, Print, Share | — |
| Goods Receipt (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Amend, Delete | Report, Export, Print, Email, Share | — |
| Housing Assignment (submittable) | Accommodation Manager | 0 | Read, Write, Create, Submit, Cancel, Amend | Report | — |
| Housing Assignment (submittable) | Internal Auditor | 0 | Read | Report | — |
| Housing Assignment (submittable) | Resident Supervisor | 0 | Read, Write, Create, Submit | Report | — |
| Housing Assignment (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Amend, Delete | Report, Export, Print, Email, Share | — |
| Housing Assignment (submittable) | Accommodation Manager | 1 | Read, Write | — | — |
| Housing Assignment (submittable) | Resident Supervisor | 1 | Read, Write | — | — |
| Housing Assignment (submittable) | System Manager | 1 | Read, Write | — | — |
| Housing Checkout (submittable) | Accommodation Manager | 0 | Read, Write, Create, Submit, Cancel, Amend | Report | — |
| Housing Checkout (submittable) | Resident Supervisor | 0 | Read, Write, Create, Submit | Report | — |
| Housing Checkout (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Amend, Delete | Report, Export, Print, Email, Share | — |
| Housing Checkout (submittable) | Accommodation Manager | 1 | Read, Write | — | — |
| Housing Checkout (submittable) | Finance Manager | 1 | Read, Write | — | — |
| Housing Checkout (submittable) | System Manager | 1 | Read, Write | — | — |
| Housing Inventory | Accommodation Manager | 0 | Read, Write, Create | Report | — |
| Housing Inventory | Internal Auditor | 0 | Read | Report, Export | — |
| Housing Inventory | Resident Supervisor | 0 | Read, Write | — | — |
| Housing Inventory | System Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Idle Resident Report | Accommodation Manager | 0 | Read, Write, Create, Delete | Report | — |
| Idle Resident Report | Resident Supervisor | 0 | Read, Write, Create | — | — |
| Idle Resident Report | System Manager | 0 | Read, Write, Create, Delete | — | — |
| Lease (submittable) | Accommodation Manager | 0 | Read, Write, Create, Submit | Report | — |
| Lease (submittable) | Finance Manager | 0 | Read, Write, Create, Submit, Cancel | Report | — |
| Lease (submittable) | Internal Auditor | 0 | Read | Report, Export | — |
| Lease (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Print, Email, Share | — |
| Maintenance Cost Ledger | Accommodation Manager | 0 | Read | Report, Export | — |
| Maintenance Cost Ledger | Finance Manager | 0 | Read | Report, Export | — |
| Maintenance Cost Ledger | Internal Auditor | 0 | Read | Report, Export | — |
| Maintenance Cost Ledger | System Manager | 0 | Read | Report, Export | — |
| Maintenance Inspection Report (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | — | — |
| Maintenance Material | Accommodation Manager | 0 | Read, Write, Create | — | — |
| Maintenance Material | Maintenance Technician | 0 | Read, Write, Create | — | — |
| Maintenance Material | System Manager | 0 | Read, Write, Create, Delete | Print, Email, Share | — |
| Maintenance Material Template | Accommodation Manager | 0 | Read, Write, Create | — | — |
| Maintenance Material Template | Maintenance Technician | 0 | Read, Write, Create | — | — |
| Maintenance Material Template | System Manager | 0 | Read, Write, Create, Delete | — | — |
| Maintenance Request (submittable) | Accommodation Manager | 0 | Read, Write, Create, Submit | Report | — |
| Maintenance Request (submittable) | All | 0 | Read, Create | — | Own records only |
| Maintenance Request (submittable) | Maintenance Technician | 0 | Read | — | — |
| Maintenance Request (submittable) | Resident Request Coordinator | 0 | Read, Write, Create, Submit | — | — |
| Maintenance Request (submittable) | Resident Supervisor | 0 | Read, Write, Create, Submit | Report | — |
| Maintenance Request (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Maintenance Request (submittable) | Accommodation Manager | 1 | Read, Write | — | — |
| Maintenance Request (submittable) | Finance Manager | 1 | Read, Write | — | — |
| Maintenance Request (submittable) | System Manager | 1 | Read, Write | — | — |
| Maintenance Work Order (submittable) | Maintenance Technician | 0 | Read, Write | — | — |
| Maintenance Work Order (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | — | — |
| Material Transfer (submittable) | Accommodation Manager | 0 | Read, Write, Create, Submit, Cancel, Amend | Report | — |
| Material Transfer (submittable) | Resident Supervisor | 0 | Read, Write, Create | — | — |
| Material Transfer (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Amend, Delete | Report, Export, Print, Email, Share | — |
| Occupancy Snapshot | Accommodation Manager | 0 | Read | Report, Export, Print, Email, Share | — |
| Occupancy Snapshot | Finance Manager | 0 | Read | Report, Export, Print, Email, Share | — |
| Occupancy Snapshot | Internal Auditor | 0 | Read | Report, Export, Print, Email, Share | — |
| Occupancy Snapshot | Resident Supervisor | 0 | Read | Report, Export, Print, Email, Share | — |
| Occupancy Snapshot | System Manager | 0 | Read, Delete | Report, Export, Print, Email, Share | — |
| Operational Depreciation Policy | System Manager | 0 | Read, Write, Create, Delete | — | — |
| Operational Depreciation Snapshot (submittable) | Accommodation Manager | 0 | Read, Write, Submit, Cancel, Amend, Delete | Report | — |
| Operational Depreciation Snapshot (submittable) | Finance Manager | 0 | Read | Report | — |
| Operational Depreciation Snapshot (submittable) | Internal Auditor | 0 | Read | Report, Export | — |
| Operational Depreciation Snapshot (submittable) | Resident Supervisor | 0 | Read, Write | — | — |
| Operational Depreciation Snapshot (submittable) | System Manager | 0 | Read, Write, Submit, Cancel, Delete | Report | — |
| QR Location | Accommodation Manager | 0 | Read, Write, Create | — | — |
| QR Location | System Manager | 0 | Read, Write, Create, Delete | — | — |
| Resident Request | Accommodation Manager | 0 | Read, Write, Create | — | — |
| Resident Request | Resident Request Coordinator | 0 | Read, Write, Create | — | — |
| Resident Request | Resident Supervisor | 0 | Read, Write, Create | — | — |
| Resident Request | System Manager | 0 | Read, Write, Create, Delete | — | — |
| Resident Request | Accommodation Manager | 1 | Read, Write | — | — |
| Resident Request | Resident Request Coordinator | 1 | Read, Write | — | — |
| Resident Request | Resident Supervisor | 1 | Read, Write | — | — |
| Resident Request | System Manager | 1 | Read, Write | — | — |
| Room | Accommodation Manager | 0 | Read, Write, Create | — | — |
| Room | Resident Supervisor | 0 | Read | — | — |
| Room | System Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Room Bed Transfer (submittable) | Accommodation Manager | 0 | Read, Write, Create, Submit, Cancel, Amend | — | — |
| Room Bed Transfer (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Amend, Delete | Report, Export, Print, Email, Share | — |
| Safety Finding Ledger | Accommodation Manager | 0 | Read | Report, Export | — |
| Safety Finding Ledger | Internal Auditor | 0 | Read | Report, Export | — |
| Safety Finding Ledger | Safety Officer | 0 | Read | Report, Export | — |
| Safety Finding Ledger | System Manager | 0 | Read | Report, Export | — |
| Safety Incident (submittable) | Accommodation Manager | 0 | Read, Write, Create, Submit, Cancel, Amend | Report, Print, Email, Share | — |
| Safety Incident (submittable) | Internal Auditor | 0 | Read | Report | — |
| Safety Incident (submittable) | Resident Supervisor | 0 | Read, Write, Create, Submit | Report, Print | — |
| Safety Incident (submittable) | Safety Officer | 0 | Read, Write, Create | — | — |
| Safety Incident (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Amend, Delete | Report, Export, Print, Email, Share | — |
| Safety Inspection Report (submittable) | Accommodation Manager | 0 | Read, Write, Create, Submit, Cancel, Amend | — | — |
| Safety Inspection Report (submittable) | Resident Supervisor | 0 | Read, Write, Create, Submit | — | — |
| Safety Inspection Report (submittable) | Safety Officer | 0 | Read, Write, Create | — | — |
| Safety Inspection Report (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Amend, Delete | Report, Export, Print, Email, Share | — |
| Safety Round (submittable) | Accommodation Manager | 0 | Read, Write, Create, Submit, Cancel, Amend | — | — |
| Safety Round (submittable) | Resident Supervisor | 0 | Read, Write, Create, Submit | — | — |
| Safety Round (submittable) | Safety Officer | 0 | Read, Write, Create | — | — |
| Safety Round (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Amend, Delete | Report, Export, Print, Email, Share | — |
| Safety Task Catalog | Accommodation Manager | 0 | Read, Write, Create | — | — |
| Safety Task Catalog | Resident Supervisor | 0 | Read | — | — |
| Safety Task Catalog | Safety Officer | 0 | Read | — | — |
| Safety Task Catalog | System Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Safety Task Execution (submittable) | Accommodation Manager | 0 | Read, Write, Create, Submit, Cancel, Amend | Report | — |
| Safety Task Execution (submittable) | Resident Supervisor | 0 | Read, Write, Create, Submit | Report | — |
| Safety Task Execution (submittable) | Safety Officer | 0 | Read, Write, Create | Report | — |
| Safety Task Execution (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Amend, Delete | Report, Export, Print, Email, Share | — |
| Scheduled Task Assignment | Accommodation Manager | 0 | Read, Write, Create | — | — |
| Scheduled Task Assignment | System Manager | 0 | Read, Write, Create, Delete | — | — |
| Scheduled Task Instance (submittable) | System Manager | 0 | Read, Write, Submit, Cancel, Delete | — | — |
| Scheduled Task Template | System Manager | 0 | Read, Write, Create, Delete | — | — |
| Scheduled Task Template Item (child table) | System Manager | 0 | Read, Write, Create, Delete | — | — |
| Site | Accommodation Manager | 0 | Read, Write, Create | — | — |
| Site | System Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Subcontractor Service Contract (submittable) | Accommodation Manager | 0 | Read, Write, Create, Submit, Cancel, Amend | — | — |
| Subcontractor Service Contract (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Amend, Delete | Report, Export, Print, Email, Share | — |
| Subcontractor Service Contract (submittable) | Accommodation Manager | 1 | Read, Write | — | — |
| Subcontractor Service Contract (submittable) | Finance Manager | 1 | Read, Write | — | — |
| Subcontractor Service Contract (submittable) | System Manager | 1 | Read, Write | — | — |
| Subcontractor Service Order (submittable) | Accommodation Manager | 0 | Read, Write, Create, Submit | — | — |
| Subcontractor Service Order (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Subcontractor Service Order (submittable) | Accommodation Manager | 1 | Read, Write | — | — |
| Subcontractor Service Order (submittable) | Finance Manager | 1 | Read, Write | — | — |
| Subcontractor Service Order (submittable) | System Manager | 1 | Read, Write | — | — |
| Utility Account | Accommodation Manager | 0 | Read, Write, Create | — | — |
| Utility Account | Finance Manager | 0 | Read | — | — |
| Utility Account | System Manager | 0 | Read, Write, Create, Delete | Print, Email, Share | — |
| Utility Bill Entry (submittable) | Accommodation Manager | 0 | Read, Write, Create, Submit | Report | — |
| Utility Bill Entry (submittable) | Finance Manager | 0 | Read, Write, Create, Submit, Cancel | Report | — |
| Utility Bill Entry (submittable) | Internal Auditor | 0 | Read | Report, Export | — |
| Utility Bill Entry (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Print, Email, Share | — |

No DocPerm row of its own: Accommodation Custody Item (child table), Accommodation Custody Return Item (child table), Arrival Batch Worker (child table), Audit Remediation Building Scope (child table), Audit Remediation Item (child table), Camera Access Building Scope (child table), Cleaning Area Photo (child table), Cleaning Log Room Detail (child table), Custody Damage Item (child table), Custody Issue Item (child table), Custody Return Item (child table), Depreciation Snapshot Item (child table), Facility Custody Item (child table), Floor Plan (child table), Inspection Finding Item (child table), Linked Maintenance Request Item (child table), Maintenance Material Template Item (child table), Maintenance Procurement Item (child table), Material Transfer Item (child table), Rent Payment Schedule (child table), Safety Task Building Scope (child table), Subcontractor Building Coverage (child table).

## Logistay

| DocType | Role | Level | Document rights | Data rights | Row filter |
| --- | --- | --- | --- | --- | --- |
| Freelancer | Accommodation Manager | 0 | Read, Write, Delete | Report, Export, Print, Email, Share | — |
| Freelancer | Finance Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Freelancer | Internal Auditor | 0 | Read | Report, Export | — |
| Freelancer | System Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Freelancer | Finance Manager | 1 | Read, Write | — | — |
| Freelancer | System Manager | 1 | Read, Write | — | — |
| SIM Card | Finance Manager | 0 | Read | Report, Export, Print | — |
| SIM Card | Internal Auditor | 0 | Read | Report, Export | — |
| SIM Card | SIM Operations User | 0 | Read, Write, Create | Report, Export, Print | — |
| SIM Card | System Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| SIM Custody Assignment (submittable) | Finance Manager | 0 | Read | Report, Export, Print | — |
| SIM Custody Assignment (submittable) | Internal Auditor | 0 | Read | Report, Export | — |
| SIM Custody Assignment (submittable) | SIM Operations User | 0 | Read, Write, Create, Submit, Cancel, Amend | Report, Export, Print | — |
| SIM Custody Assignment (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Amend, Delete | Report, Export, Print, Email, Share | — |
| Telecom Contract (submittable) | Finance Manager | 0 | Read | Report, Export, Print | — |
| Telecom Contract (submittable) | Internal Auditor | 0 | Read | Report, Export | — |
| Telecom Contract (submittable) | SIM Operations User | 0 | Read, Write, Create, Submit, Cancel, Amend | Report, Export, Print | — |
| Telecom Contract (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Amend, Delete | Report, Export, Print, Email, Share | — |
| Temporary Worker | Accommodation Manager | 0 | Read, Write, Create | Report, Export, Print, Email, Share | — |
| Temporary Worker | Internal Auditor | 0 | Read | Report, Export | — |
| Temporary Worker | Resident Supervisor | 0 | Read, Write, Create | Report, Print | — |
| Temporary Worker | System Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Temporary Worker | Accommodation Manager | 1 | Read, Write | — | — |
| Temporary Worker | Internal Auditor | 1 | Read | — | — |
| Temporary Worker | Resident Supervisor | 1 | Read, Write | — | — |
| Temporary Worker | System Manager | 1 | Read, Write | — | — |

No DocPerm row of its own: Telecom Billing Document (child table).

## Salis

| DocType | Role | Level | Document rights | Data rights | Row filter |
| --- | --- | --- | --- | --- | --- |
| Boarding Scan Log | Driver | 0 | Read | — | Own records only |
| Boarding Scan Log | Finance Manager | 0 | Read | Report, Export, Print | — |
| Boarding Scan Log | Fleet Manager | 0 | Read, Create, Delete | Report, Export, Print, Email, Share | — |
| Boarding Scan Log | Fleet Project Manager | 0 | Read, Create | Report, Export, Print | — |
| Boarding Scan Log | Fleet Supervisor | 0 | Read, Create | Report, Export, Print | — |
| Boarding Scan Log | Internal Auditor | 0 | Read | Report, Export | — |
| Boarding Scan Log | System Manager | 0 | Read, Create, Delete | Report, Export, Print, Email, Share | — |
| Dispatch Trip (submittable) | Finance Manager | 0 | Read | — | — |
| Dispatch Trip (submittable) | Fleet Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Dispatch Trip (submittable) | Fleet Project Manager | 0 | Read, Write, Create, Submit | — | — |
| Dispatch Trip (submittable) | Fleet Supervisor | 0 | Read, Write, Create | — | — |
| Dispatch Trip (submittable) | Internal Auditor | 0 | Read | Report, Export | — |
| Dispatch Trip (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Driver Attendance (submittable) | Driver | 0 | Read, Create, Submit | — | Own records only |
| Driver Attendance (submittable) | Finance Manager | 0 | Read | Report, Export, Print | — |
| Driver Attendance (submittable) | Fleet Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Driver Attendance (submittable) | Fleet Project Manager | 0 | Read, Write, Create, Submit | Report, Export, Print, Email, Share | — |
| Driver Attendance (submittable) | Fleet Supervisor | 0 | Read, Write, Create | Report, Export, Print, Email, Share | — |
| Driver Attendance (submittable) | Internal Auditor | 0 | Read | Report, Export | — |
| Driver Attendance (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Driver Clearance (submittable) | Finance Manager | 0 | Read | Report, Export | — |
| Driver Clearance (submittable) | Fleet Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Driver Clearance (submittable) | Fleet Supervisor | 0 | Read, Write, Create | Report | — |
| Driver Clearance (submittable) | Government Relations Officer | 0 | Read | Report, Export | — |
| Driver Clearance (submittable) | Internal Auditor | 0 | Read | Report, Export | — |
| Driver Clearance (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Driver Portal Theme | Fleet Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Driver Portal Theme | Fleet Project Manager | 0 | Read | — | — |
| Driver Portal Theme | Internal Auditor | 0 | Read | Report, Export | — |
| Driver Portal Theme | System Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Driver Push Subscription | Fleet Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Driver Push Subscription | Fleet Project Manager | 0 | Read, Write, Create, Delete | Report | — |
| Driver Push Subscription | Internal Auditor | 0 | Read | Report, Export | — |
| Driver Push Subscription | System Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Driver Suspension (submittable) | Driver | 0 | Read | — | Own records only |
| Driver Suspension (submittable) | Finance Manager | 0 | Read | Report, Export, Print | — |
| Driver Suspension (submittable) | Fleet Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Driver Suspension (submittable) | Fleet Project Manager | 0 | Read, Write, Create, Submit | Report, Export, Print, Email, Share | — |
| Driver Suspension (submittable) | Fleet Supervisor | 0 | Read, Write, Create | Report, Export, Print, Email, Share | — |
| Driver Suspension (submittable) | Government Relations Officer | 0 | Read | Report, Export | — |
| Driver Suspension (submittable) | Internal Auditor | 0 | Read | Report, Export | — |
| Driver Suspension (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Fuel Claim (submittable) | Finance Manager | 0 | Read, Write | Report, Export | — |
| Fuel Claim (submittable) | Fleet Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Fuel Claim (submittable) | Fleet Project Manager | 0 | Read, Write, Create | Report | — |
| Fuel Claim (submittable) | Fleet Supervisor | 0 | Read, Write, Create | Report | — |
| Fuel Claim (submittable) | Internal Auditor | 0 | Read | Report, Export | — |
| Fuel Claim (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Fuel Consumption Ledger | Finance Manager | 0 | Read | Report, Export | — |
| Fuel Consumption Ledger | Fleet Manager | 0 | Read | Report, Export | — |
| Fuel Consumption Ledger | Internal Auditor | 0 | Read | Report, Export | — |
| Fuel Consumption Ledger | System Manager | 0 | Read | Report, Export | — |
| Fuel Daily Log | Finance Manager | 0 | Read, Write | Report | — |
| Fuel Daily Log | Fleet Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Fuel Daily Log | Fleet Project Manager | 0 | Read, Write, Create | Report | — |
| Fuel Daily Log | Fleet Supervisor | 0 | Read, Write, Create | Report | — |
| Fuel Daily Log | Internal Auditor | 0 | Read | Report, Export | — |
| Fuel Daily Log | System Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Fuel Exception Case (submittable) | Finance Manager | 0 | Read | Report, Export | — |
| Fuel Exception Case (submittable) | Fleet Manager | 0 | Read, Write, Create, Submit, Cancel, Amend, Delete | Report, Export, Print, Email, Share | — |
| Fuel Exception Case (submittable) | Fleet Project Manager | 0 | Read, Write, Create | Report | — |
| Fuel Exception Case (submittable) | Fleet Supervisor | 0 | Read, Write, Create | Report | — |
| Fuel Exception Case (submittable) | Internal Auditor | 0 | Read | Report, Export | — |
| Fuel Exception Case (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Amend, Delete | Report, Export, Print, Email, Share | — |
| Fuel Platform | Finance Manager | 0 | Read | — | — |
| Fuel Platform | Fleet Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Fuel Platform | Fleet Project Manager | 0 | Read, Write, Create | Report | — |
| Fuel Platform | Fleet Supervisor | 0 | Read, Write, Create | Report | — |
| Fuel Platform | Internal Auditor | 0 | Read | Report, Export | — |
| Fuel Platform | System Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Fuel Quota (submittable) | Finance Manager | 0 | Read | Report, Export | — |
| Fuel Quota (submittable) | Fleet Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Fuel Quota (submittable) | Fleet Project Manager | 0 | Read, Write, Create, Submit | Report | — |
| Fuel Quota (submittable) | Fleet Supervisor | 0 | Read, Write, Create | Report | — |
| Fuel Quota (submittable) | Internal Auditor | 0 | Read | Report, Export | — |
| Fuel Quota (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Fuel Request (submittable) | Finance Manager | 0 | Read | Report, Export | — |
| Fuel Request (submittable) | Fleet Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Fuel Request (submittable) | Fleet Project Manager | 0 | Read, Write, Create, Submit | Report | — |
| Fuel Request (submittable) | Fleet Supervisor | 0 | Read, Write, Create | Report | — |
| Fuel Request (submittable) | Internal Auditor | 0 | Read | Report, Export | — |
| Fuel Request (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Movement Cost Recovery (submittable) | Finance Manager | 0 | Read, Write | Report | — |
| Movement Cost Recovery (submittable) | Fleet Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Movement Cost Recovery (submittable) | Fleet Supervisor | 0 | Read, Write, Create, Submit | Report | — |
| Movement Cost Recovery (submittable) | Internal Auditor | 0 | Read | Report, Export | — |
| Movement Cost Recovery (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Movement Cost Transfer (submittable) | Finance Manager | 0 | Read, Write | Report | — |
| Movement Cost Transfer (submittable) | Fleet Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Movement Cost Transfer (submittable) | Fleet Project Manager | 0 | Read, Write, Create | Report | — |
| Movement Cost Transfer (submittable) | Internal Auditor | 0 | Read | Report | — |
| Movement Cost Transfer (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Passenger Manifest (submittable) | Finance Manager | 0 | Read | — | — |
| Passenger Manifest (submittable) | Fleet Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Passenger Manifest (submittable) | Fleet Project Manager | 0 | Read, Write, Create, Submit | — | — |
| Passenger Manifest (submittable) | Fleet Supervisor | 0 | Read, Write, Create | — | — |
| Passenger Manifest (submittable) | Internal Auditor | 0 | Read | Report, Export | — |
| Passenger Manifest (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Rental Accrual Ledger | Finance Manager | 0 | Read | Report, Export | — |
| Rental Accrual Ledger | Fleet Manager | 0 | Read | Report, Export | — |
| Rental Accrual Ledger | Internal Auditor | 0 | Read | Report, Export | — |
| Rental Accrual Ledger | System Manager | 0 | Read | Report, Export | — |
| Rental Office | Finance Manager | 0 | Read | — | — |
| Rental Office | Fleet Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Rental Office | Fleet Project Manager | 0 | Read, Write, Create | Report | — |
| Rental Office | Fleet Supervisor | 0 | Read, Write, Create | Report | — |
| Rental Office | Internal Auditor | 0 | Read | Report, Export | — |
| Rental Office | System Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Rental Settlement (submittable) | Finance Manager | 0 | Read, Write | Report | — |
| Rental Settlement (submittable) | Fleet Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Rental Settlement (submittable) | Fleet Project Manager | 0 | Read, Write, Create | Report | — |
| Rental Settlement (submittable) | Internal Auditor | 0 | Read | Report | — |
| Rental Settlement (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Rental Settlement (submittable) | Accommodation Manager | 1 | Read, Write | — | — |
| Rental Settlement (submittable) | Finance Manager | 1 | Read, Write | — | — |
| Rental Settlement (submittable) | System Manager | 1 | Read, Write | — | — |
| Rental Vehicle Movement (submittable) | Finance Manager | 0 | Read | Report | — |
| Rental Vehicle Movement (submittable) | Fleet Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Rental Vehicle Movement (submittable) | Fleet Project Manager | 0 | Read, Write, Create | Report | — |
| Rental Vehicle Movement (submittable) | Fleet Supervisor | 0 | Read, Write, Create | Report | — |
| Rental Vehicle Movement (submittable) | Internal Auditor | 0 | Read | Report | — |
| Rental Vehicle Movement (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Route Assignment | Finance Manager | 0 | Read | — | — |
| Route Assignment | Fleet Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Route Assignment | Fleet Project Manager | 0 | Read, Write, Create | Report | — |
| Route Assignment | Fleet Supervisor | 0 | Read | Report | — |
| Route Assignment | Internal Auditor | 0 | Read | Report, Export | — |
| Route Assignment | System Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Route Plan (submittable) | Finance Manager | 0 | Read | — | — |
| Route Plan (submittable) | Fleet Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Route Plan (submittable) | Fleet Project Manager | 0 | Read, Write, Create, Submit | — | — |
| Route Plan (submittable) | Fleet Supervisor | 0 | Read, Write, Create | — | — |
| Route Plan (submittable) | Internal Auditor | 0 | Read | Report, Export | — |
| Route Plan (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Route Plan (submittable) | Finance Manager | 1 | Read | — | — |
| Route Plan (submittable) | Fleet Manager | 1 | Read | — | — |
| Route Plan (submittable) | Fleet Project Manager | 1 | Read | — | — |
| Route Plan (submittable) | Fleet Supervisor | 1 | Read | — | — |
| Route Plan (submittable) | Internal Auditor | 1 | Read | — | — |
| Route Plan (submittable) | System Manager | 1 | Read | — | — |
| Route Template | Fleet Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Route Template | Fleet Project Manager | 0 | Read, Write, Create | Report | — |
| Route Template | Fleet Supervisor | 0 | Read | Report | — |
| Route Template | System Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Salis Driver | Driver | 0 | Read | — | Own records only |
| Salis Driver | Finance Manager | 0 | Read | Report, Export, Print | — |
| Salis Driver | Fleet Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Salis Driver | Fleet Project Manager | 0 | Read, Write, Create | Report, Export, Print, Email, Share | — |
| Salis Driver | Fleet Supervisor | 0 | Read, Write, Create | Report, Export, Print, Email, Share | — |
| Salis Driver | Government Relations Officer | 0 | Read | Report, Export | — |
| Salis Driver | Internal Auditor | 0 | Read | Report, Export | — |
| Salis Driver | System Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Salis Driver | Fleet Manager | 1 | Read, Write | — | — |
| Salis Driver | System Manager | 1 | Read, Write | — | — |
| Salis Payment Request (submittable) | Finance Manager | 0 | Read, Write, Submit, Cancel | Report | — |
| Salis Payment Request (submittable) | Fleet Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Salis Payment Request (submittable) | Fleet Project Manager | 0 | Read, Write, Create | Report | — |
| Salis Payment Request (submittable) | Fleet Supervisor | 0 | Read, Write, Create | Report | — |
| Salis Payment Request (submittable) | Internal Auditor | 0 | Read | Report, Export | — |
| Salis Payment Request (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Salis Vehicle | Finance Manager | 0 | Read | Report | — |
| Salis Vehicle | Fleet Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Salis Vehicle | Fleet Project Manager | 0 | Read, Write, Create | Report | — |
| Salis Vehicle | Fleet Supervisor | 0 | Read, Write, Create | Report | — |
| Salis Vehicle | Government Relations Officer | 0 | Read | Report, Export | — |
| Salis Vehicle | Internal Auditor | 0 | Read | Report, Export | — |
| Salis Vehicle | System Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Transport Request (submittable) | Finance Manager | 0 | Read | — | — |
| Transport Request (submittable) | Fleet Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Transport Request (submittable) | Fleet Project Manager | 0 | Read, Write, Create, Submit | Report | — |
| Transport Request (submittable) | Fleet Supervisor | 0 | Read, Write, Create, Submit | — | — |
| Transport Request (submittable) | Internal Auditor | 0 | Read | Report, Export | — |
| Transport Request (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Transport Request (submittable) | Fleet Manager | 1 | Read, Write | — | — |
| Transport Request (submittable) | Fleet Project Manager | 1 | Read, Write | — | — |
| Transport Request (submittable) | Fleet Supervisor | 1 | Read, Write | — | — |
| Transport Request (submittable) | System Manager | 1 | Read, Write | — | — |
| Transport Trip Rating | Fleet Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Transport Trip Rating | Fleet Supervisor | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Transport Trip Rating | System Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Trip Boarding Ledger | Fleet Manager | 0 | Read | Report, Export | — |
| Trip Boarding Ledger | Internal Auditor | 0 | Read | Report, Export | — |
| Trip Boarding Ledger | System Manager | 0 | Read | Report, Export | — |
| Trip Fulfilment Ledger | Finance Manager | 0 | Read | Report, Export | — |
| Trip Fulfilment Ledger | Fleet Manager | 0 | Read | Report, Export | — |
| Trip Fulfilment Ledger | Internal Auditor | 0 | Read | Report, Export | — |
| Trip Fulfilment Ledger | System Manager | 0 | Read | Report, Export | — |
| Trip Start Log (submittable) | Driver | 0 | Read, Write, Create, Submit | — | Own records only |
| Trip Start Log (submittable) | Finance Manager | 0 | Read | — | — |
| Trip Start Log (submittable) | Fleet Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Trip Start Log (submittable) | Fleet Project Manager | 0 | Read, Write, Create, Submit | — | — |
| Trip Start Log (submittable) | Fleet Supervisor | 0 | Read, Write, Create, Submit | — | — |
| Trip Start Log (submittable) | Internal Auditor | 0 | Read | Report, Export | — |
| Trip Start Log (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Vehicle Assignment (submittable) | Finance Manager | 0 | Read | Report | — |
| Vehicle Assignment (submittable) | Fleet Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Vehicle Assignment (submittable) | Fleet Project Manager | 0 | Read, Write, Create, Submit, Cancel, Amend | Report | — |
| Vehicle Assignment (submittable) | Fleet Supervisor | 0 | Read, Write, Create | Report | — |
| Vehicle Assignment (submittable) | Internal Auditor | 0 | Read | Report, Export | — |
| Vehicle Assignment (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Amend, Delete | Report, Export, Print, Email, Share | — |
| Vehicle Category | Finance Manager | 0 | Read | — | — |
| Vehicle Category | Fleet Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Vehicle Category | Fleet Project Manager | 0 | Read, Write, Create | Report | — |
| Vehicle Category | Fleet Supervisor | 0 | Read, Write, Create | Report | — |
| Vehicle Category | Internal Auditor | 0 | Read | Report, Export | — |
| Vehicle Category | System Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Vehicle Damage Write-Off (submittable) | Finance Manager | 0 | Read | Report, Export | — |
| Vehicle Damage Write-Off (submittable) | Fleet Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Vehicle Damage Write-Off (submittable) | Fleet Supervisor | 0 | Read, Write, Create, Submit | Report | — |
| Vehicle Damage Write-Off (submittable) | Internal Auditor | 0 | Read | Report, Export | — |
| Vehicle Damage Write-Off (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Vehicle Handover (submittable) | Finance Manager | 0 | Read | Report | — |
| Vehicle Handover (submittable) | Fleet Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Vehicle Handover (submittable) | Fleet Project Manager | 0 | Read, Write, Create, Submit, Cancel, Amend | Report | — |
| Vehicle Handover (submittable) | Fleet Supervisor | 0 | Read, Write, Create | Report | — |
| Vehicle Handover (submittable) | Internal Auditor | 0 | Read | Report, Export | — |
| Vehicle Handover (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Amend, Delete | Report, Export, Print, Email, Share | — |
| Vehicle Handover Checklist Template | Fleet Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Vehicle Handover Checklist Template | Fleet Project Manager | 0 | Read, Write, Create | Report | — |
| Vehicle Handover Checklist Template | Fleet Supervisor | 0 | Read | Report | — |
| Vehicle Handover Checklist Template | System Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Vehicle Incident (submittable) | Fleet Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Vehicle Incident (submittable) | Fleet Project Manager | 0 | Read, Write, Create | Report | — |
| Vehicle Incident (submittable) | Fleet Supervisor | 0 | Read, Write, Create | Report | — |
| Vehicle Incident (submittable) | Government Relations Officer | 0 | Read | Report, Export | — |
| Vehicle Incident (submittable) | Internal Auditor | 0 | Read | Report, Export | — |
| Vehicle Incident (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Vehicle Incident (submittable) | Fleet Manager | 1 | Read, Write | — | — |
| Vehicle Incident (submittable) | Fleet Project Manager | 1 | Read, Write | — | — |
| Vehicle Incident (submittable) | Fleet Supervisor | 1 | Read, Write | — | — |
| Vehicle Incident (submittable) | System Manager | 1 | Read, Write | — | — |
| Vehicle Suspension (submittable) | Finance Manager | 0 | Read | Report | — |
| Vehicle Suspension (submittable) | Fleet Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Vehicle Suspension (submittable) | Fleet Project Manager | 0 | Read, Write, Create, Submit, Cancel, Amend | Report | — |
| Vehicle Suspension (submittable) | Fleet Supervisor | 0 | Read, Write, Create | Report | — |
| Vehicle Suspension (submittable) | Internal Auditor | 0 | Read | Report, Export | — |
| Vehicle Suspension (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Amend, Delete | Report, Export, Print, Email, Share | — |
| Vehicle Utilisation Snapshot | Finance Manager | 0 | Read | Report, Export | — |
| Vehicle Utilisation Snapshot | Fleet Manager | 0 | Read | Report, Export | — |
| Vehicle Utilisation Snapshot | Internal Auditor | 0 | Read | Report, Export | — |
| Vehicle Utilisation Snapshot | System Manager | 0 | Read | Report, Export | — |
| Wash Platform | Finance Manager | 0 | Read | — | — |
| Wash Platform | Fleet Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Wash Platform | Fleet Project Manager | 0 | Read, Write, Create | Report | — |
| Wash Platform | Fleet Supervisor | 0 | Read, Write, Create | Report | — |
| Wash Platform | Internal Auditor | 0 | Read | Report, Export | — |
| Wash Platform | System Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Wash Request (submittable) | Finance Manager | 0 | Read | Report | — |
| Wash Request (submittable) | Fleet Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Wash Request (submittable) | Fleet Project Manager | 0 | Read, Write, Create, Submit | Report | — |
| Wash Request (submittable) | Fleet Supervisor | 0 | Read, Write, Create | Report | — |
| Wash Request (submittable) | Internal Auditor | 0 | Read | Report, Export | — |
| Wash Request (submittable) | System Manager | 0 | Read, Write, Create, Submit, Cancel, Delete | Report, Export, Print, Email, Share | — |
| Work Shift | Finance Manager | 0 | Read | — | — |
| Work Shift | Fleet Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |
| Work Shift | Fleet Project Manager | 0 | Read, Write, Create | Report | — |
| Work Shift | Fleet Supervisor | 0 | Read | Report | — |
| Work Shift | Internal Auditor | 0 | Read | Report, Export | — |
| Work Shift | System Manager | 0 | Read, Write, Create, Delete | Report, Export, Print, Email, Share | — |

No DocPerm row of its own: Dispatch Trip Assigned Request (child table), Driver Attendance Image (child table), Passenger Manifest Item (child table), Rental Settlement Item (child table), Route Stop (child table), Salis Vehicle Compliance (child table), Transport Request Ad Hoc Passenger (child table), Transport Request Worker (child table), Trip Boarding Event (child table), Trip Boarding State (child table), Trip Stop Progress (child table), Vehicle Handover Checklist Template Item (child table), Vehicle Handover Item (child table), Work Shift Day (child table).
