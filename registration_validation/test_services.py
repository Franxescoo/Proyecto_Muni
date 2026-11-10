from django.test import SimpleTestCase

from .forms import ServiceForm


class ServiceFormTests(SimpleTestCase):

    def test_text_limits_are_enforced_server_side_and_in_html(self):
        form = ServiceForm(data={
            "code": "C" * 51,
            "name": "N" * 151,
            "description": "D" * 301,
            "status": "True",
        })

        self.assertFalse(form.is_valid())
        self.assertIn("code", form.errors)
        self.assertIn("name", form.errors)
        self.assertIn("description", form.errors)
        self.assertEqual(form.fields["code"].widget.attrs["maxlength"], 50)
        self.assertEqual(form.fields["name"].widget.attrs["maxlength"], 150)
        self.assertEqual(
            form.fields["description"].widget.attrs["maxlength"],
            300,
        )
