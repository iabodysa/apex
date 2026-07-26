# Copyright (c) 2026, AFMCO and contributors
"""Guards for the default Issue SLA's Holiday List precondition.

``Service Level Agreement.holiday_list`` is a REQUIRED core ERPNext Link, and no
app provisions a Holiday List on a fresh site — not the ERPNext setup wizard, not
hrms — so ``_seed_sla`` bailed and the SLA the driver portal assumes was absent on
every new deployment. The seeder now provisions an empty fallback list, but only
when the site has none, which is what makes it safe to re-run on a configured site.

Site-free: ``salis_issue_seed.frappe`` is replaced by an in-memory recorder. This
proves the precondition and the write ORDER; a genuinely-new-site run is still owed.
"""

import unittest
from unittest.mock import patch

from apex.apex_core.setup.seeders import salis_issue_seed as issue_seed

_SLA = "Service Level Agreement"
_HOLIDAY_LIST = "Holiday List"
# Which field a stub insert copies into ``name``, mirroring each DocType's autoname.
_AUTONAME = {_HOLIDAY_LIST: "holiday_list_name", _SLA: "service_level"}
_FRESH_SITE_DOCTYPES = (_SLA, "Issue", "Issue Priority", "Support Settings", _HOLIDAY_LIST)


class _FakeDoc:
    def __init__(self, doctype, store):
        self.doctype = doctype
        self.name = None
        self.tables = {}
        self._store = store

    def append(self, table, row):
        self.tables.setdefault(table, []).append(row)

    def insert(self, **_kwargs):
        self.name = getattr(self, _AUTONAME[self.doctype])
        self._store.setdefault(self.doctype, {})[self.name] = self


class _FakeDB:
    def __init__(self, doctypes, records, singles):
        self.doctypes = set(doctypes)
        self.records = {dt: dict(rows) for dt, rows in records.items()}
        self.singles = dict(singles)

    def exists(self, doctype, key):
        if doctype == "DocType":
            return key in self.doctypes
        rows = self.records.get(doctype, {})
        if isinstance(key, dict):
            for field, wanted in key.items():
                if field == "name":
                    if wanted in rows:
                        return True
                elif any(self._field(row, field) == wanted for row in rows.values()):
                    return True
            return False
        return key in rows

    def get_value(self, doctype, key, field):
        rows = self.records.get(doctype, {})
        if key == {} or key is None:
            if not rows:
                return None
            first = next(iter(rows))
            return first if field == "name" else self._field(rows[first], field)
        row = rows.get(key)
        return None if row is None else self._field(row, field)

    def get_single_value(self, doctype, field):
        return self.singles.get((doctype, field))

    def set_single_value(self, doctype, field, value):
        self.singles[(doctype, field)] = value

    @staticmethod
    def _field(row, field):
        return row.get(field) if isinstance(row, dict) else getattr(row, field, None)


class _FakeDefaults:
    def __init__(self, values):
        self._values = values

    def get_global_default(self, key):
        return self._values.get(key)


class _NullLogger:
    def info(self, _message):
        return None


class _FakeFrappe:
    def __init__(self, doctypes=_FRESH_SITE_DOCTYPES, records=None, globals_=None, singles=None):
        # Issue Priority masters are always present: the shipped order seeds them in
        # the step immediately before this one.
        seeded = {"Issue Priority": {name: {} for name in issue_seed._ISSUE_PRIORITIES}}
        seeded.update(records or {})
        self.db = _FakeDB(doctypes, seeded, singles or {})
        self.defaults = _FakeDefaults(globals_ or {})

    def new_doc(self, doctype):
        return _FakeDoc(doctype, self.db.records)

    def logger(self):
        return _NullLogger()

    def created(self, doctype):
        return list(self.db.records.get(doctype, {}))


def _seed(stub):
    with patch.object(issue_seed, "frappe", stub):
        issue_seed._seed_sla()
    return stub


