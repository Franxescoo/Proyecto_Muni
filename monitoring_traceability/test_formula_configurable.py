"""Pruebas de regresión: fórmulas configurables y agenda (base temporal Django)."""

from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from planning_measurements.measurement_rules import (
    FormulaError, evaluate_formula, validate_formula,
)
from planning_measurements.forms import MeasurementItemForm
from planning_measurements.models import MeasurementItem
from registration_validation.models import Activity, AttentionEntry, AttentionType, SubAttention, Evidence, Validation
from citizen_requests.models import CitizenRequest
from monitoring_traceability.models import Commitment, Indicator
from monitoring_traceability.forms import CommitmentForm
from monitoring_traceability.services import recalculate_indicator_for_goal


class FormulaSecurityTests(SimpleTestCase):
    def test_custom_arithmetic_with_spaces_and_aliases(self):
        formula = "(actividades aprobadas + compromisos_validados) / actividades registradas * 100"
        self.assertEqual(evaluate_formula(formula, {
            "actividades_aprobadas": 2, "compromisos_validados": 1,
            "actividades_registradas": 4,
        }), Decimal("75"))

    def test_division_by_zero_has_controlled_result(self):
        self.assertEqual(evaluate_formula(
            "(solicitudes_resueltas / solicitudes_registradas) * 100",
            {"solicitudes_resueltas": 0, "solicitudes_registradas": 0},
        ), Decimal("0"))

    def test_code_injection_and_unknown_variables_are_rejected(self):
        for formula in (
            "__import__('os').system('echo bad')",
            "actividades_aprobadas ** 999999999",
            "actividades_aprobadas.__class__",
            "campo_no_configurado / 2",
            "[1, 2, 3]",
        ):
            with self.subTest(formula=formula), self.assertRaises(FormulaError):
                validate_formula(formula)


