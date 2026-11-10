"""RUT del mismo caso y privacidad del cambio de correo de seguimiento."""
import re
from urllib.parse import urlsplit
from datetime import date
from django.core import mail
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase, override_settings
from django.urls import reverse
from accounts.models import UserProfile
from organization.models import Delegation, Employee, OrganizationRole, PositionFunction
from registration_validation.models import AttentionEntry, AttentionType, SubAttention
from citizen_registry.models import Citizen
from citizen_requests.models import CitizenRequest

@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    PUBLIC_PORTAL_URL="http://127.0.0.1:8000/portal/",
    DEBUG=True,
)
class TestChangeCitizenAndVerifyEmail(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.delegation=Delegation.objects.create(code="RUTV",name="Delegación RUT",status="Active",scope="Urbana",commune="La Serena")
        position=PositionFunction.objects.create(position_name="RUT",measurable_items="Atenciones",services="Servicio",weightings="100",validity_start=date(2026,1,1),validity_end=date(2027,12,31))
        cls.employee=Employee.objects.create(name="Funcionario",delegation=cls.delegation,position=position,roles="Atención",status="Active")
        cls.attention_type=AttentionType.objects.create(code="RUTVA",name="Social",status=True)
        cls.sub_attention=SubAttention.objects.create(code="RUTVS",name="Consulta",attention_type=cls.attention_type,status=True)
        cls.user=get_user_model().objects.create_user(username="rut_verifier",password="12345")
        profile=UserProfile.objects.create(user=cls.user,employee_code="RUTV",delegation=cls.delegation,employee=cls.employee)
        profile.authorized_delegations.add(cls.delegation)
        group=Group.objects.create(name="RUT verification")
        role=OrganizationRole.objects.create(group=group,delegation=cls.delegation)
        role.application_delegations.add(cls.delegation)
        group.permissions.add(*Permission.objects.filter(content_type__app_label="registration_validation",codename__in=["view_attentionentry","add_attentionentry","change_attentionentry"]))
        group.permissions.add(Permission.objects.get(content_type__app_label="citizen_registry",codename="view_citizen"))
        cls.user.groups.add(group)
        cls.old=Citizen.objects.create(rut="11111111-1",full_name="Juan",email="juan@example.com",address="Calle A")
        cls.new=Citizen.objects.create(rut="12345678-5",full_name="María",email="maria@example.com",address="Calle B")

    def setUp(self):
        self.client.force_login(self.user)
        self.attention=AttentionEntry.objects.create(
            citizen=self.old,requester=self.old.full_name,requester_email=self.old.email,requester_phone="",address=self.old.address,
            subject="Caso de prueba", description="Detalle del caso",attention_type=self.attention_type,sub_attention=self.sub_attention,
            delegation=self.delegation,responsible_employee=self.employee,status="IN_PROGRESS",registered_by=self.user,
        )
        self.case=CitizenRequest.objects.create(
            citizen=self.old,origin="INTERNAL",requester_name=self.old.full_name,requester_email=self.old.email,
            requester_phone="",address=self.old.address,subject="Caso de prueba",description="Detalle del caso",
            delegation=self.delegation,attention_entry=self.attention,status="IN_PROGRESS",tracking_code=self.attention.tracking_code,
        )

    def url(self):
        return reverse("registration:attention_entry_update",args=[self.attention.pk])

    def payload(self, **additional):
        return {
            "requester":"Manipulado", "requester_email":"intruso@example.com", "requester_phone":"5555", "address":"Falso",
            "subject":"Caso de prueba", "description":"Detalle del caso",
            "delegation":self.delegation.pk,"responsible_employee":self.employee.pk,
            "attention_type":self.attention_type.pk,"sub_attention":self.sub_attention.pk,
            "status":"IN_PROGRESS", "citizen_rut":self.new.rut, **additional,
        }

    def change_rut(self):
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            result=self.client.post(self.url(),self.payload(confirm_citizen_change="on"))
        self.assertEqual(result.status_code,302)
        self.case.refresh_from_db(); self.attention.refresh_from_db()

    def verification_url(self):
        msg=mail.outbox[-1]
        link=re.search(r'https?://[^\s]+',msg.body).group(0)
        return urlsplit(link).path

    def test_change_requires_confirmation_and_updates_both(self):
        result=self.client.post(self.url(),self.payload())
        self.assertEqual(result.status_code,200)
        self.case.refresh_from_db();self.attention.refresh_from_db()
        self.assertEqual(self.case.citizen_id,self.old.pk)
        self.assertEqual(self.attention.citizen_id,self.old.pk)
        self.change_rut()
        self.assertEqual(self.case.citizen_id,self.new.pk)
        self.assertEqual(self.attention.citizen_id,self.new.pk)
        self.assertEqual(self.case.original_citizen_id,self.old.pk)
        self.assertEqual(self.case.requester_email,self.old.email)  # snapshot inmutable
        self.assertTrue(self.case.followup_email_paused)
        self.assertEqual(self.case.followup_recipient,"")
        self.assertTrue(self.case.events.filter(observation__contains="Anterior: ").exists())
        detail=self.client.get(reverse("citizen_requests:request_detail",args=[self.case.pk])).json()["request"]
        self.assertEqual(detail["original_rut"],self.old.rut)
        self.assertEqual(detail["current_rut"],self.new.rut)
        self.assertEqual(len(mail.outbox),1)
        self.assertEqual(mail.outbox[0].to,[self.new.email])
        self.assertNotIn(str(self.case.tracking_code),mail.outbox[0].body)
        self.assertNotIn(self.case.subject,mail.outbox[0].body)

    def test_verify_once_then_new_notifications_not_old(self):
        self.change_rut()
        link=self.verification_url()
        self.assertEqual(self.client.get(link).status_code,200)
        self.assertEqual(self.case.followup_recipient,"")
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post(link).status_code,200)
        self.case.refresh_from_db()
        self.assertEqual(self.case.followup_recipient,self.new.email)
        self.assertEqual(mail.outbox[-1].to,[self.new.email])
        self.assertIn(str(self.case.tracking_code),mail.outbox[-1].body)
        self.assertEqual(self.client.post(link).status_code,400)
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post(self.url(),self.payload(citizen_rut=self.new.rut,status="RESOLVED",closing_observation="Solucionado")).status_code,302)
        self.assertEqual(len(mail.outbox),1)
        self.assertEqual(mail.outbox[0].to,[self.new.email])
        self.assertNotIn(self.old.email,mail.outbox[0].to)

    def test_new_status_email_uses_current_citizen_name(self):
        self.change_rut()
        link = self.verification_url()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post(link).status_code, 200)
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            result = self.client.post(self.url(), self.payload(
                citizen_rut=self.new.rut, status="RESOLVED",
                closing_observation="Se realizó la gestión",
            ))
        self.assertEqual(result.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.new.email])
        self.assertIn(f"Estimado/a {self.new.full_name}:", mail.outbox[0].body)
        self.assertNotIn(f"Estimado/a {self.old.full_name}:", mail.outbox[0].body)
        self.case.refresh_from_db()
        self.assertEqual(self.case.requester_name, self.old.full_name)  # histórico intacto

    def test_rut_confirmation_uses_sweetalert2_not_browser_confirm(self):
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'title: "¿Confirmar cambio de ciudadano?"')
        self.assertContains(response, 'confirmButtonText: "Sí, cambiar ciudadano"')
        self.assertNotContains(response, 'window.confirm("Vas a cambiar el ciudadano vinculado')

    def test_paused_does_not_notify_old_even_when_status_changes(self):
        self.change_rut()
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            r=self.client.post(self.url(),self.payload(citizen_rut=self.new.rut,status="RESOLVED",closing_observation="Solucionado"))
        self.assertEqual(r.status_code,302)
        self.assertEqual(len(mail.outbox),0)

    def test_resend_invalidates_first_link(self):
        self.change_rut()
        old_link=self.verification_url()
        with self.captureOnCommitCallbacks(execute=True):
            response=self.client.post(self.url(),{"action":"resend_email_verification"})
        self.assertEqual(response.status_code,302)
        self.assertEqual(len(mail.outbox),2)
        new_link=self.verification_url()
        self.assertNotEqual(old_link,new_link)
        self.assertEqual(self.client.post(old_link).status_code,400)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post(new_link).status_code,200)

    def test_previous_citizen_cannot_see_history_after_rut_correction(self):
        from citizen_requests.history import SESSION_VERIFIED
        self.change_rut()
        session=self.client.session
        session[SESSION_VERIFIED]={"email":self.old.email,"verified_at":__import__('time').time()}
        session.save()
        r=self.client.get(reverse("citizen_requests:public_request_history"))
        self.assertNotContains(r,str(self.case.tracking_code))
        link=self.verification_url()
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(link)
        session=self.client.session
        session[SESSION_VERIFIED]={"email":self.new.email,"verified_at":__import__('time').time()}
        session.save()
        r=self.client.get(reverse("citizen_requests:public_request_history"))
        self.assertContains(r,str(self.case.tracking_code))
        self.assertContains(r,self.new.full_name)
        self.assertNotContains(r,self.old.full_name)
