from django.core.exceptions import ValidationError
from django.template import Context, Template
from django.template.loader import get_template
from django.test import SimpleTestCase

from .forms import EvidenceForm
from .models import (
    Evidence,
    is_safe_evidence_file_link,
    validate_evidence_file_link,
)


class EvidenceFileLinkTests(SimpleTestCase):
    def validate_form_link(self, value):
        form = EvidenceForm()
        form.cleaned_data = {"file_link": value}
        return form.clean_file_link()

    def test_http_and_https_links_are_accepted(self):
        for value in (
            "http://example.com/evidence/1",
            "https://example.com/evidence/1",
        ):
            with self.subTest(value=value):
                self.assertEqual(self.validate_form_link(value), value)

    def test_dangerous_schemes_are_rejected_case_insensitively(self):
        for value in (
            "javascript:alert(1)",
            "data:text/html,example",
            "vbscript:msgbox(1)",
            "JaVaScRiPt:alert(1)",
            " DATA:text/html,example ",
            "VbScRiPt:msgbox(1)",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    self.validate_form_link(value)

    def test_scheme_with_embedded_whitespace_is_rejected(self):
        for value in (
            "java script:alert(1)",
            "java\nscript:alert(1)",
            "https://example.com/a path",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    self.validate_form_link(value)

    def test_existing_relative_evidence_references_remain_compatible(self):
        for value in (
            "evidence/north-001",
            "evidence/south-001",
        ):
            with self.subTest(value=value):
                self.assertEqual(self.validate_form_link(value), value)
                self.assertTrue(is_safe_evidence_file_link(value))

    def test_model_validation_rejects_unsafe_link(self):
        evidence = Evidence(file_link="javascript:alert(1)")

        with self.assertRaises(ValidationError) as context:
            evidence.full_clean(
                exclude={
                    "code",
                    "activity",
                    "author",
                    "date",
                }
            )

        self.assertIn("file_link", context.exception.message_dict)

    def test_unsafe_stored_link_is_not_rendered_as_clickable(self):
        evidence = Evidence(file_link=" JaVaScRiPt:alert(1) ")

        self.assertEqual(evidence.safe_file_link, "")
        template = get_template(
            "registration_validation/evidence_list.html"
        ).template.source
        self.assertIn("evidence.safe_file_link", template)
        self.assertNotIn('href="{{ evidence.file_link }}"', template)

    def test_relative_links_remain_clickable_and_escaped(self):
        evidence = Evidence(
            file_link='evidence/north-001?name="informe"',
        )

        self.assertEqual(
            evidence.safe_file_link,
            'evidence/north-001?name="informe"',
        )
        self.assertTrue(is_safe_evidence_file_link(evidence.safe_file_link))
        rendered_link = Template(
            '<a href="{{ evidence.safe_file_link }}">Enlace</a>'
        ).render(Context({"evidence": evidence}))
        self.assertIn(
            'href="evidence/north-001?name=&quot;informe&quot;"',
            rendered_link,
        )
