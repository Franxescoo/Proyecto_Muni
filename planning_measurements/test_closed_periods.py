from datetime import date
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from .models import Period, PeriodArchiveLog


class ClosedPeriodArchiveTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("archivo-períodos", password="Seguro2026!clave")
        self.user.user_permissions.add(Permission.objects.get(
            content_type__app_label="planning_measurements", codename="delete_period",
        ))
        self.period = Period.objects.create(
            start_date=date(2026, 1, 1), end_date=date(2026, 1, 31),
            computable_days=21, thresholds="70%,80%", parameters_version="v1",
            status=Period.Status.CLOSED,
        )
        self.client.force_login(self.user)

    def test_closed_requires_direct_special_permission(self):
        url = reverse("planning:period_delete", kwargs={"period_id": self.period.pk})
        self.assertEqual(self.client.post(url).status_code, 403)
        self.period.refresh_from_db()
        self.assertIsNone(self.period.deleted_at)
        special = Permission.objects.get(
            content_type__app_label="planning_measurements", codename="delete_closed_period",
        )
        self.user.user_permissions.add(special)
        result = self.client.post(url)
        self.assertEqual(result.status_code, 302)
        self.assertEqual(result.url, reverse("planning:period_list"))
        self.period.refresh_from_db()
        self.assertIsNotNone(self.period.deleted_at)
        self.assertTrue(PeriodArchiveLog.objects.filter(
            period=self.period, user=self.user, was_closed=True,
        ).exists())