class TestFreshSiteGetsTheSla(unittest.TestCase):
    def test_sla_is_created_although_the_site_has_no_holiday_list(self):
        stub = _seed(_FakeFrappe())
        self.assertEqual(stub.created(_SLA), [issue_seed._SLA_NAME])

    def test_the_fallback_holiday_list_is_provisioned_and_linked(self):
        stub = _seed(_FakeFrappe())
        self.assertEqual(stub.created(_HOLIDAY_LIST), [issue_seed._SLA_HOLIDAY_LIST])
        sla = stub.db.records[_SLA][issue_seed._SLA_NAME]
        self.assertEqual(sla.holiday_list, issue_seed._SLA_HOLIDAY_LIST)

    def test_the_fallback_list_carries_no_holidays(self):
        """Zero holiday rows is the point: the SLA clock reads only those rows, so an
        empty list is the 24x7 window the SLA declares."""
        stub = _seed(_FakeFrappe())
        holiday_list = stub.db.records[_HOLIDAY_LIST][issue_seed._SLA_HOLIDAY_LIST]
        self.assertEqual(holiday_list.tables.get("holidays", []), [])
        self.assertLess(holiday_list.from_date, holiday_list.to_date)

    def test_the_sla_is_the_default_and_covers_every_priority(self):
        stub = _seed(_FakeFrappe())
        sla = stub.db.records[_SLA][issue_seed._SLA_NAME]
        self.assertEqual(sla.default_service_level_agreement, 1)
        self.assertEqual(
            [row["priority"] for row in sla.tables["priorities"]],
            [priority for priority, _r, _x, _d in issue_seed._SLA_PRIORITIES],
        )
        self.assertEqual(len(sla.tables["support_and_resolution"]), len(issue_seed._WORKDAYS))


class TestConfiguredSiteIsUntouched(unittest.TestCase):
    def test_an_existing_holiday_list_is_reused_and_none_is_created(self):
        stub = _seed(_FakeFrappe(records={_HOLIDAY_LIST: {"Saudi Holidays 2026": {}}}))
        self.assertEqual(stub.created(_HOLIDAY_LIST), ["Saudi Holidays 2026"])
        self.assertEqual(
            stub.db.records[_SLA][issue_seed._SLA_NAME].holiday_list, "Saudi Holidays 2026"
        )

    def test_the_company_default_still_wins(self):
        stub = _seed(
            _FakeFrappe(
                records={
                    "Company": {"AFMCO": {"default_holiday_list": "Company Calendar"}},
                    _HOLIDAY_LIST: {"Company Calendar": {}, "Stray List": {}},
                },
                globals_={"company": "AFMCO"},
            )
        )
        self.assertEqual(
            stub.db.records[_SLA][issue_seed._SLA_NAME].holiday_list, "Company Calendar"
        )

    def test_a_second_run_creates_nothing(self):
        stub = _seed(_FakeFrappe())
        before = (stub.created(_SLA), stub.created(_HOLIDAY_LIST))
        _seed(stub)
        self.assertEqual((stub.created(_SLA), stub.created(_HOLIDAY_LIST)), before)

    def test_a_lone_leftover_fallback_list_is_reused_not_duplicated(self):
        """The SLA deleted by an admin, our list left behind: the next migrate must
        rebuild the SLA on the same list rather than pile up a second one."""
        stub = _seed(
            _FakeFrappe(records={_HOLIDAY_LIST: {issue_seed._SLA_HOLIDAY_LIST: {}}})
        )
        self.assertEqual(stub.created(_HOLIDAY_LIST), [issue_seed._SLA_HOLIDAY_LIST])
        self.assertEqual(stub.created(_SLA), [issue_seed._SLA_NAME])


class TestMissingPrerequisitesStaySkips(unittest.TestCase):
    def test_no_holiday_list_doctype_means_skip_not_raise(self):
        stub = _seed(_FakeFrappe(doctypes=(_SLA, "Issue", "Issue Priority")))
        self.assertEqual(stub.created(_SLA), [])
        self.assertEqual(stub.created(_HOLIDAY_LIST), [])

    def test_no_issue_doctype_means_skip(self):
        stub = _seed(_FakeFrappe(doctypes=(_SLA, _HOLIDAY_LIST)))
        self.assertEqual(stub.created(_SLA), [])
        self.assertEqual(stub.created(_HOLIDAY_LIST), [])


if __name__ == "__main__":
    unittest.main()