class FormulaAndCommitmentIntegrationTests(TestCase):
    def setUp(self):
        from monitoring_traceability.test_monitoring_hardening import CommitmentHardeningTests
        CommitmentHardeningTests.setUp(self)

    def grant(self, *names):
        from monitoring_traceability.test_monitoring_hardening import CommitmentHardeningTests
        CommitmentHardeningTests.grant(self, *names)

    def commitment(self, *, overdue=False, status="Pending"):
        from monitoring_traceability.test_monitoring_hardening import CommitmentHardeningTests
        return CommitmentHardeningTests.commitment(self, overdue=overdue, status=status)

    def _set_formula(self, expression, *, item_type="percentage"):
        item = MeasurementItem.objects.create(
            code=f"CUSTOM-{MeasurementItem.objects.count() + 1}",
            name="Indicador configurable", item_type=item_type,
            unit="%" if item_type == "percentage" else "units",
            formula=expression,
        )
        self.goal.measurement_item = item
        self.goal.objective_value = 100 if item_type == "percentage" else 10
        self.goal.save(update_fields=["measurement_item", "objective_value"])
        return item

    def test_form_accepts_new_formula_but_rejects_unknown_variable(self):
        data = {
            "code": "FORM-NEW", "name": "Indicador nuevo", "description": "",
            "item_type": "percentage", "unit": "%", "is_active": True,
            "formula": "(actividades_aprobadas + compromisos_validados) / actividades_registradas * 100",
        }
        form = MeasurementItemForm(data)
        self.assertTrue(form.is_valid(), form.errors)
        data["formula"] = "variables_inexistentes * 100"
        self.assertFalse(MeasurementItemForm(data).is_valid())

    def test_manual_commitment_without_activity_preserves_responsible(self):
        data = {
            "delegation": self.north.pk, "activity": "", "responsible": self.owner.pk,
            "origin": "Solicitud interna", "requester": "Vecino de prueba",
            "territory": "Norte", "commitment_date": "2026-12-20",
            "support": "Asistencia municipal", "observation": "Seguimiento",
        }
        form = CommitmentForm(
            data, employees=type(self.owner).objects.all(),
            delegations=type(self.north).objects.all(),
            activities=Activity.objects.filter(pk=self.activity.pk),
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().responsible_id, self.owner.pk)
        self.grant("add_commitment")
        data["action"] = "create_commitment"
        self.assertEqual(self.client.post(self.path, data).status_code, 302)
        self.assertEqual(Commitment.objects.filter(activity__isnull=True).count(), 2)

    def test_manual_commitment_requires_responsible_and_date(self):
        form = CommitmentForm({
            "delegation": self.north.pk, "activity": "", "origin": "Interna",
            "requester": "Vecino", "territory": "Norte",
        }, employees=type(self.owner).objects.all(),
           delegations=type(self.north).objects.all(), activities=Activity.objects.all())
        self.assertFalse(form.is_valid())
        self.assertIn("responsible", form.errors)
        self.assertIn("commitment_date", form.errors)

    def test_status_transition_requires_valid_path_and_observation(self):
        self.grant("change_commitment")
        commitment = self.commitment()
        url = self.path
        for status, observation, expected in [
            ("Validated", "No permitido", "Pending"),
            ("In progress", "", "Pending"),
            ("Completed", "Trabajo terminado", "Completed"),
            ("Validated", "Validación final", "Validated"),
            ("Pending", "Reabrir sin permiso", "Validated"),
        ]:
            res = self.client.post(url, {
                "action": "status", "commitment_id": commitment.pk,
                "status": status, "observation": observation,
            })
            self.assertEqual(res.status_code, 302)
            commitment.refresh_from_db()
            self.assertEqual(commitment.status, expected)

    def test_commitment_validated_is_counted_once_and_reversal_updates(self):
        self._set_formula("compromisos_validados / compromisos_registrados * 100")
        commitment = self.commitment(status="Completed")
        self.assertEqual(recalculate_indicator_for_goal(self.goal).actual_progress, Decimal("0"))
        commitment.status = "Validated"
        commitment.save(update_fields=["status", "updated_at"])
        self.assertEqual(Indicator.objects.get(goal=self.goal).actual_progress, Decimal("100"))
        # La repetición del mismo estado no duplica el resultado.
        commitment.save(update_fields=["status", "updated_at"])
        self.assertEqual(Indicator.objects.get(goal=self.goal).actual_progress, Decimal("100"))
        commitment.status = "In progress"
        commitment.save(update_fields=["status", "updated_at"])
        self.assertEqual(Indicator.objects.get(goal=self.goal).actual_progress, Decimal("0"))

    def test_distinct_attentions_not_activities_are_counted(self):
        self._set_formula("(atenciones_completadas / atenciones_registradas) * 100")
        attention_type = AttentionType.objects.create(code="F-ATTN", name="Test")
        sub = SubAttention.objects.create(code="F-SUB", name="Sub", attention_type=attention_type)
        attention = AttentionEntry.objects.create(
            requester="Solicitante", attention_type=attention_type,
            sub_attention=sub, description="Solicitud", delegation=self.north,
            responsible_employee=self.owner, status="RESOLVED",
        )
        for n in range(2):
            Activity.objects.create(
                goal=self.goal, author=self.owner, attention=attention,
                date=date(2026, 6, n + 8), request_problem="Gestión",
                action="Acción", contact="Vecino", phone="123",
            )
        # La atención resuelta por sí sola no otorga avance sin evidencia validada.
        self.assertEqual(recalculate_indicator_for_goal(self.goal).actual_progress, Decimal("0"))
        activity = Activity.objects.filter(goal=self.goal, attention=attention).first()
        evidence = Evidence.objects.create(
            code="FORM-ATT-VALIDATED", activity=activity, author=self.owner,
            date=timezone.now(), review_status="Pending",
        )
        Validation.objects.create(
            evidence=evidence, verifier=self.owner, date=timezone.now(),
            decision="approved", result="approved", version=1,
        )
        self.assertEqual(recalculate_indicator_for_goal(self.goal).actual_progress, Decimal("100"))
        attention.status = "IN_PROGRESS"
        attention.save(update_fields=["status", "updated_at"])
        self.assertEqual(Indicator.objects.get(goal=self.goal).actual_progress, Decimal("0"))

    def test_resolved_requests_use_request_status_not_attention_status(self):
        self._set_formula("solicitudes_resueltas / solicitudes_registradas * 100")
        attention_type = AttentionType.objects.create(code="F-AT2", name="Solicitud")
        sub = SubAttention.objects.create(code="F-SUB2", name="Sub", attention_type=attention_type)
        attention = AttentionEntry.objects.create(
            requester="Solicitante", attention_type=attention_type,
            sub_attention=sub, description="Solicitud", delegation=self.north,
            responsible_employee=self.owner, status="RESOLVED",
        )
        self.activity.attention = attention
        self.activity.save(update_fields=["attention", "updated_at"])
        request = CitizenRequest.objects.create(
            attention_entry=attention, delegation=self.north,
            origin="INTERNAL", requester_name="Vecino", address="Norte",
            subject="Gestión", description="Solicitud", status="NEW",
        )
        self.assertEqual(recalculate_indicator_for_goal(self.goal).actual_progress, Decimal("0"))
        request.status = "CLOSED"
        request.save(update_fields=["status", "updated_at"])
        self.assertEqual(Indicator.objects.get(goal=self.goal).actual_progress, Decimal("0"))
        evidence = Evidence.objects.create(
            code="FORM-REQ-VALIDATED", activity=self.activity, author=self.owner,
            date=timezone.now(), review_status="Pending",
        )
        Validation.objects.create(
            evidence=evidence, verifier=self.owner, date=timezone.now(),
            decision="approved", result="approved", version=1,
        )
        self.assertEqual(Indicator.objects.get(goal=self.goal).actual_progress, Decimal("100"))

    def test_closed_period_indicator_remains_frozen_until_reopened(self):
        self._set_formula("actividades_registradas * 10")
        indicator = recalculate_indicator_for_goal(self.goal)
        self.assertEqual(indicator.actual_progress, Decimal("10"))
        self.period.status = "Closed"
        self.period.save(update_fields=["status", "updated_at"])
        Activity.objects.create(
            goal=self.goal, author=self.owner, date=date(2026, 7, 2),
            request_problem="Nueva", action="Acción", contact="Vecino", phone="123",
        )
        self.assertEqual(recalculate_indicator_for_goal(self.goal).actual_progress, Decimal("10"))
        self.period.status = "Active"
        self.period.save(update_fields=["status", "updated_at"])
        self.assertEqual(recalculate_indicator_for_goal(self.goal).actual_progress, Decimal("20"))

    def test_commitment_summary_matches_filtered_list(self):
        self.commitment(status="Pending")
        Commitment.objects.create(
            delegation=self.north, responsible=self.owner, activity=None,
            requester="Otro vecino", origin="Solicitud interna", territory="Norte",
            commitment_date=timezone.localdate() + timedelta(days=3),
            status="Completed",
        )
        page = self.client.get(self.path)
        self.assertEqual(page.status_code, 200)
        summary = page.context["commitment_summary"]
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["total"], 2)
        self.assertEqual(summary[0]["realized"], 1)
        self.assertEqual(summary[0]["pending"], 1)
        self.assertEqual(summary[0]["pct_realized"], 50)

    def test_edit_with_stale_version_is_forbidden_instead_of_overwriting(self):
        # La edición general se bloquea aunque se envíe una versión antigua.
        self.grant("change_commitment")
        commitment = self.commitment()
        old_version = commitment.updated_at.isoformat()
        commitment.territory = "Territorio cambiado por otro funcionario"
        commitment.save(update_fields=["territory", "updated_at"])
        res = self.client.post(self.path, {
            "action": "edit_commitment", "commitment_id": commitment.pk,
            "commitment_version": old_version,
            "territory": "Cambio atrasado", "observation": "Prueba de conflicto",
        })
        self.assertEqual(res.status_code, 403)
        commitment.refresh_from_db()
        self.assertEqual(commitment.territory, "Territorio cambiado por otro funcionario")

    def test_finished_after_deadline_is_flagged(self):
        commitment = self.commitment(overdue=True)
        commitment.status = "Completed"
        commitment.save(update_fields=["status", "updated_at"])
        self.assertTrue(commitment.is_completed_late)

    def test_outdated_alert_is_resolved_after_new_due_date(self):
        from monitoring_traceability.services import synchronize_commitment_alerts
        from monitoring_traceability.models import CommitmentAlert
        commitment = self.commitment(overdue=True)
        synchronize_commitment_alerts([commitment])
        self.assertTrue(CommitmentAlert.objects.filter(
            commitment=commitment, resolved_at__isnull=True,
        ).exists())
        commitment.commitment_date = timezone.localdate() + timedelta(days=30)
        commitment.save(update_fields=["commitment_date", "updated_at"])
        synchronize_commitment_alerts([commitment])
        self.assertFalse(CommitmentAlert.objects.filter(
            commitment=commitment, resolved_at__isnull=True,
        ).exists())

    def test_inactivity_alert_is_period_scoped_and_skips_closed(self):
        from monitoring_traceability.services import monitoring_alerts
        alerts = monitoring_alerts(employees=[self.owner], period=self.period)
        self.assertEqual(alerts["inactive_employees"], 1)
        self.period.status = "Closed"
        self.period.save(update_fields=["status", "updated_at"])
        alerts = monitoring_alerts(employees=[self.owner], period=self.period)
        self.assertEqual(alerts["inactive_employees"], 0)

    def test_adjustment_cannot_change_closed_period_result(self):
        self.grant("view_indicator", "change_indicator")
        indicator = recalculate_indicator_for_goal(self.goal)
        self.period.status = "Closed"
        self.period.save(update_fields=["status", "updated_at"])
        response = self.client.post(reverse("monitoring:indicator_list"), {
            "indicator_id": indicator.pk,
            "adjustment": "30",
            "reason": "Intento sobre período cerrado",
        })
        self.assertEqual(response.status_code, 302)
        indicator.refresh_from_db()
        self.assertEqual(indicator.adjustment, 0)
