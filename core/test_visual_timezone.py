"""Pruebas sin BD: estilo institucional incrustado y zona horaria chilena."""
from datetime import datetime, timezone as utc

from django.conf import settings
from django.template.loader import render_to_string
from django.test import SimpleTestCase, RequestFactory
from django.utils import timezone


class VisualAndTimezoneTests(SimpleTestCase):
    def test_base_includes_visual_styles_without_external_css(self):
        html = render_to_string("base.html", request=RequestFactory().get("/"))
        self.assertIn(".modal.sgr-upgraded-modal .modal-header", html)
        self.assertIn(".sgr-catalog .catalog-toolbar-actions", html)
        self.assertNotIn('css/municipal_forms.css', html)
        self.assertNotIn('css/catalog_uniform.css', html)

    def test_santiago_uses_summer_and_winter_offsets(self):
        self.assertEqual(settings.TIME_ZONE, "America/Santiago")
        self.assertTrue(settings.USE_TZ)
        summer = timezone.localtime(datetime(2026, 10, 21, 5, tzinfo=utc.utc))
        winter = timezone.localtime(datetime(2026, 6, 21, 5, tzinfo=utc.utc))
        self.assertEqual(summer.strftime("%H:%M%z"), "02:00-0300")
        self.assertEqual(winter.strftime("%H:%M%z"), "01:00-0400")
