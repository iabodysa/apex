# Copyright (c) 2026, afmcoltd
"""Coverage for the token-scoped portal image validator
(``apex.salis.api.driver_portal.images``).

Exercises every callable: ``verified_image_type`` (the public entry point),
``_has_exact_container_end`` (the trailing-bytes guard per format) and
``_invalid_photo`` (the raise helper every rejection routes through). Fixtures are
real PIL-encoded PNG/JPEG/WEBP bytes, base64-wrapped into the exact data URI shape
the driver portal upload endpoints send, so a passing case proves round-trip
correctness and not merely "no exception".
"""

from __future__ import annotations

import base64
from io import BytesIO

import frappe
from frappe.tests.utils import FrappeTestCase
from PIL import Image

from apex.salis.api.driver_portal import images


def _data_uri(image_format, size=(2, 2), color=(255, 0, 0), mime=None):
    """A base64 data URI wrapping a real PIL-encoded image of ``image_format``."""
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format=image_format)
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    mime = mime or {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}[image_format]
    return f"data:{mime};base64,{encoded}"


class TestVerifiedImageType(FrappeTestCase):
    """``verified_image_type`` proves the bytes support the declared type."""

    def setUp(self):
        frappe.set_user("Administrator")

    def test_valid_png_round_trips_to_its_declared_type(self):
        """A real PNG, correctly declared, is accepted and named."""
        self.assertEqual(images.verified_image_type(_data_uri("PNG")), "image/png")

    def test_valid_jpeg_round_trips_to_its_declared_type(self):
        """A real JPEG, correctly declared, is accepted and named."""
        self.assertEqual(images.verified_image_type(_data_uri("JPEG")), "image/jpeg")

    def test_valid_webp_round_trips_to_its_declared_type(self):
        """A real WEBP, correctly declared, is accepted and named."""
        self.assertEqual(images.verified_image_type(_data_uri("WEBP")), "image/webp")

    def test_non_image_bytes_declared_as_image_are_refused(self):
        """Plain bytes wearing an ``image/png`` declaration are refused: the
        declaration alone proves nothing, PIL must actually open the container."""
        fake = base64.b64encode(b"not an image, just text pretending to be one").decode("ascii")
        with self.assertRaises(frappe.ValidationError):
            images.verified_image_type(f"data:image/png;base64,{fake}")

    def test_unsupported_declared_mime_is_refused(self):
        """A data URI declaring a type outside the accepted set never matches the
        pattern at all, regardless of what the bytes are."""
        real_png = _data_uri("PNG")
        forged = real_png.replace("data:image/png", "data:image/gif")
        with self.assertRaises(frappe.ValidationError):
            images.verified_image_type(forged)

    def test_non_string_payload_is_refused(self):
        """A caller that hands over anything but a string is refused outright."""
        with self.assertRaises(frappe.ValidationError):
            images.verified_image_type(None)
        with self.assertRaises(frappe.ValidationError):
            images.verified_image_type(b"data:image/png;base64,AAAA")

    def test_malformed_base64_is_refused(self):
        """A payload that is not exact, validate-clean base64 is refused before
        any image decoding is attempted."""
        with self.assertRaises(frappe.ValidationError):
            images.verified_image_type("data:image/png;base64,not-base64-!!!")

    def test_oversized_payload_is_refused(self):
        """A real, otherwise-valid image is refused once it crosses the caller's
        own byte ceiling — proved cheaply with a tiny image and a tiny ceiling
        rather than manufacturing a multi-megabyte fixture."""
        uri = _data_uri("PNG", size=(20, 20))
        with self.assertRaises(frappe.ValidationError):
            images.verified_image_type(uri, max_bytes=20)

    def test_default_ceiling_is_five_megabytes(self):
        """The module's own published ceiling is exactly 5 MiB."""
        self.assertEqual(images.MAX_IMAGE_BYTES, 5 * 1024 * 1024)

    def test_oversized_dimension_is_refused(self):
        """A width past the module's ceiling is refused even though the file
        itself stays tiny (a 1px-tall strip)."""
        uri = _data_uri("PNG", size=(images.MAX_IMAGE_WIDTH + 1, 1))
        with self.assertRaises(frappe.ValidationError):
            images.verified_image_type(uri)

    def test_expected_type_pins_the_accepted_declaration(self):
        """``expected_type`` refuses a correctly-formed image whose declared type
        does not match what the caller already knows it must be (the driver door
        derives the expected type from the filename)."""
        jpeg_uri = _data_uri("JPEG")
        with self.assertRaises(frappe.ValidationError):
            images.verified_image_type(jpeg_uri, expected_type="image/png")
        self.assertEqual(
            images.verified_image_type(jpeg_uri, expected_type="image/jpeg"), "image/jpeg"
        )

    def test_declared_type_disagreeing_with_container_is_refused(self):
        """A real JPEG re-wrapped with a ``image/png`` declaration fails: the
        container format PIL detects must agree with what was declared."""
        buf = BytesIO()
        Image.new("RGB", (4, 4)).save(buf, format="JPEG")
        encoded = base64.b64encode(buf.getvalue()).decode("ascii")
        with self.assertRaises(frappe.ValidationError):
            images.verified_image_type(f"data:image/png;base64,{encoded}")

    def test_trailing_bytes_after_a_valid_container_are_refused(self):
        """Bytes appended after an otherwise-valid PNG container are refused —
        the exact-container-end guard, not merely "PIL could open it"."""
        buf = BytesIO()
        Image.new("RGB", (4, 4)).save(buf, format="PNG")
        tampered = buf.getvalue() + b"\x00\x00\x00extra-trailer-bytes"
        encoded = base64.b64encode(tampered).decode("ascii")
        with self.assertRaises(frappe.ValidationError):
            images.verified_image_type(f"data:image/png;base64,{encoded}")


class TestHasExactContainerEnd(FrappeTestCase):
    """Direct coverage of the per-format trailing-bytes check."""

    def setUp(self):
        frappe.set_user("Administrator")

    def _bytes_for(self, image_format):
        buf = BytesIO()
        Image.new("RGB", (3, 3)).save(buf, format=image_format)
        return buf.getvalue()

    def test_png_exact_end_is_accepted_and_extra_bytes_refused(self):
        raw = self._bytes_for("PNG")
        self.assertTrue(images._has_exact_container_end(raw, "PNG"))
        self.assertFalse(images._has_exact_container_end(raw + b"\x00", "PNG"))

    def test_jpeg_exact_end_is_accepted_and_extra_bytes_refused(self):
        raw = self._bytes_for("JPEG")
        self.assertTrue(images._has_exact_container_end(raw, "JPEG"))
        self.assertFalse(images._has_exact_container_end(raw + b"\x00", "JPEG"))

    def test_webp_exact_end_is_accepted_and_extra_bytes_refused(self):
        raw = self._bytes_for("WEBP")
        self.assertTrue(images._has_exact_container_end(raw, "WEBP"))
        self.assertFalse(images._has_exact_container_end(raw + b"\x00", "WEBP"))

    def test_unknown_format_is_never_accepted(self):
        self.assertFalse(images._has_exact_container_end(b"anything", "GIF"))


class TestInvalidPhoto(FrappeTestCase):
    """Direct coverage of the shared raise helper."""

    def setUp(self):
        frappe.set_user("Administrator")

    def test_invalid_photo_raises_validation_error_with_the_given_message(self):
        with self.assertRaises(frappe.ValidationError) as ctx:
            images._invalid_photo("custom refusal message")
        self.assertIn("custom refusal message", str(ctx.exception))
