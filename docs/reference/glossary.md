# Apex Business Glossary

This glossary explains the names used in Apex. It uses the shipped English
source terms while clarifying their practical business meaning.

## Cross-cutting terms

| Term | Meaning in Apex |
|------|-----------------|
| **Apex** | One Frappe application containing Habitat, Salis, Apex Core, and Logistay. |
| **Frappe site** | One deployed Frappe tenant. This is not the Habitat **Site** master. |
| **Role** | A named permission set such as Fleet Supervisor or Accommodation Manager. A role does not by itself remove project or building row scope. |
| **Project** | The ERPNext project used for operational ownership and fleet row scope. |
| **Cost Center** | The ERPNext accounting dimension used to attribute cost to a company unit or project. |
| **Supplier** | The ERPNext party used for landlords, rental offices, telecom operators, and other vendors where the process requires it. |
| **System-written** | Created or maintained by controllers or scheduled jobs. Operators read the record but do not enter it manually. |
| **Operational memo** | A non-GL operational amount retained for allocation, reconciliation, or reporting. It is not an accounting posting. |
| **Ledger** | An append-oriented operational trace. In Apex, a ledger name does not imply an ERPNext General Ledger entry. |
| **Snapshot** | A point-in-time record kept because later master-data changes would make the old state impossible to reconstruct exactly. |
| **Assignment queue** | The open native ToDo assignments a watcher job places on a source document for the role that can act, and closes again when the condition clears. |
| **Salary Deduction Policy** | The shared switch and per-type rules that gate automated wage-recovery installments. The shipped rules are inactive until configured. |

## Habitat terms

| Term | Meaning in Apex |
|------|-----------------|
| **Habitat** | Accommodation and facility operations: housing, custody, cleaning, safety, maintenance, leases, utilities, and operational cost history. |
| **Site** | A location master grouping accommodation properties by city and district. Do not confuse it with a Frappe site. |
| **Building** | The operational property or leased unit. One record may represent a whole building, villa, compound block, or apartment. |
| **Room** | A room inside a Building. |
| **Bed** | The individual capacity unit assigned to a resident. |
| **Resident** | The Employee or Temporary Worker occupying accommodation. It is a business role, not a separate master. |
| **Temporary Worker** | A passport-based worker record used before the permanent Employee record exists. The daily link process later connects the two. |
| **Housing Assignment** | The active placement of a resident into a Building, Room, and Bed for a defined stay. |
| **Housing Checkout** | The controlled end of a Housing Assignment, including bed release, custody clearance, and condition evidence. |
| **Resident Request** | A housing issue or service request raised by a worker or supervisor, including maintenance, safety, cleaning, utilities, complaints, and other needs. |
| **Custody** | Company property entrusted to a worker, project, or facility supervisor. The word means asset responsibility, not legal guardianship. |
| **Custody Article** | The catalog item that can be issued and returned, such as linen or equipment. |
| **Custody Issue** | The submitted handover of custody articles to a responsible party. |
| **Custody Return** | The submitted receipt of articles against an earlier Custody Issue. |
| **Custody Damage Assessment** | The documented condition and replacement-cost review for damaged returned articles. |
| **Facility Asset** | A building-level asset such as a camera, recorder, router, switch, or generator. Its operational custody belongs to a supervisor rather than an Employee. |
| **Safety Round** | The current periodic building safety record. It groups Safety Task Executions for one cadence and supersedes Safety Inspection Report. |
| **Scheduled Task Instance** | One due execution generated from a scheduled task assignment and catalog item. |
| **Maintenance Request** | The reported maintenance need or ticket. |
| **Maintenance Work Order** | The formal execution record derived from a Maintenance Request. |
| **Accommodation Ledger** | System-written daily accommodation cost allocation by resident, building, assignment, and cost type. It is an Operational Memo and posts no GL entry. |
| **Accommodation Stock Ledger** | System-written signed quantity movement for custody articles and maintenance materials by building and custodian. |
| **Occupancy Snapshot** | Daily building capacity, occupancy, room-state, and unused-capacity cost history. |

## Salis terms

| Term | Meaning in Apex |
|------|-----------------|
| **Salis** | Movement and fleet operations: drivers, vehicles, workforce transport, dispatch, boarding, fuel, rentals, compliance, and recoveries. |
| **Salis Driver** | The fleet driver master. It links driver identity, project, supervisor, vehicle, licence, and portal access without replacing Employee. |
| **Salis Vehicle** | The fleet vehicle master for plate, ownership, project, status, and compliance. |
| **Vehicle Assignment** | The dated assignment of a vehicle to a driver and project. |
| **Transport Request** | The demand for a shuttle, inter-city relocation, or administrative trip. It describes who needs movement and why. |
| **Route Plan** | The planned vehicle, driver, shift, supervisor decision, and ordered stops for transport. |
| **Dispatch Trip** | The execution record for a planned movement, including status, odometer, boarding state, and current driver position. |
| **Driver Attendance** | The driver's daily check-in and check-out record with optional photographic evidence. |
| **Fuel Request** | One request model for Standard fuel, Top-up, or fuel-chip action. Request type selects the behavior. |
| **Fuel Quota** | The approved monthly litre allowance for a vehicle and driver on a project. |
| **Fuel Consumption Ledger** | System-written fuel consumption from Fuel Daily Log and completed Fuel Request sources. It posts no GL entry. |
| **Vehicle Suspension** | A vehicle stop event, such as maintenance downtime. It describes operational availability. |
| **Vehicle Incident** | An accident or theft event with location, report number, and evidence. It is distinct from a vehicle stop or damage disposition. |
| **Rental Office** | The external supplier location that provides rented vehicles. |
| **Rental Vehicle Movement** | A submitted Receipt or Return. The latest movement determines whether a rented vehicle is currently in service. |
| **Rental Accrual Ledger** | One system-written daily rental-cost memo per received rented vehicle. It posts no GL entry. |
| **Rental Settlement** | The monthly comparison of a rental office claim with accrued vehicle days before a finance request is considered. |
| **Movement Cost Recovery** | The movement-domain review and authorization of a loss. It does not post a payment, payroll deduction, or General Ledger entry. |

## Logistay terms

| Term | Meaning in Apex |
|------|-----------------|
| **Logistay** | Workforce-arrival and telecom operations, with its own Logistay workspace; telecom records are also reached through Telecom Control and Custody navigation. |
| **Telecom Contract** | One supplier service agreement that owns SIM cards and provides recurring billing terms. |
| **SIM Card** | The managed telecom asset. Its mobile number can be corrected on the same record; a number change does not create a second SIM record. |
| **SIM Custody Assignment** | One immutable SIM action: Assign, Transfer, Return, Suspend, or Reactivate. The latest submitted action projects the SIM's current state. |
| **SIM transfer** | A Transfer action inside SIM Custody Assignment. Apex does not use a separate SIM Transfer Request DocType. |
| **Custodian** | The current Employee or Project responsible for a SIM. Unassigned means no current custodian. |
| **Telecom Billing Document** | The child reference connecting a billing period to the draft Material Request or Payment Entry raised from a Telecom Contract. |

## Related references

- [Modules, workspaces, and routes](routes-workspaces.md)
- [Scheduled automation](automation.md)
- [Troubleshooting](troubleshooting.md)
