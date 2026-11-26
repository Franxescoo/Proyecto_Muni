"""Regresión de acreditación, validación, alertas y fecha de recálculo."""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from monitoring_traceability.test_monitoring_hardening import CommitmentHardeningTests
from planning_measurements.models import MeasurementItem
from registration_validation.models import Evidence, Validation, AttentionEntry, AttentionType, SubAttention
from monitoring_traceability.models import Indicator
from monitoring_traceability.services import (
    monitoring_alerts, recalculate_indicator_for_goal,
    pending_evidence_queryset,
)


class AccreditationMonitoringTests(TestCase):
    def grant(self, *names):
        return CommitmentHardeningTests.grant(self, *names)

    def setUp(self):
        CommitmentHardeningTests.setUp(self)
        item = MeasurementItem.objects.create(
            code="ACCREDITATION-ATT", name="Atenciones resueltas con evidencia",
            item_type="percentage", unit="%",
            formula="(atenciones_completadas / atenciones_registradas) * 100",
        )
        self.goal.measurement_item = item
        self.goal.objective_value = 40
        self.goal.required_evidence_count = 12
        self.goal.save(update_fields=["measurement_item", "objective_value", "required_evidence_count"])
        atype = AttentionType.objects.create(code="ACC-ATT", name="Atención")
        sub = SubAttention.objects.create(code="ACC-SUB", name="Gestión", attention_type=atype)
        self.attention = AttentionEntry.objects.create(
            requester="Solicitante de prueba", attention_type=atype,
            sub_attention=sub, description="Prueba", delegation=self.north,
            responsible_employee=self.owner, status="RESOLVED",
        )
        self.activity.attention = self.attention
        self.activity.save(update_fields=["attention", "updated_at"])

    def _validate(self, code, decision="approved", result="approved", evidence=None):
        if evidence is None:
            evidence = Evidence.objects.create(
                code=code, activity=self.activity, author=self.owner,
                date=timezone.now(), review_status="Pending",
            )
        Validation.objects.create(
            evidence=evidence, verifier=self.owner,
            decision=decision, result=result, date=timezone.now(),
            version=evidence.validations.count() + 1,
        )
        return evidence

    def test_atencion_resuelta_sin_evidencia_avanza_pero_no_acredita(self):
        indicator = recalculate_indicator_for_goal(self.goal)
        self.assertEqual(indicator.actual_progress, Decimal("100"))
        self.assertFalse(indicator.evidence_accreditation_met)
        self.assertEqual(indicator.effective_traffic_light, "Pending")

    def test_una_evidencia_no_acredita_doce_y_semaforo_no_es_verde(self):
        self._validate("PRUEBA-001")
        indicator = recalculate_indicator_for_goal(self.goal)
        self.assertEqual(indicator.approved_evidences, 1)
        self.assertEqual(indicator.actual_progress, Decimal("100"))
        self.assertEqual(indicator.compliance, Decimal("120.00"))
        self.assertEqual(indicator.evidence_remaining, 11)
        self.assertEqual(indicator.traffic_light, "Green")
        self.assertEqual(indicator.effective_traffic_light, "Pending")

    def test_ultima_validacion_rechazada_resta_acreditacion_no_avance(self):
        evidence = self._validate("EVI-REVERTIR")
        self.assertEqual(recalculate_indicator_for_goal(self.goal).actual_progress, Decimal("100"))
        self._validate("EVI-REVERTIR", decision="rejected", result="rejected", evidence=evidence)
        indicator = recalculate_indicator_for_goal(self.goal)
        self.assertEqual(indicator.actual_progress, Decimal("100"))
        self.assertEqual(indicator.approved_evidences, 0)
        self.assertEqual(pending_evidence_queryset(Evidence.objects.filter(pk=evidence.pk)).count(), 1)
        self.assertEqual(monitoring_alerts(employees=[self.owner], period=self.period)["pending_evidences"], 1)

    def test_alerta_no_incluye_evidencia_validada_con_campo_pending(self):
        evidence = self._validate("EVI-APROBADA")
        evidence.refresh_from_db()
        self.assertEqual(evidence.review_status, "Pending")
        alerts = monitoring_alerts(employees=[self.owner], period=self.period)
        self.assertEqual(alerts["pending_evidences"], 0)

    def test_llegar_a_doce_evidencias_acredita(self):
        for index in range(12):
            self._validate(f"EVI-{index:02d}")
        indicator = recalculate_indicator_for_goal(self.goal)
        self.assertEqual(indicator.approved_evidences, 12)
        self.assertTrue(indicator.evidence_accreditation_met)
        self.assertEqual(indicator.effective_traffic_light, "Green")

    def test_una_aprobada_y_otra_pendiente_no_acredita_actividad(self):
        self._validate("EVI-PARCIAL-OK")
        pendiente = Evidence.objects.create(
            code="EVI-PARCIAL-PEND", activity=self.activity, author=self.owner,
            date=timezone.now(), review_status="Pending",
        )
        indicator = recalculate_indicator_for_goal(self.goal)
        self.assertEqual(indicator.approved_activities, 0)
        self.assertEqual(indicator.approved_evidences, 0)
        self.assertEqual(indicator.actual_progress, Decimal("100"))

        self._validate("EVI-PARCIAL-PEND", evidence=pendiente)
        indicator = recalculate_indicator_for_goal(self.goal)
        self.assertEqual(indicator.approved_activities, 1)
        self.assertEqual(indicator.approved_evidences, 2)
        self.assertEqual(indicator.actual_progress, Decimal("100"))

    def test_ultima_validacion_rechazada_retira_aprobacion_conjunta(self):
        self._validate("EVI-CONJ-1")
        segunda = self._validate("EVI-CONJ-2")
        self.assertEqual(recalculate_indicator_for_goal(self.goal).approved_activities, 1)
        self._validate("EVI-CONJ-2", decision="rejected", result="rejected", evidence=segunda)
        indicator = recalculate_indicator_for_goal(self.goal)
        self.assertEqual(indicator.approved_activities, 0)
        self.assertEqual(indicator.approved_evidences, 0)
        self.assertEqual(indicator.actual_progress, Decimal("100"))

    def test_evidencia_archivada_no_impide_aprobacion_de_vigentes(self):
        self._validate("EVI-ACTIVA")
        archivada = Evidence.objects.create(
            code="EVI-ARCHIVADA", activity=self.activity, author=self.owner,
            date=timezone.now(), review_status="Pending", deleted_at=timezone.now(),
        )
        indicator = recalculate_indicator_for_goal(self.goal)
        self.assertEqual(indicator.approved_activities, 1)
        self.assertEqual(indicator.approved_evidences, 1)
        archivada.refresh_from_db()
        self.assertIsNotNone(archivada.deleted_at)

    def test_recalcular_refresca_fecha_sin_cambiar_periodos_cerrados(self):
        self._validate("EVI-FECHA")
        indicator = recalculate_indicator_for_goal(self.goal)
        old_date = timezone.localdate() - timedelta(days=20)
        Indicator.objects.filter(pk=indicator.pk).update(calculation_date=old_date)
        indicator = recalculate_indicator_for_goal(self.goal)
        self.assertEqual(indicator.calculation_date, timezone.localdate())
        self.period.status = "Closed"
        self.period.save(update_fields=["status", "updated_at"])
        Indicator.objects.filter(pk=indicator.pk).update(calculation_date=old_date)
        indicator = recalculate_indicator_for_goal(self.goal)
        self.assertEqual(indicator.calculation_date, old_date)
