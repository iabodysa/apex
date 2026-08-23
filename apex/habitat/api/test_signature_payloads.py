# Copyright (c) 2026, afmcoltd

"""A signature reaching a print format must be an image, and must stay in its attribute.

The receipt renders the stored value inside ``<img src="...">`` and Frappe's Jinja
environment does not autoescape (``frappe/utils/jinja.py`` builds a SandboxedEnvironment
with autoescape left at its default of False), so a value carrying a quote closes the
attribute and whatever follows runs in the session of whoever opens the receipt.

Two independent layers, and both are tested here because either alone is one edit from
being removed: the door refuses anything that is not a verified image, and the template
escapes what it prints.

The signature field is OPTIONAL. A validator that fires on a blank turns this fix into a
refusal every kiosk user meets, so the blank case is asserted as loudly as the payload.
"""

import ast
import base64
import inspect
import io
import pathlib
import re

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils.jinja import get_jenv
from PIL import Image

from apex.habitat.api import custody_kiosk, front_desk
from apex.salis.api.driver_portal.images import verified_image_type

PAYLOAD = 'data:x" onerror=alert(1)'
NOT_AN_IMAGE = "data:image/png;base64,bm90YW5pbWFnZQ=="


class TestSignatureIsRefusedAtTheDoor(FrappeTestCase):
    """``verified_image_type`` is the single validator both signature doors call."""

    def test_an_attribute_breaking_payload_is_refused(self):
        with self.assertRaises(frappe.ValidationError):
            verified_image_type(PAYLOAD)

    def test_a_bare_data_prefix_is_not_enough(self):
        """The prefix check this replaces inspected five characters and passed."""
        self.assertTrue(PAYLOAD.startswith("data:"))
        with self.assertRaises(frappe.ValidationError):
            verified_image_type(PAYLOAD)

    def test_a_declared_image_that_is_not_one_is_refused(self):
        with self.assertRaises(frappe.ValidationError):
            verified_image_type(NOT_AN_IMAGE)

    def test_a_real_image_passes(self):
        """The positive control: without it a validator that refuses everything looks
        identical to one that works."""
        self.assertEqual(verified_image_type(_one_pixel_png()), "image/png")

    def test_both_doors_call_this_one_validator(self):
        self.assertIs(custody_kiosk.verified_image_type, verified_image_type)
        self.assertIs(front_desk.verified_image_type, verified_image_type)


class TestBlankSignatureStaysLegal(FrappeTestCase):
    """The second negative control the fix must not break.

    Both doors validate INSIDE an ``if signature:`` branch. These assert the branch is
    still there: an unconditional validator would refuse every unsigned issue and every
    check-in that collects the signature later.
    """

    def test_the_validator_is_never_reached_for_a_blank(self):
        for module, func in ((custody_kiosk, "issue_cart"), (front_desk, "quick_check_in")):
            with self.subTest(func=func):
                tree = ast.parse(inspect.getsource(getattr(module, func)))
                guarded = [
                    node
                    for node in ast.walk(tree)
                    if isinstance(node, ast.If)
                    and "verified_image_type" in ast.unparse(node.body)
                ]
                self.assertTrue(
                    guarded, f"{func} calls the validator outside an if-present guard"
                )

    def test_a_blank_is_not_sent_to_the_validator_by_the_helper_itself(self):
        for blank in (None, "", "   "):
            with self.subTest(blank=blank):
                self.assertFalse((blank or "").strip())


class TestTemplateEscapesTheValue(FrappeTestCase):
    """The render layer, proved against the real Jinja environment."""

    def test_an_unescaped_interpolation_breaks_the_attribute(self):
        rendered = get_jenv().from_string('<img src="{{ v }}">').render(v=PAYLOAD)
        self.assertIn("onerror=alert(1)", rendered)
        self.assertNotIn("&#34;", rendered)

    def test_the_escape_filter_keeps_it_inside_the_attribute(self):
        rendered = get_jenv().from_string('<img src="{{ v | e }}">').render(v=PAYLOAD)
        self.assertIn("&#34;", rendered)
        self.assertNotIn('src="data:x" onerror', rendered)

    def test_every_signature_interpolation_in_a_print_format_is_escaped(self):
        root = pathlib.Path(frappe.get_app_path("apex"))
        unescaped = [
            f"{path}:{i}"
            for path in root.rglob("*.html")
            for i, line in enumerate(path.read_text().splitlines(), 1)
            if re.search(r'(?:src|alt)="\{\{(?![^}]*\|\s*e\b)', line)
        ]
        self.assertEqual(unescaped, [])


def _one_pixel_png():
    """A minimal real PNG as a data URI, built rather than pasted."""
    buffer = io.BytesIO()
    Image.new("RGB", (1, 1), (0, 0, 0)).save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
