# Copyright (c) 2026, AFMCO and contributors
"""Schema-reference integrity: code/metadata must not point at a nonexistent target.

Guards the class of bug fixed in 1.54.18 (workshop_overstay_days was read in code
but missing from the DocType). Fails CI the moment a hook/card method path, a
settings field, or a fetch_from source stops resolving.
"""

import glob
import json
import re

import frappe
from frappe.tests.utils import FrappeTestCase

APP = frappe.get_app_path("apex")


def _collect(value, out):
    if isinstance(value, str):
        if value.startswith("apex."):
            out.add(value)
    elif isinstance(value, dict):
        for v in value.values():
            _collect(v, out)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _collect(v, out)


class TestSchemaIntegrity(FrappeTestCase):
    def test_method_paths_resolve(self):
        import apex.hooks as hooks

        paths = set()
        for v in vars(hooks).values():
            _collect(v, paths)
        for j in glob.glob(f"{APP}/**/number_card/*/*.json", recursive=True):
            d = json.load(open(j, encoding="utf-8"))
            if d.get("type") == "Custom" and d.get("method"):
                paths.add(d["method"])
        bad = []
        for p in sorted(paths):
            try:
                frappe.get_attr(p)
            except Exception:
                bad.append(p)
        self.assertEqual(bad, [], f"hook/card method paths that do not resolve: {bad}")

    def test_settings_fields_exist(self):
        # [#dt2pre]
        pi = re.compile(r'(?:_settings_int|get_salis_int|get_salis_float)\(\s*["\']([a-z_0-9]+)["\']')
        ps = re.compile(r'get_single_value\(\s*["\']([A-Za-z ]+Settings)["\']\s*,\s*["\']([a-z_0-9]+)["\']')
        missing = []
        for f in glob.glob(f"{APP}/**/*.py", recursive=True):
            if "/tests/" in f:
                continue
            t = open(f, encoding="utf-8").read()
            for m in pi.finditer(t):
                if not frappe.get_meta("Salis Settings").get_field(m.group(1)):
                    missing.append(f"Salis Settings.{m.group(1)}")
            for m in ps.finditer(t):
                dt, fld = m.group(1), m.group(2)
                if frappe.db.exists("DocType", dt) and not frappe.get_meta(dt).get_field(fld):
                    missing.append(f"{dt}.{fld}")
        self.assertEqual(sorted(set(missing)), [], f"settings fields read in code but missing from the DocType: {sorted(set(missing))}")

    def test_fetch_from_sources_exist(self):
        bad = []
        for j in glob.glob(f"{APP}/**/doctype/*/*.json", recursive=True):
            try:
                d = json.load(open(j, encoding="utf-8"))
            except Exception:
                continue
            if d.get("doctype") != "DocType":
                continue
            links = {
                f["fieldname"]: f.get("options")
                for f in d.get("fields", [])
                if f.get("fieldtype") in ("Link", "Dynamic Link") and f.get("fieldname")
            }
            for f in d.get("fields", []):
                ff = f.get("fetch_from")
                if not ff or "." not in ff:
                    continue
                link, src = ff.split(".", 1)
                target = links.get(link)
                if target and "." not in src and frappe.db.exists("DocType", target) and not frappe.get_meta(target).get_field(src):
                    bad.append(f"{d['name']}.{f.get('fieldname')} ({ff})")
        self.assertEqual(bad, [], f"fetch_from sources that do not exist: {bad}")

    def test_workspace_refs_resolve(self):
        kind = {"DocType": "DocType", "Report": "Report", "Page": "Page"}
        bad = []
        for j in glob.glob(f"{APP}/**/workspace/*/*.json", recursive=True):
            d = json.load(open(j, encoding="utf-8"))
            for s in d.get("shortcuts", []):
                m = kind.get(s.get("type"))
                if m and s.get("link_to") and not frappe.db.exists(m, s["link_to"]):
                    bad.append(f"{d['name']} shortcut -> {s['type']} {s['link_to']}")
            for link in d.get("links", []):
                if link.get("type") == "Link" and link.get("link_type") == "DocType" and link.get("link_to") and not frappe.db.exists("DocType", link["link_to"]):
                    bad.append(f"{d['name']} link -> DocType {link['link_to']}")
            for c in d.get("charts", []):
                if c.get("chart_name") and not frappe.db.exists("Dashboard Chart", c["chart_name"]):
                    bad.append(f"{d['name']} chart -> {c['chart_name']}")
            for nc in d.get("number_cards", []):
                if nc.get("number_card_name") and not frappe.db.exists("Number Card", nc["number_card_name"]):
                    bad.append(f"{d['name']} number_card -> {nc['number_card_name']}")
        self.assertEqual(bad, [], f"workspace references that do not resolve: {bad}")

    def test_workspace_content_blocks_resolve(self):
        # [#m6btux]
        ref = {
            "chart": ("chart_name", "charts"),
            "number_card": ("number_card_name", "number_cards"),
            "shortcut": ("shortcut_name", "shortcuts"),
            "quick_list": ("quick_list_name", "quick_lists"),
            "card": ("card_name", "links"),
        }
        bad = []
        for j in glob.glob(f"{APP}/**/workspace/*/*.json", recursive=True):
            d = json.load(open(j, encoding="utf-8"))
            name = d["name"]
            declared = {
                "charts": {c.get("chart_name") for c in d.get("charts", [])},
                "number_cards": {c.get("number_card_name") for c in d.get("number_cards", [])},
                "shortcuts": {s.get("label") for s in d.get("shortcuts", [])},
                "quick_lists": {q.get("label") for q in d.get("quick_lists", [])},
                "links": {link.get("label") for link in d.get("links", []) if link.get("type") == "Card Break"},
            }
            for q in d.get("quick_lists", []):
                dt = q.get("document_type")
                if dt and not frappe.db.exists("DocType", dt):
                    bad.append(f"{name} quick_list -> DocType {dt} missing")
            try:
                blocks = json.loads(d.get("content") or "[]")
            except (ValueError, TypeError):
                bad.append(f"{name}: content is not valid JSON")
                continue
            for b in blocks:
                if not isinstance(b, dict):
                    continue
                spec = ref.get(b.get("type"))
                if not spec:
                    continue
                n = (b.get("data") or {}).get(spec[0])
                if n and n not in declared[spec[1]]:
                    bad.append(f"{name} content {b['type']} -> {n} (not in {spec[1]}[])")
        self.assertEqual(bad, [], f"workspace content blocks that do not resolve: {bad}")

    def test_dashboard_chart_refs_resolve(self):
        bad = []
        for j in glob.glob(f"{APP}/**/dashboard_chart/*/*.json", recursive=True):
            d = json.load(open(j, encoding="utf-8"))
            dt = d.get("document_type")
            if dt and not frappe.db.exists("DocType", dt):
                bad.append(f"{d['name']} document_type {dt} missing")
            elif dt and d.get("based_on") and "." not in d["based_on"] and not frappe.get_meta(dt).get_field(d["based_on"]):
                bad.append(f"{d['name']} based_on {dt}.{d['based_on']} missing")
        self.assertEqual(bad, [], f"dashboard chart references that do not resolve: {bad}")
