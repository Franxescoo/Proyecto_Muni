"""Pruebas de fecha automática e histórica en Validaciones."""
from datetime import date, datetime, timedelta
from unittest.mock import patch

from django.test import SimpleTestCase
from django.utils import timezone

from .forms import ValidationForm
from .models import Validation
from .views import ValidationCreateView


class ValidationAutoDateFormTests(SimpleTestCase):
    def test_new_validation_prefills_and_locks_current_time(self):
        form = ValidationForm()
        self.assertTrue(form.fields["date"].disabled)
        self.assertIsNotNone(form.fields["date"].initial)
        self.assertLess(
            abs((timezone.now() - form.fields["date"].initial).total_seconds()),
            120,
        )

    def test_edit_validation_preserves_historical_date(self):
        past = timezone.make_aware(datetime(2026, 6, 1, 10, 30))
        validation = Validation(pk=123, date=past)
        form = ValidationForm(instance=validation)
        self.assertTrue(form.fields["date"].disabled)
        self.assertEqual(form.initial["date"], past)

    def test_create_view_sets_server_time_before_saving(self):
        # Comprueba la protección del lado del servidor sin tocar la BD.
        fake_form = type("Form", (), {"instance": Validation(date=timezone.make_aware(datetime(2000, 1, 1)))})()
        view = ValidationCreateView()
        with patch("django.views.generic.edit.ModelFormMixin.form_valid", return_value="OK") as parent_save, patch("registration_validation.views.messages.success"):
            view.request = object()
            previous = timezone.now()
            self.assertEqual(view.form_valid(fake_form), "OK")
            subsequent = timezone.now()
        self.assertTrue(previous <= fake_form.instance.date <= subsequent)
        parent_save.assert_called_once_with(fake_form)
