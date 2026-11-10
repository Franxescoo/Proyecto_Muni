from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from .validators import normalize_rut


class RutValidationTests(SimpleTestCase):
    def test_formats_and_normalizes_valid_rut(self):
        self.assertEqual(normalize_rut("123456785"), "12.345.678-5")
        self.assertEqual(normalize_rut("12.345.678-5"), "12.345.678-5")

    def test_rejects_invalid_verifier(self):
        with self.assertRaises(ValidationError):
            normalize_rut("12.345.678-6")

    def test_rejects_excessive_body_length(self):
        with self.assertRaises(ValidationError):
            normalize_rut("123456789-5")

    def test_accepts_uppercase_and_lowercase_k_verifier(self):
        self.assertEqual(normalize_rut("16.666.666-K"), "16.666.666-K")
        self.assertEqual(normalize_rut("16.666.666-k"), "16.666.666-K")
