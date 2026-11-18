"""Pruebas de regresión del flujo restringido de compromisos del SGR."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from organization.models import Delegation, Employee, PositionFunction
from planning_measurements.models import Goal, Period
from registration_validation.models import Activity

from .forms import CommitmentReassignmentForm
from .models import Commitment, CommitmentReassignment
from .views import _commitment_can_be_reassigned
from organization.permission_labels import permission_label


class CompromisosSinEdicionGeneralTest(TestCase):
    def setUp(self):
        self.delegation = Delegation.objects.create(
            name="Delegación de pruebas SGR", status="Active", scope="Local"
        )
        self.position = PositionFunction.objects.create(
            position_name="Cargo SGR de pruebas",
            measurable_items="Atenciones",
            services="Atención",
            weightings="100",
            validity_start=timezone.localdate() - timedelta(days=365),
            validity_end=timezone.localdate() + timedelta(days=365),
        )
        self.employee = Employee.objects.create(
            delegation=self.delegation,
            position=self.position,
            name="Funcionario titular SGR",
            roles="Funcionario",
            status="Active",
        )
        self.replacement = Employee.objects.create(
            delegation=self.delegation,
            position=self.position,
            name="Funcionario reemplazo SGR",
            roles="Funcionario",
            status="Active",
        )
        self.commitment = Commitment.objects.create(
            delegation=self.delegation,
            responsible=self.employee,
            origin="Origen original",
            requester="Vecino",
            territory="Territorio original",
            commitment_date=timezone.localdate() + timedelta(days=20),
            status=Commitment.Status.PENDING,
            support="Apoyo original",
        )
        self.user = get_user_model().objects.create_user(
            username="prueba_compromisos_restringidos",
            password="clave-prueba",
        )
        UserProfile.objects.create(
            user=self.user,
            delegation=self.delegation,
            employee_code="SGR-COMPROMISOS-TEST",
        )
        perms = Permission.objects.filter(
            content_type__app_label="monitoring_traceability",
            codename__in=("view_commitment", "change_commitment"),
        )
        self.user.user_permissions.add(*perms)
        self.client.force_login(self.user)
        self.url = reverse("monitoring:commitment_list")

    def test_antiguo_enlace_y_envio_de_modificacion_rechazados(self):
        old_edit_url = reverse(
            "monitoring:commitment_edit",
            args=[self.commitment.pk],
        )
        self.assertEqual(self.client.get(old_edit_url).status_code, 403)
        self.assertEqual(
            self.client.get(self.url, {"open_modal": "edit", "commitment_id": self.commitment.pk}).status_code,
            403,
        )
        response = self.client.post(self.url, {
            "action": "edit_commitment",
            "commitment_id": self.commitment.pk,
            "territory": "Valor manipulado",
            "support": "Valor manipulado",
        })
        self.assertEqual(response.status_code, 403)
        self.commitment.refresh_from_db()
        self.assertEqual(self.commitment.territory, "Territorio original")
        self.assertEqual(self.commitment.support, "Apoyo original")

    def test_ausencia_permite_reasignar_antes_de_vencer_y_deja_historial(self):
        # Si el funcionario sigue activo, no se muestra botón ni se acepta una petición directa.
        self.assertFalse(_commitment_can_be_reassigned(self.commitment))
        self.assertFalse(self.commitment.is_overdue)
        response = self.client.get(self.url, {
            "open_modal": "reassign", "commitment_id": self.commitment.pk,
        })
        self.assertEqual(response.status_code, 403)
        denied = self.client.post(self.url, {
            "action": "reassign", "commitment_id": self.commitment.pk,
            "cause": "absence", "responsible": self.replacement.pk,
            "reason": "Ausencia no registrada",
        })
        self.assertEqual(denied.status_code, 403)
        self.assertFalse(self.commitment.reassignments.exists())

        # Solo cuando Organización registra la licencia la reasignación se habilita.
        self.employee.status = "On leave"
        self.employee.save(update_fields=["status", "updated_at"])
        self.commitment.refresh_from_db()
        self.assertTrue(_commitment_can_be_reassigned(self.commitment))
        page = self.client.get(self.url)
        self.assertContains(page, "Funcionario con licencia")
        self.assertContains(page, "Reasignar responsable")
        response = self.client.get(self.url, {
            "open_modal": "reassign", "commitment_id": self.commitment.pk,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ausencia del funcionario")
        self.assertNotContains(response, "Modificar</a>")
        response = self.client.post(self.url, {
            "action": "reassign", "commitment_id": self.commitment.pk,
            "cause": "absence", "responsible": self.replacement.pk,
            "reason": "Licencia registrada en Organización; requiere suplencia",
        })
        self.assertEqual(response.status_code, 302)
        self.commitment.refresh_from_db()
        self.assertEqual(self.commitment.responsible_id, self.replacement.pk)
        entry = CommitmentReassignment.objects.get(commitment=self.commitment)
        self.assertEqual(entry.previous_responsible_id, self.employee.pk)
        self.assertEqual(entry.new_responsible_id, self.replacement.pk)
        self.assertEqual(entry.changed_by_id, self.user.pk)
        self.assertIn("Ausencia del funcionario", entry.reason)
        self.assertIn("requiere suplencia", entry.reason)

    def test_inactivo_habilita_reasignacion_anticipada(self):
        from organization.forms import EMPLOYEE_STATUS_CHOICES
        self.assertIn(("On leave", "Con licencia"), EMPLOYEE_STATUS_CHOICES)
        self.employee.status = "Inactive"
        self.employee.save(update_fields=["status", "updated_at"])
        self.commitment.refresh_from_db()
        self.assertTrue(_commitment_can_be_reassigned(self.commitment))
        response = self.client.get(self.url, {
            "open_modal": "reassign", "commitment_id": self.commitment.pk,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ausencia del funcionario")
        self.assertContains(response, "Funcionario inactivo")

    def test_compromiso_vencido_de_funcionario_activo_permite_solo_causa_vencimiento(self):
        self.commitment.commitment_date = timezone.localdate() - timedelta(days=1)
        self.commitment.save(update_fields=["commitment_date", "updated_at"])
        self.assertTrue(_commitment_can_be_reassigned(self.commitment))
        form = CommitmentReassignmentForm(
            employees=Employee.objects.filter(pk=self.replacement.pk),
            is_overdue=True, employee_unavailable=False,
        )
        self.assertEqual([choice[0] for choice in form.fields["cause"].choices], ["overdue"])
        response = self.client.post(self.url, {
            "action": "reassign", "commitment_id": self.commitment.pk,
            "cause": "absence", "responsible": self.replacement.pk,
            "reason": "Intento de declarar ausencia sin registrarla",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.commitment.reassignments.exists())

    def test_vencimiento_no_es_opcion_si_aun_no_vencio(self):
        form = CommitmentReassignmentForm(
            data={
                "cause": "overdue",
                "responsible": self.replacement.pk,
                "reason": "No corresponde declarar vencimiento",
            },
            employees=Employee.objects.filter(pk=self.replacement.pk),
            is_overdue=False,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("cause", form.errors)

    def test_no_se_reasigna_un_compromiso_finalizado(self):
        self.commitment.status = Commitment.Status.COMPLETED
        self.commitment.save(update_fields=["status", "updated_at"])
        self.assertFalse(_commitment_can_be_reassigned(self.commitment))
        response = self.client.get(self.url, {
            "open_modal": "reassign", "commitment_id": self.commitment.pk,
        })
        self.assertEqual(response.status_code, 403)
        response = self.client.post(self.url, {
            "action": "reassign",
            "commitment_id": self.commitment.pk,
            "cause": "absence",
            "responsible": self.replacement.pk,
            "reason": "No se permite",
        })
        self.assertEqual(response.status_code, 403)
        self.commitment.refresh_from_db()
        self.assertEqual(self.commitment.responsible_id, self.employee.pk)

    def test_listado_identifica_actividad_y_meta_real(self):
        period = Period.objects.create(
            start_date=timezone.localdate() - timedelta(days=10),
            end_date=timezone.localdate() + timedelta(days=60),
            computable_days=50,
            thresholds="Green >= 90",
            parameters_version="1.0",
        )
        goal = Goal.objects.create(
            period=period,
            employee=self.employee,
            position=self.position,
            item="Meta asociada de prueba",
            objective_value=10,
            unit="atenciones",
            weight=100,
        )
        activity = Activity.objects.create(
            goal=goal,
            author=self.employee,
            date=timezone.localdate(),
            request_problem="Solicitud de ejemplo",
            action="Actividad registrada de prueba",
            contact="Vecino",
            phone="123456789",
        )
        self.commitment.activity = activity
        self.commitment.save(update_fields=["activity", "updated_at"])
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Actividad registrada de prueba")
        self.assertContains(response, "Meta asociada de prueba")
        self.assertNotContains(response, "Modificar</a>")

    def test_permiso_conservado_con_nombre_operativo(self):
        permission = Permission.objects.get(
            content_type__app_label="monitoring_traceability",
            codename="change_commitment",
        )
        self.assertIn("reasignar responsables", permission_label(permission))
        self.assertIn("actualizar estados", permission_label(permission))
