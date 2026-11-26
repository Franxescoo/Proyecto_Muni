"""Regresión: el cálculo no supera el 120 % aun con topes heredados."""
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from organization.models import Delegation, Employee, PositionFunction
from planning_measurements.models import Goal, Period
from registration_validation.models import Activity, Evidence, Validation
from registration_validation.test_resolved_attention_support import link_resolved_attention

from .services import _compliance_cap, recalculate_indicator_for_goal


class EffectiveCapTests(SimpleTestCase):
    def test_legacy_150_is_clamped(self):
        period = SimpleNamespace(parameters_version="v1", thresholds="Tope: 150")
        self.assertEqual(_compliance_cap(period), Decimal("120"))

    def test_legacy_180_is_clamped(self):
        period = SimpleNamespace(parameters_version="v1", thresholds="Max: 180")
        self.assertEqual(_compliance_cap(period), Decimal("120"))

    def test_lower_configured_cap_is_honored(self):
        period = SimpleNamespace(parameters_version="v1", thresholds="Tope: 110")
        self.assertEqual(_compliance_cap(period), Decimal("110"))

    def test_missing_cap_defaults_to_120(self):
        period = SimpleNamespace(parameters_version="v1", thresholds="Verde: 100")
        self.assertEqual(_compliance_cap(period), Decimal("120"))


class IndicatorComplianceCapTests(TestCase):
    def test_200_percent_raw_progress_becomes_120_without_losing_actual(self):
        today = timezone.localdate()
        delegation = Delegation.objects.create(
            name="Delegación límite", status="Active", scope="Local",
        )
        position = PositionFunction.objects.create(
            position_name="Cargo prueba límite", measurable_items="Actividades",
            services="Servicios", weightings="100",
            validity_start=today - timedelta(days=60),
            validity_end=today + timedelta(days=60),
        )
        employee = Employee.objects.create(
            delegation=delegation, position=position, name="Funcionario prueba",
            roles="Staff", status="Active",
        )
        period = Period.objects.create(
            start_date=today - timedelta(days=30),
            end_date=today + timedelta(days=30),
            computable_days=40, status=Period.Status.ACTIVE,
            thresholds="Verde: 100, Amarillo: 80, Rojo: 60, Tope: 150.00",
            parameters_version="v1",
        )
        goal = Goal.objects.create(
            period=period, employee=employee, position=position,
            item="Actividades aprobadas", objective_value=Decimal("1"),
            unit="unidades", weight=Decimal("100"),
        )
        for n in range(2):
            activity = Activity.objects.create(
                goal=goal, author=employee, date=today,
                request_problem="Problema", action="Acción",
                contact="Contacto", phone="555",
            )
            link_resolved_attention(activity)
            evidence = Evidence.objects.create(
                code=f"LIM-120-{n}", activity=activity, author=employee,
                file_link=f"evidencias/tope-{n}", date=timezone.now(),
                review_status="Pending",
            )
            Validation.objects.create(
                evidence=evidence, verifier=employee, decision="Approved",
                result="Approved", date=timezone.now(),
            )
        indicator = recalculate_indicator_for_goal(goal)
        self.assertEqual(indicator.actual_progress, Decimal("2"))
        self.assertEqual(indicator.compliance, Decimal("120.00"))
        self.assertEqual(indicator.weighted_result, Decimal("120.00"))

        indicator.adjustment = Decimal("25")
        indicator.save(update_fields=["adjustment"])
        indicator = recalculate_indicator_for_goal(goal)
        self.assertEqual(indicator.compliance, Decimal("120.00"))
        self.assertEqual(indicator.weighted_result, Decimal("120.00"))

        period.status = Period.Status.CLOSED
        period.save(update_fields=["status"])
        # Al cerrar, el cálculo consolidado no se altera.
        indicator = recalculate_indicator_for_goal(goal)
        self.assertEqual(indicator.compliance, Decimal("120.00"))
