"""Pruebas del cierre semanal por delegación, sin cuentas superusuario."""
from datetime import date, datetime, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from organization.models import Delegation, Employee, OrganizationRole, PositionFunction
from .models import CitizenRequest, CitizenRequestAction
from .weekly_models import CitizenRequestActionWeek, CitizenRequestActionWeekEvent
from .weekly_rules import manage_week, start_of_week
from organization.permission_labels import catalog_permission_queryset


class WeeklyClosureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.delegation = Delegation.objects.create(
            code="TEST-WEEK-NORTH", name="Delegación Test", status="Active", scope="Local",
        )
        cls.other_delegation = Delegation.objects.create(
            code="TEST-WEEK-SOUTH", name="Delegación Ajena", status="Active", scope="Local",
        )
        cls.position = PositionFunction.objects.create(
            position_name="Gestiones Test", measurable_items="Gestiones", services="Gestiones",
            weightings="100", validity_start=date(2026, 1, 1), validity_end=date(2028, 12, 31),
        )
        cls.employee = Employee.objects.create(
            name="Funcionario Test", delegation=cls.delegation, position=cls.position,
            roles="Gestión", status="Active",
        )
        cls.user = get_user_model().objects.create_user(
            username="gestiones_week_admin", password="TestStrong!9271",
        )
        cls.profile = UserProfile.objects.create(
            user=cls.user, employee_code="WEEK-USER-1", delegation=cls.delegation,
        )
        cls.profile.authorized_delegations.add(cls.delegation)
        cls.group = Group.objects.create(name="Rol prueba cierre semanal")
        OrganizationRole.objects.create(group=cls.group, delegation=cls.delegation)
        cls.group.permissions.add(*Permission.objects.filter(
            content_type__app_label="citizen_requests",
            codename__in=[
                "view_citizenrequestaction", "add_citizenrequestaction",
                "change_citizenrequestaction", "manage_citizenrequestaction_week",
            ],
        ))
        cls.user.groups.add(cls.group)
        cls.outsider = get_user_model().objects.create_user(
            username="gestiones_week_outsider", password="TestStrong!9271",
        )
        outsider_profile = UserProfile.objects.create(
            user=cls.outsider, employee_code="WEEK-USER-2", delegation=cls.other_delegation,
        )
        outsider_profile.authorized_delegations.add(cls.other_delegation)
        cls.request = CitizenRequest.objects.create(
            origin="INTERNAL", requester_name="Vecino Ficticio",
            requester_email="", address="Calle de prueba 10",
            subject="Solicitud de prueba", description="Prueba de gestiones",
            delegation=cls.delegation,
        )
        cls.previous_week = start_of_week(timezone.localdate()) - timedelta(days=7)
        cls.previous_date = timezone.make_aware(
            datetime.combine(cls.previous_week + timedelta(days=2), datetime.min.time().replace(hour=12)),
            timezone.get_current_timezone(),
        )

    def create_action(self, performed_at=None):
        payload = dict(
            request=self.request, responsible=self.employee,
            delegation=self.delegation, registered_by=self.user,
            action_type="INSPECTION", performed_at=performed_at or self.previous_date,
            description="Realizó una visita de prueba", outcome="Resultado de prueba",
        )
        # Compatibilidad con la ampliación local del modelo de gestiones.
        names = {field.name for field in CitizenRequestAction._meta.fields}
        for name in ("executor_type", "execution_status"):
            if name in names:
                field = CitizenRequestAction._meta.get_field(name)
                payload[name] = next((key for key, _ in field.flatchoices if key), field.get_default())
        if "executor_name" in names:
            payload["executor_name"] = "Funcionario Test"
        if "executor_contact" in names:
            payload["executor_contact"] = "Fono de prueba"
        return CitizenRequestAction.objects.create(**payload)

    def test_permission_visible_in_roles_catalog(self):
        perm = Permission.objects.get(
            content_type__app_label="citizen_requests",
            codename="manage_citizenrequestaction_week",
        )
        self.assertTrue(catalog_permission_queryset(Permission.objects.all()).filter(pk=perm.pk).exists())

    def test_closed_week_blocks_new_actions_and_preserves_existing(self):
        historical = self.create_action()
        manage_week(delegation_id=self.delegation.pk, monday=self.previous_week,
                    action="close", actor=self.user)
        historical.refresh_from_db()
        self.assertEqual(historical.description, "Realizó una visita de prueba")
        with self.assertRaises(ValidationError):
            self.create_action()
        with self.assertRaises(ValidationError):
            historical.description = "Alteración después del cierre"
            historical.save()

    def test_reopening_requires_reason_and_retains_audit(self):
        manage_week(delegation_id=self.delegation.pk, monday=self.previous_week,
                    action="close", actor=self.user)
        with self.assertRaises(ValidationError):
            manage_week(delegation_id=self.delegation.pk, monday=self.previous_week,
                        action="reopen", actor=self.user, reason="")
        manage_week(delegation_id=self.delegation.pk, monday=self.previous_week,
                    action="reopen", actor=self.user, reason="Gestión pendiente documentada")
        self.assertFalse(CitizenRequestActionWeek.objects.get(delegation=self.delegation).is_closed)
        self.assertEqual(list(CitizenRequestActionWeekEvent.objects.values_list("action",flat=True)),
                         ["REOPEN", "CLOSE"])
        self.create_action()
        manage_week(delegation_id=self.delegation.pk, monday=self.previous_week,
                    action="close", actor=self.user)
        self.assertEqual(CitizenRequestActionWeekEvent.objects.count(),3)

    def test_cannot_close_current_or_future_week(self):
        with self.assertRaises(ValidationError):
            manage_week(delegation_id=self.delegation.pk,
                        monday=start_of_week(timezone.localdate()), action="close", actor=self.user)
        with self.assertRaises(ValidationError):
            manage_week(delegation_id=self.delegation.pk,
                        monday=self.previous_week + timedelta(days=1), action="close", actor=self.user)

    def test_modal_and_post_with_normal_user(self):
        self.client.force_login(self.user)
        url = reverse("citizen_requests:request_action_list",args=[self.request.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code,200)
        self.assertContains(response,"Gestionar cierre semanal de gestiones")
        manage_url = reverse("citizen_requests:manage_request_action_week",args=[self.request.pk])
        response = self.client.post(manage_url,{
            "operation":"close", "week_start":self.previous_week.isoformat(),
        })
        self.assertRedirects(response,url)
        self.assertTrue(CitizenRequestActionWeek.objects.get(delegation=self.delegation).is_closed)
        response = self.client.post(manage_url,{
            "operation":"reopen", "week_start":self.previous_week.isoformat(), "reason":"",
        })
        self.assertRedirects(response,url)
        self.assertTrue(CitizenRequestActionWeek.objects.get(delegation=self.delegation).is_closed)
        response = self.client.post(manage_url,{
            "operation":"reopen", "week_start":self.previous_week.isoformat(),
            "reason":"Reapertura validada en pruebas",
        })
        self.assertRedirects(response,url)
        self.assertFalse(CitizenRequestActionWeek.objects.get(delegation=self.delegation).is_closed)

    def test_user_without_permission_cannot_close_by_url(self):
        self.client.force_login(self.outsider)
        url=reverse("citizen_requests:manage_request_action_week",args=[self.request.pk])
        response=self.client.post(url,{"operation":"close","week_start":self.previous_week.isoformat()})
        self.assertEqual(response.status_code,403)
        self.assertFalse(CitizenRequestActionWeek.objects.exists())

    def test_closed_action_cannot_be_edited_by_direct_url(self):
        action=self.create_action()
        manage_week(delegation_id=self.delegation.pk,monday=self.previous_week,
                    action="close",actor=self.user)
        self.client.force_login(self.user)
        url=reverse("citizen_requests:edit_request_action",args=[self.request.pk, action.pk])
        self.assertEqual(self.client.get(url).status_code,403)
