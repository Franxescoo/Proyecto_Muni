"""Pruebas de clasificación y respaldo formal de felicitaciones (usuarios normales)."""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.utils import timezone

from accounts.models import UserProfile
from monitoring_traceability.services import _evidence_is_approved, recalculate_indicator_for_goal
from registration_validation.test_resolved_attention_support import link_resolved_attention
from organization.models import Delegation, Employee, PositionFunction
from planning_measurements.models import Goal, Period
from registration_validation.activity_rules import activity_qualifies_for_goal
from registration_validation.forms import ActivityTypeForm, ValidationForm
from registration_validation.models import Activity, ActivityType, Evidence, EvidenceFile, Validation


class FelicitacionesFormalesTests(TestCase):
    def setUp(self):
        now = timezone.localdate()
        self.delegation = Delegation.objects.create(
            name="Delegación felicitaciones", status="Active", scope="Urbana",
        )
        self.position = PositionFunction.objects.create(
            position_name="Gestor felicitaciones", measurable_items="Atenciones",
            services="Atención", weightings="100",
            validity_start=date(now.year - 1, 1, 1),
            validity_end=date(now.year + 1, 12, 31),
        )
        self.author = Employee.objects.create(
            name="Funcionario autor", delegation=self.delegation,
            position=self.position, status="Active", roles="Funcionario",
        )
        self.delegate = Employee.objects.create(
            name="Delegado validador", delegation=self.delegation,
            position=self.position, status="Active", roles="Delegado",
        )
        self.delegation.responsible = self.delegate
        self.delegation.save(update_fields=["responsible", "updated_at"])
        self.delegate_user = get_user_model().objects.create_user(
            username="delegado-felicitaciones", password="Prueba123!",
        )
        self.normal_user = get_user_model().objects.create_user(
            username="normal-felicitaciones", password="Prueba123!",
        )
        p = Permission.objects.get(
            content_type__app_label="registration_validation",
            codename="add_validation",
        )
        for user, employee in ((self.delegate_user, self.delegate), (self.normal_user, self.author)):
            user.user_permissions.add(p)
            profile = UserProfile.objects.create(
                user=user, employee=employee,
                employee_code=f"FELIC-{employee.pk}", delegation=self.delegation,
            )
            profile.authorized_delegations.add(self.delegation)
        self.period = Period.objects.create(
            start_date=date(now.year, 1, 1),
            end_date=date(now.year, 12, 31),
            status="Active", computable_days=200,
            thresholds="Verde: 100, Amarillo: 80, Rojo: 60, Tope: 120",
            parameters_version="v1",
        )
        self.goal = Goal.objects.create(
            period=self.period, employee=self.author,
            position=self.position, item="Felicitaciones", objective_value=1,
            unit="unidades", weight=100,
        )
        self.kind = ActivityType.objects.create(
            code="FELIC-PRUEBA", name="Reconocimiento ciudadano",
            is_congratulation=True, is_preparatory_coordination=False,
        )
        self.activity = Activity.objects.create(
            goal=self.goal, author=self.author, activity_type=self.kind,
            date=now, contact="Ciudadano solicitante", phone="912345678",
            request_problem="Felicitación", action="Reconocimiento al funcionario",
        )
        link_resolved_attention(self.activity)
        self.evidence = Evidence.objects.create(
            activity=self.activity, author=self.author,
            date=timezone.now(), review_status="Pending",
        )
        # Referencia a un archivo de prueba, sin escribir archivos físicos.
        EvidenceFile.objects.create(
            evidence=self.evidence, file="evidences/test_carta_felicitacion.pdf",
        )

    def data(self, *, endorsement=False, verifier=None, decision="Approved", result="Approved", observation="Carta firmada y verificada"):
        return {
            "evidence": str(self.evidence.pk),
            "verifier": str((verifier or self.delegate).pk),
            "decision": decision, "result": result, "version": "1",
            "observation": observation,
            **({"formal_delegate_endorsement": "on"} if endorsement else {}),
        }

    def test_felicitacion_aprobada_sin_aval_no_suma(self):
        Validation.objects.create(
            evidence=self.evidence, verifier=self.delegate,
            decision="Approved", result="Approved", date=timezone.now(),
        )
        self.assertTrue(_evidence_is_approved(self.evidence))
        self.assertFalse(activity_qualifies_for_goal(self.activity, _evidence_is_approved))
        self.assertEqual(recalculate_indicator_for_goal(self.goal).actual_progress, Decimal("0"))

    def test_no_puede_fingir_el_delegado_seleccionando_su_nombre(self):
        form = ValidationForm(data=self.data(endorsement=True), user=self.normal_user)
        self.assertFalse(form.is_valid())
        self.assertIn("formal_delegate_endorsement", form.errors)

    def test_aval_firmado_por_delegado_suma_con_evidencia_aprobada(self):
        form = ValidationForm(data=self.data(endorsement=True), user=self.delegate_user)
        self.assertTrue(form.is_valid(), form.errors)
        validation = form.save(commit=False)
        validation.date = timezone.now()
        validation.save()
        self.assertTrue(validation.formal_delegate_endorsement)
        self.assertEqual(validation.delegate_endorsed_by_id, self.delegate_user.pk)
        self.assertIsNotNone(validation.delegate_endorsed_at)
        self.assertTrue(activity_qualifies_for_goal(self.activity, _evidence_is_approved))
        self.assertEqual(recalculate_indicator_for_goal(self.goal).actual_progress, Decimal("1"))
        # Renombrar el tipo no altera su clasificación.
        self.kind.name = "Reconocimiento extraordinario"
        self.kind.save()
        self.activity.refresh_from_db()
        self.assertTrue(activity_qualifies_for_goal(self.activity, _evidence_is_approved))

    def test_aval_requiere_fundamento_y_documento(self):
        without_reason = ValidationForm(
            data=self.data(endorsement=True, observation=""), user=self.delegate_user,
        )
        self.assertFalse(without_reason.is_valid())
        self.evidence.files.all().delete()
        without_file = ValidationForm(
            data=self.data(endorsement=True), user=self.delegate_user,
        )
        self.assertFalse(without_file.is_valid())
        self.assertIn("formal_delegate_endorsement", without_file.errors)

    def test_aprobacion_normal_no_convierte_en_aval_formal(self):
        form = ValidationForm(data=self.data(), user=self.normal_user)
        self.assertTrue(form.is_valid(), form.errors)
        validation = form.save(commit=False)
        validation.date = timezone.now()
        validation.save()
        self.assertFalse(validation.formal_delegate_endorsement)
        self.assertFalse(activity_qualifies_for_goal(self.activity, _evidence_is_approved))

    def test_tipo_preparatorio_y_felicitacion_no_pueden_coexistir(self):
        form = ActivityTypeForm(data={
            "code": "TIPO-ERRONEO", "name": "Categoría contradictoria",
            "status": "True", "is_preparatory_coordination": "on",
            "is_congratulation": "on",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("is_congratulation", form.errors)

    def test_nombres_no_clasifican_por_si_solos(self):
        item = ActivityType.objects.create(
            code="NOMBRE-FELIC", name="Felicitación ciudadana",
            is_congratulation=False,
        )
        self.activity.activity_type = item
        self.activity.save(update_fields=["activity_type", "updated_at"])
        self.assertTrue(activity_qualifies_for_goal(self.activity, _evidence_is_approved))

    def test_aval_formal_ya_firmado_no_se_puede_alterar(self):
        form = ValidationForm(data=self.data(endorsement=True), user=self.delegate_user)
        self.assertTrue(form.is_valid(), form.errors)
        validation = form.save(commit=False)
        validation.date = timezone.now()
        validation.save()
        validation.observation = "Cambiar respaldo antiguo"
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            validation.save()

    def test_cambiar_clasificacion_recalcula_meta_activa(self):
        Validation.objects.create(
            evidence=self.evidence, verifier=self.delegate,
            decision="Approved", result="Approved", date=timezone.now(),
        )
        self.assertEqual(recalculate_indicator_for_goal(self.goal).actual_progress, Decimal("0"))
        self.kind.is_congratulation = False
        self.kind.save(update_fields=["is_congratulation", "updated_at"])
        self.assertEqual(recalculate_indicator_for_goal(self.goal).actual_progress, Decimal("1"))
        self.kind.is_congratulation = True
        self.kind.save(update_fields=["is_congratulation", "updated_at"])
        self.assertEqual(recalculate_indicator_for_goal(self.goal).actual_progress, Decimal("0"))

    def test_aval_permanece_registrado_tras_cambio_de_responsable(self):
        form = ValidationForm(data=self.data(endorsement=True), user=self.delegate_user)
        self.assertTrue(form.is_valid(), form.errors)
        validation = form.save(commit=False)
        validation.date = timezone.now()
        validation.save()
        self.delegation.responsible = None
        self.delegation.save(update_fields=["responsible", "updated_at"])
        self.assertEqual(recalculate_indicator_for_goal(self.goal).actual_progress, Decimal("1"))
        validation.refresh_from_db()
        self.assertEqual(validation.delegate_endorsed_by_id, self.delegate_user.pk)
