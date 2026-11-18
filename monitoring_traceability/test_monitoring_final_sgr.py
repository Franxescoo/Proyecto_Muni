"""Pruebas RF-025, RF-031, RF-033, HU-31 / revisión final.

No escribe datos permanentes: Django crea y destruye una base de pruebas.
"""
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from monitoring_traceability.test_monitoring_hardening import CommitmentHardeningTests
from monitoring_traceability.models import (
    MonitoringSettings, MonitoringSettingsRevision, MonitoringAlertReview,
)
from monitoring_traceability.services import (
    inactivity_threshold_days, monitoring_alerts, recalculate_indicator_for_goal,
)
from organization.models import PositionFunction
from planning_measurements.models import Goal


class MonitoringFinalSgrTests(TestCase):
    def setUp(self):
        CommitmentHardeningTests.setUp(self)

    def grant(self, *names):
        return CommitmentHardeningTests.grant(self, *names)

    def test_indicator_export_respects_position_and_delegation(self):
        self.grant("view_indicator")
        second_position = PositionFunction.objects.create(
            position_name="Otro cargo", measurable_items="Pruebas", services="Consulta",
            weightings="100", validity_start=self.period.start_date,
            validity_end=self.period.end_date,
        )
        Goal.objects.create(
            period=self.period, employee=self.owner, position=second_position,
            item="Distinta", objective_value=10, weight=30, unit="units",
        )
        recalculate_indicator_for_goal(self.goal)
        for goal in Goal.objects.filter(position=second_position):
            recalculate_indicator_for_goal(goal)
        uri = reverse("monitoring:indicator_export")
        response = self.client.get(uri, {
            "delegation": self.north.pk, "position": self.position.pk,
            "period": self.period.pk,
        })
        self.assertEqual(response.status_code, 200)
        book = load_workbook(BytesIO(response.content), read_only=True)
        data = [row for row in book.active.values]
        self.assertTrue(any(self.goal.item == str(cell) for row in data for cell in row))
        self.assertFalse(any("Distinta" == str(cell) for row in data for cell in row))
        self.assertTrue(any("cargo=" in str(cell) for row in data for cell in row))
        book.close()

    def test_dashboard_displays_group_by_goal_position_and_period(self):
        self.grant("view_indicator")
        response = self.client.get(reverse("monitoring:executive_dashboard"), {
            "period": self.period.pk,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Consolidado por cargo y período")
        groups = response.context["positions_summary"]
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["position"].pk, self.position.pk)
        self.assertEqual(groups[0]["goals"], 1)
        self.assertEqual(groups[0]["weighting"], Decimal("100"))

    def test_alert_review_persists_without_deleting_original_alert(self):
        self.grant("view_indicator", "change_indicator")
        uri = reverse("monitoring:executive_dashboard")
        response = self.client.get(uri, {"period": self.period.pk})
        self.assertEqual(response.status_code, 200)
        item = response.context["low_performance_details"][0]
        key = item.monitor_key
        self.assertEqual(self.client.post(uri + f"?period={self.period.pk}", {
            "alert_key": key,
        }).status_code, 302)
        self.assertEqual(MonitoringAlertReview.objects.filter(alert_key=key).count(), 1)
        self.assertEqual(MonitoringAlertReview.objects.get(alert_key=key).reviewed_by, self.user)
        response = self.client.get(uri, {"period": self.period.pk})
        self.assertContains(response, "Revisada")
        self.assertEqual(response.context["low_performance_details"][0].monitor_key, key)

    def test_unprivileged_user_cannot_review_alert(self):
        self.grant("view_indicator")
        uri = reverse("monitoring:executive_dashboard")
        response = self.client.get(uri, {"period": self.period.pk})
        key = response.context["low_performance_details"][0].monitor_key
        self.assertEqual(self.client.post(uri + f"?period={self.period.pk}", {
            "alert_key": key,
        }).status_code, 403)
        self.assertFalse(MonitoringAlertReview.objects.exists())

    def test_rule_editor_needs_distinct_permission(self):
        self.grant("view_indicator", "change_indicator")
        self.assertEqual(self.client.get(reverse("monitoring:monitoring_settings")).status_code, 403)

    def test_rule_update_keeps_before_after_and_actor(self):
        self.grant("change_monitoringsettings")
        url = reverse("monitoring:monitoring_settings")
        response = self.client.post(url, {
            "low_compliance_threshold": "75.00",
            "inactivity_workdays": "9", "due_soon_days": "3",
            "positive_adjustment_max": "20", "negative_adjustment_max": "15",
            "recipient_users": [self.user.pk],
            "effective_from": "",
        })
        self.assertEqual(response.status_code, 302)
        rule = MonitoringSettings.objects.get(key="global")
        self.assertEqual(rule.low_compliance_threshold, Decimal("75.00"))
        self.assertEqual(rule.inactivity_workdays, 9)
        self.assertEqual(rule.recipient_users.count(), 1)
        self.assertEqual(inactivity_threshold_days(), 9)
        revision = MonitoringSettingsRevision.objects.get()
        self.assertEqual(revision.changed_by, self.user)
        self.assertEqual(revision.previous_value["inactivity_workdays"], 5)
        self.assertEqual(revision.new_value["inactivity_workdays"], 9)

    def test_configured_adjustment_limit_rejects_excess(self):
        self.grant("view_indicator", "change_indicator")
        MonitoringSettings.objects.create(
            key="global", positive_adjustment_max=Decimal("10.00"),
            negative_adjustment_max=Decimal("5.00"),
        )
        indicator = recalculate_indicator_for_goal(self.goal)
        result = self.client.post(reverse("monitoring:indicator_list"), {
            "indicator_id": indicator.pk,
            "adjustment": "30", "adjustment_type": "bonificacion",
            "reason": "Prueba de límite",
        })
        self.assertEqual(result.status_code, 302)
        indicator.refresh_from_db()
        self.assertEqual(indicator.adjustment, Decimal("0"))

    def test_compliance_threshold_is_configurable(self):
        MonitoringSettings.objects.create(key="global", low_compliance_threshold=Decimal("75"))
        recalculate_indicator_for_goal(self.goal)
        result = monitoring_alerts(employees=[self.owner], period=self.period)
        self.assertEqual(result["low_performance"], 1)
