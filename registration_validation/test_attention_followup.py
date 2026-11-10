"""Seguimiento completo de atenciones, sin nuevos permisos ni migraciones."""
from datetime import date
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from accounts.models import UserProfile
from organization.models import Delegation, Employee, OrganizationRole, PositionFunction
from citizen_requests.models import CitizenRequest, RequestEvent
from registration_validation.models import AttentionEntry, AttentionType, SubAttention
from citizen_registry.models import Citizen


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AttentionFollowupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.delegation = Delegation.objects.create(
            code="FUP1", name="Delegación de pruebas", status="Active", scope="Urbana",
            commune="La Serena")
        cls.position = PositionFunction.objects.create(
            position_name="Atención FUP", measurable_items="Atenciones", services="Servicio",
            weightings="100", validity_start=date(2026,1,1), validity_end=date(2027,12,31))
        cls.employee = Employee.objects.create(
            name="Responsable FUP", delegation=cls.delegation, position=cls.position,
            roles="Atención", status="Active")
        cls.attention_type = AttentionType.objects.create(code="FUPA", name="Social FUP", status=True)
        cls.sub_attention = SubAttention.objects.create(
            code="FUPS", name="Orientación FUP", attention_type=cls.attention_type, status=True)
        cls.user = get_user_model().objects.create_user(username="atencion_fup", password="test-pass-123")
        profile = UserProfile.objects.create(
            user=cls.user, employee_code="FUP1", delegation=cls.delegation, employee=cls.employee)
        profile.authorized_delegations.add(cls.delegation)
        group = Group.objects.create(name="Seguimiento FUP")
        role = OrganizationRole.objects.create(group=group, delegation=cls.delegation)
        role.application_delegations.add(cls.delegation)
        group.permissions.add(*Permission.objects.filter(
            content_type__app_label="registration_validation",
            codename__in=["view_attentionentry","add_attentionentry","change_attentionentry","delete_attentionentry"]))
        cls.user.groups.add(group)

    def setUp(self):
        self.client.force_login(self.user)

    def payload(self, email="vecino@example.com", status=None, observation=""):
        d={"requester":"Vecina FUP", "requester_email":email, "requester_phone":"123456",
           "address":"Dirección de prueba", "subject":"Solicitud", "description":"Descripción",
           "attention_type":self.attention_type.pk, "sub_attention":self.sub_attention.pk,
           "delegation":self.delegation.pk, "responsible_employee":self.employee.pk}
        if status is not None: d["status"]=status
        if observation: d["closing_observation"]=observation
        return d

    def create_manual(self, email="vecino@example.com"):
        with self.captureOnCommitCallbacks(execute=True):
            result=self.client.post(reverse("registration:attention_entry_create"), self.payload(email))
        self.assertEqual(result.status_code,302)
        a=AttentionEntry.objects.get(requester="Vecina FUP")
        return a,CitizenRequest.objects.get(attention_entry=a)

    def test_creation_from_request_keeps_original_contact_and_edits_case(self):
        original = CitizenRequest.objects.create(
            origin="CITIZEN", requester_name="Nombre original",
            requester_email="original@example.com", requester_phone="123456",
            address="Dirección original", subject="Asunto original",
            description="Descripción original", delegation=self.delegation,
        )
        new_data = self.payload(email="actualizado@example.com")
        new_data.update({
            "citizen_request": str(original.pk),
            "requester": "Nombre actualizado",
            "requester_phone": "987654",
            "address": "Dirección actualizada",
            "subject": "Asunto actualizado",
            "description": "Descripción actualizada",
        })
        result = self.client.post(reverse("registration:attention_entry_create"), new_data)
        self.assertEqual(result.status_code, 302)
        original.refresh_from_db()
        attention = original.attention_entry
        self.assertEqual(attention.requester, "Nombre original")
        self.assertEqual(attention.requester_email, "original@example.com")
        self.assertEqual(attention.requester_phone, "123456")
        self.assertEqual(attention.address, "Dirección original")
        self.assertEqual(original.requester_name, "Nombre original")
        self.assertEqual(original.requester_email, "original@example.com")
        self.assertEqual(original.requester_phone, "123456")
        self.assertEqual(original.address, "Dirección original")
        data = self.client.get(reverse("citizen_requests:request_detail", args=[original.pk])).json()["request"]
        for key, expected in (
            ("requester_name", "Nombre original"),
            ("requester_email", "original@example.com"),
            ("requester_phone", "123456"),
            ("address", "Dirección original"),
            ("original_requester_name", "Nombre original"),
            ("original_requester_email", "original@example.com"),
            ("original_requester_phone", "123456"),
            ("original_address", "Dirección original"),
        ):
            self.assertEqual(data[key], expected, key)
        items = self.client.get(reverse("citizen_requests:request_inbox")).json()["delegated"]["items"]
        self.assertEqual(next(item for item in items if item["id"] == original.pk)["address"], "Dirección original")
        self.assertContains(self.client.get(reverse("citizen_requests:request_detail", args=[original.pk])), "Nombre original")

    def test_contact_edit_keeps_manual_original_and_notifies_original_email(self):
        attention, original = self.create_manual(email="original@example.com")
        mail.outbox.clear()
        new_type = AttentionType.objects.create(code="FUPB", name="Otro tipo FUP", status=True)
        new_sub = SubAttention.objects.create(code="FUPT", name="Otra sub FUP", attention_type=new_type, status=True)
        data = self.payload(email="nuevo@example.com", status="IN_PROGRESS")
        data.update({
            "requester": "Nombre cambiado", "requester_phone": "555555",
            "address": "Calle distinta", "subject": "Asunto cambiado",
            "description": "Texto cambiado", "attention_type": new_type.pk,
            "sub_attention": new_sub.pk,
        })
        result = self.client.post(reverse("registration:attention_entry_update", args=[attention.pk]), data)
        self.assertEqual(result.status_code, 302)
        attention.refresh_from_db(); original.refresh_from_db()
        self.assertEqual(attention.address, "Dirección de prueba")
        self.assertEqual(attention.requester, "Vecina FUP")
        self.assertEqual(attention.requester_email, "original@example.com")
        self.assertEqual(attention.attention_type_id, new_type.pk)
        self.assertEqual(original.requester_name, "Vecina FUP")
        self.assertEqual(original.requester_email, "original@example.com")
        self.assertEqual(original.address, "Dirección de prueba")
        data_json = self.client.get(reverse("citizen_requests:request_detail", args=[original.pk])).json()["request"]
        self.assertEqual(data_json["attention_type"], "Otro tipo FUP")
        self.assertEqual(data_json["sub_attention"], "Otra sub FUP")
        self.assertEqual(data_json["original_address"], "Dirección de prueba")
        self.assertEqual(data_json["requester_email"], "original@example.com")
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(original.events.filter(observation__icontains="dirección").exists())
        self.assertTrue(original.events.filter(observation__icontains="tipo de atención").exists())
        with self.captureOnCommitCallbacks(execute=True):
            result = self.client.post(reverse("registration:attention_entry_update", args=[attention.pk]),
                                      dict(data, status="RESOLVED", closing_observation="Atendida"))
        self.assertEqual(result.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[-1].to, ["original@example.com"])
        original.refresh_from_db()
        self.assertEqual(original.requester_email, "original@example.com")

    def test_rut_can_correct_attention_link_only_with_valid_existing_citizen(self):
        citizen_old = Citizen.objects.create(rut="11111111-1", full_name="Original", address="Uno")
        citizen_new = Citizen.objects.create(rut="12345678-5", full_name="Actual", address="Dos")
        attention, original = self.create_manual()
        attention.citizen = citizen_old
        attention.save(update_fields=["citizen"])
        original.citizen = citizen_old
        original.save(update_fields=["citizen"])
        self.user.user_permissions.add(Permission.objects.get(
            content_type__app_label="citizen_registry", codename="view_citizen"))
        self.user = get_user_model().objects.get(pk=self.user.pk)
        self.client.force_login(self.user)
        data = self.payload(status="IN_PROGRESS")
        data["citizen_rut"] = citizen_new.rut
        result = self.client.post(reverse("registration:attention_entry_update", args=[attention.pk]), data)
        # Sin confirmación expresa, el servidor NO acepta el cambio.
        self.assertEqual(result.status_code, 200)
        attention.refresh_from_db(); original.refresh_from_db()
        self.assertEqual(attention.citizen_id, citizen_old.pk)
        self.assertEqual(original.citizen_id, citizen_old.pk)
        data["confirm_citizen_change"] = "on"
        result = self.client.post(reverse("registration:attention_entry_update", args=[attention.pk]), data)
        self.assertEqual(result.status_code, 302)
        attention.refresh_from_db(); original.refresh_from_db()
        self.assertEqual(attention.citizen_id, citizen_new.pk)
        self.assertEqual(original.citizen_id, citizen_new.pk)
        self.assertEqual(original.original_citizen_id, citizen_old.pk)
        self.assertTrue(original.followup_email_paused)
        self.assertTrue(original.events.filter(observation__icontains="RUT vinculado").exists())
        displayed = self.client.get(reverse("citizen_requests:request_detail", args=[original.pk])).json()["request"]
        self.assertEqual(displayed["original_rut"], citizen_old.rut)
        self.assertEqual(displayed["current_rut"], citizen_new.rut)
        data["citizen_rut"] = "99999999-9"
        result = self.client.post(reverse("registration:attention_entry_update", args=[attention.pk]), data)
        self.assertEqual(result.status_code, 200)
        attention.refresh_from_db()
        self.assertEqual(attention.citizen_id, citizen_new.pk)

    def test_request_with_citizen_ignores_forged_personal_fields(self):
        citizen = Citizen.objects.create(
            rut="12345678-5", full_name="Nombre del CRUD",
            phone="911111111", email="registro@example.com", address="Dirección CRUD",
        )
        self.user.user_permissions.add(Permission.objects.get(
            content_type__app_label="citizen_registry", codename="view_citizen"))
        self.client.force_login(self.user)
        original = CitizenRequest.objects.create(
            origin="CITIZEN", citizen=citizen,
            requester_name="Nombre original del caso", requester_email="anterior@example.com",
            requester_phone="222", address="Dirección histórica",
            subject="Asunto original", description="Texto original", delegation=self.delegation,
        )
        data = self.payload(email="falso@example.com")
        data.update({
            "citizen_request": str(original.pk), "citizen_rut": citizen.rut,
            "requester": "Nombre falso", "requester_phone": "999", "address": "Falso",
            "subject": "Asunto de la atención", "description": "Texto actualizado",
        })
        result = self.client.post(reverse("registration:attention_entry_create"), data)
        self.assertEqual(result.status_code, 302)
        original.refresh_from_db()
        attention = original.attention_entry
        self.assertEqual(attention.citizen_id, citizen.pk)
        self.assertEqual(attention.requester, citizen.full_name)
        self.assertEqual(attention.requester_email, citizen.email)
        self.assertEqual(attention.requester_phone, citizen.phone)
        self.assertEqual(attention.address, citizen.address)
        self.assertEqual(attention.subject, "Asunto de la atención")
        self.assertEqual(original.requester_name, "Nombre original del caso")
        data = self.client.get(reverse("citizen_requests:request_detail", args=[original.pk])).json()["request"]
        self.assertEqual(data["requester_name"], citizen.full_name)
        self.assertEqual(data["requester_email"], citizen.email)
        self.assertEqual(data["address"], citizen.address)
        self.assertEqual(data["original_address"], "Dirección histórica")

    def test_personal_data_only_changes_through_citizens_crud(self):
        citizen = Citizen.objects.create(
            rut="12345678-5", full_name="Vecino existente", phone="9111",
            email="original-crud@example.com", address="Calle Uno",
        )
        self.user.user_permissions.add(Permission.objects.get(
            content_type__app_label="citizen_registry", codename="view_citizen"))
        self.client.force_login(self.user)
        data = self.payload(email="fraude@example.com")
        data.update({"citizen_rut": citizen.rut, "requester": "Falso", "address": "Dirección falsa"})
        result = self.client.post(reverse("registration:attention_entry_create"), data)
        self.assertEqual(result.status_code, 302)
        attention = AttentionEntry.objects.get(citizen=citizen)
        request_obj = CitizenRequest.objects.get(attention_entry=attention)
        self.assertEqual(attention.requester_email, citizen.email)
        self.assertEqual(attention.address, citizen.address)
        edit_url = reverse("registration:attention_entry_update", args=[attention.pk])
        response = self.client.get(edit_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="citizen_rut"')
        self.assertContains(response, 'readonly')
        fake = self.payload(email="otro-falso@example.com", status="IN_PROGRESS")
        fake.update({"citizen_rut": citizen.rut, "requester": "Otra persona",
                     "requester_phone": "999", "address": "Otra calle",
                     "subject": "Caso corregido"})
        self.assertEqual(self.client.post(edit_url, fake).status_code, 302)
        attention.refresh_from_db()
        self.assertEqual(attention.requester, citizen.full_name)
        self.assertEqual(attention.requester_email, citizen.email)
        self.assertEqual(attention.requester_phone, citizen.phone)
        self.assertEqual(attention.address, citizen.address)
        self.assertEqual(attention.subject, "Caso corregido")
        # Cambio único en el CRUD central de Ciudadanos.
        citizen.address = "Calle Dos"
        citizen.phone = "9888"
        citizen.email = "nuevo-crud@example.com"
        citizen.full_name = "Vecino actualizado"
        citizen.save()
        request_obj.refresh_from_db()
        # No se sustituye la instantánea de contacto original ni el destinatario.
        self.assertEqual(request_obj.requester_email, "original-crud@example.com")
        inbox = self.client.get(reverse("citizen_requests:request_inbox")).json()["delegated"]["items"]
        current = next(item for item in inbox if item["id"] == request_obj.pk)
        self.assertEqual(current["requester_name"], "Vecino actualizado")
        self.assertEqual(current["address"], "Calle Dos")
        detail = self.client.get(reverse("registration:attention_entry_detail", args=[attention.pk])).json()["attention"]
        self.assertEqual(detail["requester"], "Vecino actualizado")
        self.assertEqual(detail["requester_phone"], "9888")
        self.assertEqual(detail["requester_email"], "nuevo-crud@example.com")
        form_page = self.client.get(edit_url)
        self.assertContains(form_page, 'value="Calle Dos"')
        self.assertContains(form_page, 'value="Vecino actualizado"')

    def test_blank_crud_email_does_not_block_status_change_of_portal_attention(self):
        citizen = Citizen.objects.create(
            rut="12345678-5", full_name="Persona", email="verificado@example.com",
            address="Dirección original",
        )
        self.user.user_permissions.add(Permission.objects.get(
            content_type__app_label="citizen_registry", codename="view_citizen"))
        self.client.force_login(self.user)
        request_obj = CitizenRequest.objects.create(
            origin="CITIZEN", citizen=citizen, requester_name="Persona",
            requester_email="verificado@example.com", address="Dirección original",
            subject="Consulta", description="Consulta portal", delegation=self.delegation,
        )
        payload = self.payload(email="verificado@example.com")
        payload.update({"citizen_request": request_obj.pk, "citizen_rut": citizen.rut})
        response = self.client.post(reverse("registration:attention_entry_create"), payload)
        self.assertEqual(response.status_code, 302)
        request_obj.refresh_from_db()
        attention = request_obj.attention_entry
        citizen.email = ""
        citizen.save()
        mail.outbox.clear()
        change = self.payload(email="", status="RESOLVED", observation="Se resolvió")
        change.update({"citizen_rut": citizen.rut, "requester": citizen.full_name})
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("registration:attention_entry_update", args=[attention.pk]), change)
        self.assertEqual(response.status_code, 302)
        attention.refresh_from_db()
        self.assertEqual(attention.status, "RESOLVED")
        self.assertEqual(attention.requester_email, "verificado@example.com")
        self.assertEqual(mail.outbox[-1].to, ["verificado@example.com"])

    def test_manual_creates_public_tracking_and_sends_one_initial_mail(self):
        a,r=self.create_manual()
        self.assertEqual(a.status,"IN_PROGRESS")
        self.assertEqual(r.origin,"INTERNAL")
        self.assertEqual(r.status,"IN_PROGRESS")
        self.assertEqual(r.delegation_id,self.delegation.pk)
        self.assertEqual(RequestEvent.objects.filter(request=r).count(),3)
        self.assertEqual(len(mail.outbox),1)
        self.assertIn(str(r.tracking_code),mail.outbox[0].body)
        self.assertIn("derivada y en gestión",mail.outbox[0].body)
        result=self.client.post(reverse("citizen_requests:public_portal"),
                                {"tracking_form":"1", "tracking_code":str(r.tracking_code)})
        self.assertEqual(result.status_code,200)
        self.assertContains(result,"En gestión")

    def test_manual_is_visible_in_history_only_after_email_verification(self):
        import re
        from django.core.cache import cache
        cache.clear()
        attention, request_obj = self.create_manual()
        history_url = reverse("citizen_requests:public_request_history")
        initial = self.client.get(history_url)
        self.assertNotContains(initial, str(request_obj.tracking_code))
        response = self.client.post(history_url, {"action": "send", "email": "vecino@example.com"})
        self.assertEqual(response.status_code, 302)
        code = re.search(r"\b\d{6}\b", mail.outbox[-1].body).group(0)
        response = self.client.post(history_url, {"action": "verify", "code": code})
        self.assertEqual(response.status_code, 302)
        self.assertContains(self.client.get(history_url), str(request_obj.tracking_code))

    def test_manual_without_email_has_record_but_no_mail(self):
        a,r=self.create_manual(email="")
        self.assertTrue(r.tracking_code)
        self.assertEqual(len(mail.outbox),0)

    def test_change_to_resolved_then_closed_and_reopen(self):
        a,r=self.create_manual()
        mail.outbox.clear()
        url=reverse("registration:attention_entry_update",args=[a.pk])
        with self.captureOnCommitCallbacks(execute=True):
            result=self.client.post(url,self.payload(status="RESOLVED",observation="Se realizó el trabajo"))
        self.assertEqual(result.status_code,302)
        a.refresh_from_db(); r.refresh_from_db()
        self.assertEqual(a.status,"RESOLVED")
        self.assertEqual(r.status,"IN_PROGRESS")
        self.assertEqual(len(mail.outbox),1)
        self.assertIn("Resuelta",mail.outbox[-1].body)
        self.assertTrue(RequestEvent.objects.filter(request=r,observation__icontains="Se realizó el trabajo").exists())
        self.assertContains(self.client.post(reverse("citizen_requests:public_portal"),
                                            {"tracking_form":"1", "tracking_code":str(r.tracking_code)}),"Resuelta")
        with self.captureOnCommitCallbacks(execute=True):
            result=self.client.post(url,self.payload(status="CLOSED",observation="Cierre final"))
        self.assertEqual(result.status_code,302)
        a.refresh_from_db();r.refresh_from_db()
        self.assertEqual(a.status,"CLOSED")
        self.assertIsNotNone(a.closed_at)
        self.assertEqual(r.status,"CLOSED")
        self.assertEqual(len(mail.outbox),2)
        self.assertNotContains(self.client.get(reverse("registration:attention_entry_list")),"Vecina FUP")
        self.assertContains(self.client.get(reverse("registration:attention_entry_list")+"?status=closed"),"Vecina FUP")
        self.assertEqual(self.client.get(url).status_code,403)
        self.assertEqual(self.client.post(url,self.payload(status="IN_PROGRESS")).status_code,403)
        # Una atención cerrada sí puede archivarse lógicamente, con el permiso actual.
        # Se comprobará por separado para no impedir esta prueba de reapertura.
        with self.captureOnCommitCallbacks(execute=True):
            result=self.client.post(url,{"action":"reopen"})
        self.assertEqual(result.status_code,302)
        a.refresh_from_db();r.refresh_from_db()
        self.assertEqual(a.status,"IN_PROGRESS")
        self.assertEqual(a.get_status_display(), "En gestión")
        self.assertIsNone(a.closed_at)
        self.assertEqual(r.status,"IN_PROGRESS")
        self.assertEqual(r.get_status_display(), "En gestión")
        self.assertEqual(len(mail.outbox),3)
        self.assertIn("En gestión",mail.outbox[-1].body)

    def test_direct_close_registers_resolution_then_close_and_one_email(self):
        attention, req = self.create_manual()
        self.assertEqual(attention.tracking_code, req.tracking_code)
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("registration:attention_entry_update", args=[attention.pk]),
                self.payload(status="CLOSED", observation="La reparación se completó"),
            )
        self.assertEqual(response.status_code, 302)
        events = list(req.events.order_by("created_at", "pk").values_list("new_status", flat=True))
        self.assertEqual(events[-2:], ["RESOLVED", "CLOSED"])
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        self.assertIn("Estado actual: Cerrada", body)
        self.assertLess(body.index("- Resuelta"), body.index("- Cerrada"))
        result = self.client.post(reverse("citizen_requests:public_portal"),
                                  {"tracking_form": "1", "tracking_code": str(req.tracking_code)})
        self.assertContains(result, "Resuelta")
        self.assertContains(result, "Cerrada")

    def test_reopen_preserves_history_and_notifies_current_management(self):
        a, req = self.create_manual()
        url = reverse("registration:attention_entry_update", args=[a.pk])
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(url, self.payload(status="CLOSED", observation="Trabajo terminado"))
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(url, {"action": "reopen"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Estado actual: En gestión (reabierta)", mail.outbox[0].body)
        self.assertIn("- Cerrada", mail.outbox[0].body)
        self.assertIn("Reabierta", mail.outbox[0].body)
        result = self.client.post(reverse("citizen_requests:public_portal"),
                                  {"tracking_form": "1", "tracking_code": str(req.tracking_code)})
        self.assertContains(result, "Reabierta")
        self.assertContains(result, "Resuelta")
        self.assertContains(result, "Cerrada")
        self.assertContains(result, "Estado de la solicitud")

    def test_rejected_then_closed_does_not_pretend_resolved(self):
        a, req = self.create_manual()
        url = reverse("registration:attention_entry_update", args=[a.pk])
        with self.captureOnCommitCallbacks(execute=True):
            r = self.client.post(url, self.payload(status="REJECTED", observation="No corresponde"))
        self.assertEqual(r.status_code,302)
        with self.captureOnCommitCallbacks(execute=True):
            r = self.client.post(url, self.payload(status="CLOSED", observation="Se cierra sin solución"))
        self.assertEqual(r.status_code,302)
        self.assertFalse(req.events.filter(new_status="RESOLVED").exists())
        response = self.client.post(reverse("citizen_requests:public_portal"),
                                    {"tracking_form":"1", "tracking_code": str(req.tracking_code)})
        self.assertContains(response, "No procede")
        self.assertNotContains(response, ">Resuelta<")

    def test_creating_from_public_request_uses_same_tracking_code(self):
        public = CitizenRequest.objects.create(
            origin="CITIZEN", requester_name="Vecina con código",
            requester_email="vecina@example.com", address="Calle Prueba",
            subject="Solicitud", description="Detalle", delegation=self.delegation,
        )
        data = self.payload(email="vecina@example.com")
        data["citizen_request"] = str(public.pk)
        result = self.client.post(reverse("registration:attention_entry_create"), data)
        self.assertEqual(result.status_code,302)
        public.refresh_from_db()
        self.assertEqual(public.attention_entry.tracking_code,public.tracking_code)
        detail = self.client.get(reverse("registration:attention_entry_detail", args=[public.attention_entry_id])).json()["attention"]
        self.assertEqual(detail["tracking_code"], str(public.tracking_code))
        self.assertEqual(detail["request_tracking_code"], str(public.tracking_code))

    def test_linked_attention_can_correct_subject_without_changing_original_request(self):
        request_obj = CitizenRequest.objects.create(
            origin="CITIZEN", requester_name="Vecina con solicitud original",
            requester_email="vecina@example.com", address="Calle Prueba",
            subject="Luminaria apagada", description="La luz no funciona",
            delegation=self.delegation,
        )
        payload = self.payload(email="vecina@example.com")
        payload.update({
            "citizen_request": str(request_obj.pk),
            "subject": "Reparación de alumbrado público",
            "description": "Poste de luz averiado frente al domicilio",
        })
        response = self.client.post(reverse("registration:attention_entry_create"), payload)
        self.assertEqual(response.status_code, 302)
        request_obj.refresh_from_db()
        attention = request_obj.attention_entry
        self.assertEqual(attention.subject, "Reparación de alumbrado público")
        self.assertEqual(attention.description, "Poste de luz averiado frente al domicilio")
        self.assertEqual(request_obj.subject, "Luminaria apagada")
        self.assertEqual(request_obj.description, "La luz no funciona")
        self.assertTrue(request_obj.events.filter(observation__icontains="asunto").exists())

        detail = self.client.get(reverse("citizen_requests:request_detail", args=[request_obj.pk]))
        self.assertEqual(detail.status_code, 200)
        data = detail.json()["request"]
        self.assertEqual(data["subject"], attention.subject)
        self.assertEqual(data["description"], attention.description)
        self.assertEqual(data["original_subject"], request_obj.subject)
        self.assertEqual(data["original_description"], request_obj.description)
        inbox = self.client.get(reverse("citizen_requests:request_inbox"))
        self.assertEqual(inbox.status_code, 200)
        delegated = inbox.json()["delegated"]["items"]
        current = next(item for item in delegated if item["id"] == request_obj.pk)
        self.assertEqual(current["subject"], attention.subject)
        searched = self.client.get(reverse("citizen_requests:request_inbox"),
                                   {"q": "alumbrado público"})
        self.assertTrue(any(item["id"] == request_obj.pk for item in
                            searched.json()["delegated"]["items"]))

        mail.outbox.clear()
        update_payload = self.payload(email="vecina@example.com", status="IN_PROGRESS")
        update_payload.update({"subject": "Alumbrado corregido",
                               "description": "Se precisa el tramo de la calle"})
        with self.captureOnCommitCallbacks(execute=True):
            result = self.client.post(
                reverse("registration:attention_entry_update", args=[attention.pk]),
                update_payload,
            )
        self.assertEqual(result.status_code, 302)
        attention.refresh_from_db()
        request_obj.refresh_from_db()
        self.assertEqual(attention.subject, "Alumbrado corregido")
        self.assertEqual(request_obj.subject, "Luminaria apagada")
        self.assertEqual(request_obj.description, "La luz no funciona")
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(request_obj.events.filter(
            observation__icontains="Datos de atención actualizados",
        ).exists())
        latest = self.client.get(reverse("citizen_requests:request_detail",
                                         args=[request_obj.pk])).json()["request"]
        self.assertEqual(latest["subject"], "Alumbrado corregido")
        self.assertEqual(latest["original_subject"], "Luminaria apagada")

    def test_manual_original_text_is_preserved_after_status_change(self):
        attention, request_obj = self.create_manual()
        self.assertEqual(request_obj.subject, "Solicitud")
        with self.captureOnCommitCallbacks(execute=True):
            result = self.client.post(
                reverse("registration:attention_entry_update", args=[attention.pk]),
                dict(self.payload(status="RESOLVED", observation="Gestión terminada"),
                     subject="Solicitud modificada", description="Descripción actualizada"),
            )
        self.assertEqual(result.status_code, 302)
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.subject, "Solicitud")
        self.assertEqual(request_obj.description, "Descripción")
        data = self.client.get(reverse("citizen_requests:request_detail",
                                      args=[request_obj.pk])).json()["request"]
        self.assertEqual(data["subject"], "Solicitud modificada")
        self.assertEqual(data["original_subject"], "Solicitud")

    def test_no_email_on_plain_edit_or_invalid_closure(self):
        a,r=self.create_manual()
        mail.outbox.clear()
        url=reverse("registration:attention_entry_update",args=[a.pk])
        result=self.client.post(url,self.payload(status="CLOSED"))
        self.assertEqual(result.status_code,200)
        self.assertContains(result,"Indica el resultado de la gestión")
        a.refresh_from_db()
        self.assertEqual(a.status,"IN_PROGRESS")
        with self.captureOnCommitCallbacks(execute=True):
            result=self.client.post(url,self.payload(status="IN_PROGRESS"))
        self.assertEqual(result.status_code,302)
        self.assertEqual(len(mail.outbox),0)

    def test_reopen_requires_existing_change_permission(self):
        a,_=self.create_manual()
        a.status="CLOSED";a.save(update_fields=["status"])
        self.user.user_permissions.clear()
        self.user.groups.clear()
        self.user=get_user_model().objects.get(pk=self.user.pk)
        self.client.force_login(self.user)
        url=reverse("registration:attention_entry_update",args=[a.pk])
        self.assertEqual(self.client.post(url,{"action":"reopen"}).status_code,403)

    def test_creating_from_existing_request_starts_in_management(self):
        request_obj = CitizenRequest.objects.create(
            origin="CITIZEN", requester_name="Vecina desde solicitud",
            requester_email="vecina@example.com", address="Calle de prueba",
            subject="Solicitud web", description="Requiere atención",
            delegation=self.delegation, status="NEW",
        )
        data = self.payload(email="vecina@example.com")
        data["citizen_request"] = str(request_obj.pk)
        response = self.client.post(reverse("registration:attention_entry_create"), data)
        self.assertEqual(response.status_code, 302)
        request_obj.refresh_from_db()
        self.assertIsNotNone(request_obj.attention_entry_id)
        attention = request_obj.attention_entry
        self.assertEqual(attention.status, "IN_PROGRESS")
        self.assertEqual(attention.get_status_display(), "En gestión")
        self.assertEqual(request_obj.status, "IN_PROGRESS")
        self.assertEqual(request_obj.get_status_display(), "En gestión")
        list_response = self.client.get(reverse("registration:attention_entry_list"))
        self.assertContains(list_response, "En gestión")
        detail_response = self.client.get(reverse("registration:attention_entry_detail", args=[attention.pk]))
        self.assertEqual(detail_response.json()["attention"]["status"], "En gestión")

    def test_only_closed_attention_can_be_soft_deleted(self):
        attention, linked = self.create_manual()
        delete_url = reverse("registration:attention_entry_delete", args=[attention.pk])
        self.assertEqual(self.client.post(delete_url).status_code, 403)
        attention.refresh_from_db()
        self.assertIsNone(attention.deleted_at)
        self.assertNotContains(self.client.get(reverse("registration:attention_entry_list")), f'action="{delete_url}"')

        update_url = reverse("registration:attention_entry_update", args=[attention.pk])
        with self.captureOnCommitCallbacks(execute=True):
            result = self.client.post(update_url, self.payload(status="CLOSED", observation="Trabajo finalizado"))
        self.assertEqual(result.status_code, 302)
        self.assertContains(self.client.get(reverse("registration:attention_entry_list") + "?status=closed"), f'action="{delete_url}"')
        mail_count = len(mail.outbox)
        result = self.client.post(delete_url)
        self.assertEqual(result.status_code, 302)
        attention.refresh_from_db()
        linked.refresh_from_db()
        self.assertIsNotNone(attention.deleted_at)
        self.assertEqual(attention.status, "CLOSED")
        self.assertEqual(linked.status, "CLOSED")
        self.assertEqual(len(mail.outbox), mail_count)  # archivar no cambia el estado ni envía avisos nuevos
        self.assertNotContains(self.client.get(reverse("registration:attention_entry_list") + "?status=closed"), "Vecina FUP")

    def test_closed_attention_deletion_still_requires_delete_permission(self):
        attention, _ = self.create_manual()
        attention.status = "CLOSED"
        attention.save(update_fields=["status"])
        group = self.user.groups.first()
        group.permissions.remove(Permission.objects.get(
            content_type__app_label="registration_validation",
            codename="delete_attentionentry",
        ))
        self.user = get_user_model().objects.get(pk=self.user.pk)
        self.client.force_login(self.user)
        result = self.client.post(reverse("registration:attention_entry_delete", args=[attention.pk]))
        self.assertEqual(result.status_code, 403)
        attention.refresh_from_db()
        self.assertIsNone(attention.deleted_at)
