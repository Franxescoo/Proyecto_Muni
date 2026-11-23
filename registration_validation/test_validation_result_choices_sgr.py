from django.test import TestCase
from .forms import ValidationForm


class ValidationResultChoicesTests(TestCase):
    def test_result_is_select_not_free_text(self):
        form = ValidationForm()
        self.assertEqual(form.fields['result'].widget.input_type, 'select')
        choices = dict(form.fields['result'].choices)
        self.assertEqual(choices['Approved'], 'Aprobada')
        self.assertEqual(choices['Rejected'], 'Rechazada')
        self.assertNotIn('Texto arbitrario', choices)
