"""Regresión: historial de configuración legible sin alterar auditoría."""
from django.test import SimpleTestCase

from .templatetags.monitoring_settings_extras import monitoring_settings_changes


class MonitoringSettingsDisplayTests(SimpleTestCase):
    def test_muestra_solo_el_parametro_cambiado(self):
        before = {
            "low_compliance_threshold": "80",
            "inactivity_workdays": 5,
            "due_soon_days": 7,
            "positive_adjustment_max": "100.00",
        }
        after = {
            "low_compliance_threshold": "80.00",
            "inactivity_workdays": 5,
            "due_soon_days": 4,
            "positive_adjustment_max": "100",
        }
        self.assertEqual(monitoring_settings_changes(before, after), [
            {"label": "Aviso antes del vencimiento", "before": "7 días", "after": "4 días"}
        ])

    def test_no_cambia_el_historial_original(self):
        before = {"due_soon_days": 7}
        after = {"due_soon_days": 6}
        monitoring_settings_changes(before, after)
        self.assertEqual(before, {"due_soon_days": 7})
        self.assertEqual(after, {"due_soon_days": 6})

    def test_no_muestra_cambio_si_solo_varia_el_formato_numerico(self):
        self.assertEqual(
            monitoring_settings_changes(
                {"low_compliance_threshold": "80.00"},
                {"low_compliance_threshold": "80"},
            ),
            [],
        )
