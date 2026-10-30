"""Pruebas del flujo sin usar cuentas superusuario."""
from datetime import timedelta
from django.contrib.auth.models import Group, Permission, User
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from organization.models import Delegation, OrganizationRole
from registration_validation.models import AttentionEntry, AttentionType, SubAttention
from .forms import EnrollmentForm
from .models import Beneficiary, Campaign, CampaignAudit, Enrollment, GiftDelivery, MunicipalEvent, EventEdition
from .services import can_register_from_attention


class CampaignWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.d1 = Delegation.objects.create(code="N1", name="Norte", status="Activa", scope="Norte")
        cls.d2 = Delegation.objects.create(code="S1", name="Sur", status="Activa", scope="Sur")
        cls.group = Group.objects.create(name="Gestión de campañas - prueba")
        role = OrganizationRole.objects.create(group=cls.group, delegation=cls.d1)
        role.application_delegations.add(cls.d1, cls.d2)
        cls.group.permissions.add(*Permission.objects.filter(content_type__app_label="municipal_events", codename__in=[
            "view_campaign", "add_campaign", "change_campaign", "view_enrollment", "add_enrollment", "change_enrollment", "add_giftdelivery", "view_municipalevent", "add_municipalevent", "add_eventedition",
        ]))
        cls.group.permissions.add(*Permission.objects.filter(content_type__app_label="registration_validation", codename="view_attentionentry"))
        cls.user1 = User.objects.create_user("camp_norte", password="test-password")
        cls.user2 = User.objects.create_user("camp_sur", password="test-password")
        for i, (user, delegation) in enumerate([(cls.user1, cls.d1), (cls.user2, cls.d2)]):
            p = UserProfile.objects.create(user=user, employee_code=f"CAM{i}", delegation=delegation)
            p.authorized_delegations.add(delegation)
            user.groups.add(cls.group)
        cls.attention_type = AttentionType.objects.create(code="CM", name="Campaña municipal", status=True)
        cls.other_type = AttentionType.objects.create(code="OT", name="Otro servicio", status=True)
        cls.sub = SubAttention.objects.create(code="CM1", name="Inscripción", attention_type=cls.attention_type, status=True)
        cls.sub_other = SubAttention.objects.create(code="OT1", name="Consulta", attention_type=cls.other_type, status=True)
        cls.a1 = AttentionEntry.objects.create(requester="Adulto de prueba", attention_type=cls.attention_type, sub_attention=cls.sub, description="Inscripción Navidad", delegation=cls.d1)
        cls.a2 = AttentionEntry.objects.create(requester="Otro adulto de prueba", attention_type=cls.attention_type, sub_attention=cls.sub, description="Inscripción Navidad", delegation=cls.d2)
        cls.wrong = AttentionEntry.objects.create(requester="Consulta", attention_type=cls.other_type, sub_attention=cls.sub_other, description="No es campaña", delegation=cls.d1)
        today = timezone.localdate()
        cls.campaign = Campaign.objects.create(title="Navidad", year=today.year, attention_type=cls.attention_type, organizing_delegation=cls.d1, opens_on=today-timedelta(days=2), closes_on=today+timedelta(days=30), status="OPEN", created_by=cls.user1)

    def test_normal_user_can_enroll_from_matching_attention(self):
        self.client.force_login(self.user1)
        url = reverse("municipal_events:enrollment_create", args=[self.campaign.pk])
        res = self.client.post(url, {"attention":self.a1.pk,"name":"Niño Demo","rut":"123456785","birth_date":"2017-03-01","observation":"Prueba"})
        self.assertEqual(res.status_code, 302)
        item = Enrollment.objects.get()
        self.assertEqual(item.attention, self.a1)
        self.assertEqual(item.status, "PENDING")
        self.assertEqual(item.beneficiary.rut, "123456785")
        self.assertEqual(CampaignAudit.objects.count(),1)

    def test_second_delegation_cannot_duplicate_same_child(self):
        self.client.force_login(self.user1)
        url = reverse("municipal_events:enrollment_create", args=[self.campaign.pk])
        data = {"attention":self.a1.pk,"name":"Niño Demo","rut":"12.345.678-5","birth_date":"2017-03-01"}
        self.assertEqual(self.client.post(url, data).status_code,302)
        self.client.force_login(self.user2)
        data["attention"] = self.a2.pk
        res = self.client.post(url, data)
        self.assertEqual(res.status_code,200)
        self.assertContains(res,"ya está inscrito")
        self.assertEqual(Enrollment.objects.count(),1)

    def test_type_and_active_delegation_requirements(self):
        self.client.force_login(self.user1)
        url = reverse("municipal_events:enrollment_create", args=[self.campaign.pk])
        data = {"attention":self.wrong.pk,"name":"Demo","rut":"12.345.678-5","birth_date":"2017-03-01"}
        self.assertEqual(self.client.post(url,data).status_code,403)
        data["attention"] = self.a2.pk
        self.assertEqual(self.client.post(url,data).status_code,403)
        self.campaign.status = "CLOSED"
        self.campaign.save()
        data["attention"] = self.a1.pk
        self.assertEqual(self.client.post(url,data).status_code,403)

    def test_delivery_needs_approval_and_cannot_repeat(self):
        child = Beneficiary.objects.create(name="Demo",rut="123456785",birth_date="2017-03-01")
        enrollment = Enrollment.objects.create(campaign=self.campaign,beneficiary=child,attention=self.a1,delegation=self.d1,created_by=self.user1)
        self.client.force_login(self.user1)
        url = reverse("municipal_events:delivery_create",args=[enrollment.pk])
        self.assertEqual(self.client.get(url).status_code,403)
        review = reverse("municipal_events:enrollment_review",args=[enrollment.pk])
        self.assertEqual(self.client.post(review,{"status":"APPROVED","reason":"Cumple requisitos"}).status_code,302)
        self.assertEqual(self.client.post(url,{"notes":"Constancia de entrega"}).status_code,302)
        self.assertEqual(self.client.post(url,{"notes":"Otra entrega"}).status_code,403)
        self.assertEqual(GiftDelivery.objects.count(),1)
        self.assertEqual(CampaignAudit.objects.count(),2)

    def test_periodic_event_unique_year_and_campaign_not_hardcoded(self):
        event = MunicipalEvent.objects.create(name="Navidad comunitaria",created_by=self.user1)
        d = timezone.localdate()
        EventEdition.objects.create(event=event,year=d.year,date=d,place="Sede",delegation=self.d1,responsible=self.user1)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                EventEdition.objects.create(event=event,year=d.year,date=d,place="Otro",delegation=self.d1,responsible=self.user1)
        self.assertEqual(self.campaign.attention_type_id,self.attention_type.pk)

    def test_permissions_missing_returns_403(self):
        user = User.objects.create_user("sin_permisos",password="pass")
        p = UserProfile.objects.create(user=user,employee_code="CAMX",delegation=self.d1)
        p.authorized_delegations.add(self.d1)
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("municipal_events:campaign_list")).status_code,403)
        self.assertEqual(self.client.get(reverse("municipal_events:enrollment_create", args=[self.campaign.pk]),{"attention":self.a1.pk}).status_code,403)

    def test_attention_list_shows_campaign_action_only_for_matching_type(self):
        self.client.force_login(self.user1)
        res = self.client.get(reverse("registration:attention_entry_list"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Inscribir en campaña")
        picker = self.client.get(reverse("municipal_events:campaigns_for_attention", args=[self.a1.pk]))
        self.assertEqual(picker.status_code, 200)
        self.assertContains(picker, "Navidad")
        self.assertEqual(self.client.get(reverse("municipal_events:campaigns_for_attention", args=[self.a2.pk])).status_code, 403)

    def test_campaign_pages_and_create_event(self):
        self.client.force_login(self.user1)
        self.assertEqual(self.client.get(reverse("municipal_events:campaign_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("municipal_events:campaign_detail", args=[self.campaign.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("municipal_events:event_list")).status_code, 200)
        res = self.client.post(reverse("municipal_events:event_create"), {"name": "Evento anual", "description": "Demo"})
        self.assertEqual(res.status_code, 302)
        self.assertEqual(MunicipalEvent.objects.count(), 1)

    def test_campaign_with_enrollments_cannot_change_linked_type(self):
        child = Beneficiary.objects.create(name="Demo",rut="123456785",birth_date="2017-03-01")
        Enrollment.objects.create(campaign=self.campaign,beneficiary=child,attention=self.a1,delegation=self.d1,created_by=self.user1)
        self.client.force_login(self.user1)
        res = self.client.post(reverse("municipal_events:campaign_edit", args=[self.campaign.pk]), {
            "title":"Navidad", "year":self.campaign.year, "description":"", "attention_type":self.other_type.pk,
            "edition":"", "organizing_delegation":self.d1.pk, "opens_on":self.campaign.opens_on.isoformat(),
            "closes_on":self.campaign.closes_on.isoformat(), "status":"OPEN",
        })
        self.assertEqual(res.status_code, 200)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.attention_type, self.attention_type)

    def test_old_dashboard_redirects_to_sgr_home(self):
        """Un enlace anterior a Resumen termina en el inicio general del SGR."""
        self.client.force_login(self.user1)
        res = self.client.get(reverse("municipal_events:dashboard"))
        self.assertRedirects(res, reverse("home"))

    def test_sgr_home_has_five_independent_cards_and_no_summary(self):
        """Cada tarjeta entra directamente a una sección con su permiso específico."""
        from core.views import build_sections
        self.client.force_login(self.user1)
        res = self.client.get(reverse("home"))
        self.assertEqual(res.status_code, 200)
        sections = build_sections(self.user1)
        cards = next(s["cards"] for s in sections if s["title"] == "Eventos y Campañas")
        names = [card["title"] for card in cards]
        self.assertEqual(names, ["Eventos", "Campañas", "Inscripciones", "Historial"])
        self.assertNotContains(res, "Panel Eventos y Campañas")
        self.assertContains(res, reverse("municipal_events:event_list"))
        self.assertContains(res, reverse("municipal_events:campaign_list"))
        self.assertContains(res, reverse("municipal_events:enrollment_list"))
        self.assertContains(res, reverse("municipal_events:history_list"))
        self.assertNotContains(res, reverse("municipal_events:delivery_list"))
        self.group.permissions.add(Permission.objects.get(
            content_type__app_label="municipal_events", codename="view_giftdelivery"))
        self.user1 = User.objects.get(pk=self.user1.pk)  # refrescar caché de permisos
        with_delivery = next(s["cards"] for s in build_sections(self.user1)
                             if s["title"] == "Eventos y Campañas")
        self.assertEqual([card["title"] for card in with_delivery],
                         ["Eventos", "Campañas", "Inscripciones", "Entregas", "Historial"])

    def test_sidebar_inicio_goes_home_without_duplicate_link(self):
        self.client.force_login(self.user1)
        res = self.client.get(reverse("municipal_events:event_list"))
        self.assertContains(res, f'href="{reverse("home")}"')
        self.assertNotContains(res, "Inicio del SGR")
        self.assertNotContains(res, "Panel de Eventos y Campañas")
        self.assertNotContains(res, f'href="{reverse("municipal_events:dashboard")}"')


    def test_new_pages_enforce_territorial_visibility(self):
        """La navegación nueva no revela beneficiarios de otra delegación."""
        child1 = Beneficiary.objects.create(name="Niño Norte Autorizado", rut="123456785", birth_date="2017-03-01")
        child2 = Beneficiary.objects.create(name="Niño Sur Reservado", rut="111111111", birth_date="2017-03-01")
        en1 = Enrollment.objects.create(campaign=self.campaign, beneficiary=child1, attention=self.a1, delegation=self.d1, created_by=self.user1, status="APPROVED")
        en2 = Enrollment.objects.create(campaign=self.campaign, beneficiary=child2, attention=self.a2, delegation=self.d2, created_by=self.user2, status="APPROVED")
        CampaignAudit.objects.create(enrollment=en1, actor=self.user1, action="APPROVED", reason="Norte")
        CampaignAudit.objects.create(enrollment=en2, actor=self.user2, action="APPROVED", reason="Sur privado")
        GiftDelivery.objects.create(enrollment=en1, delivered_by=self.user1, notes="Entrega norte")
        GiftDelivery.objects.create(enrollment=en2, delivered_by=self.user2, notes="Entrega sur")
        self.client.force_login(self.user1)
        for route in ("municipal_events:enrollment_list", "municipal_events:history_list"):
            result = self.client.get(reverse(route))
            self.assertEqual(result.status_code, 200, route)
            self.assertContains(result, "Niño Norte Autorizado")
            self.assertNotContains(result, "Niño Sur Reservado")
            self.assertNotContains(result, "Sur privado")
        self.assertNotContains(self.client.get(reverse("municipal_events:history_list")), "Entrega sur")
        # Las entregas tienen permiso de lectura independiente.
        delivery_url = reverse("municipal_events:delivery_list")
        self.assertEqual(self.client.get(delivery_url).status_code, 403)
        self.group.permissions.add(Permission.objects.get(content_type__app_label="municipal_events", codename="view_giftdelivery"))
        # El test usa una nueva instancia para evitar la caché local de permisos.
        from django.contrib.auth import get_user_model
        self.client.force_login(get_user_model().objects.get(pk=self.user1.pk))
        result = self.client.get(delivery_url)
        self.assertEqual(result.status_code, 200)
        self.assertContains(result, "Niño Norte Autorizado")
        self.assertNotContains(result, "Niño Sur Reservado")

    def test_new_sections_reject_users_without_permissions(self):
        user = User.objects.create_user("mec_no_perm", password="demo-pass")
        profile = UserProfile.objects.create(user=user, employee_code="CAM-Z", delegation=self.d1)
        profile.authorized_delegations.add(self.d1)
        self.client.force_login(user)
        # La ruta del panel anterior solo redirige a un inicio seguro, sin exponer datos.
        self.assertRedirects(self.client.get(reverse("municipal_events:dashboard")), reverse("home"))
        for route in ("municipal_events:enrollment_list", "municipal_events:delivery_list", "municipal_events:history_list"):
            self.assertEqual(self.client.get(reverse(route)).status_code, 403, route)

    def test_ajax_event_modal_create_and_invalid_form(self):
        self.client.force_login(self.user1)
        url = reverse("municipal_events:event_create")
        headers = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}
        get_response = self.client.get(url, **headers)
        self.assertEqual(get_response.status_code, 200)
        self.assertContains(get_response, 'data-mec-ajax-form')
        self.assertNotContains(get_response, 'mec-shell')
        invalid_response = self.client.post(url, {"name": ""}, **headers)
        self.assertEqual(invalid_response.status_code, 422)
        self.assertContains(invalid_response, 'data-mec-ajax-form', status_code=422)
        valid_response = self.client.post(url, {"name": "Evento Modal", "description": "Prueba"}, **headers)
        self.assertEqual(valid_response.status_code, 200)
        self.assertEqual(valid_response.json()["ok"], True)
        event = MunicipalEvent.objects.get(name="Evento Modal")
        self.assertContains(self.client.get(reverse("municipal_events:event_detail", args=[event.pk]), **headers), 'Evento Modal')
        listing = self.client.get(reverse("municipal_events:event_list"))
        self.assertContains(listing, 'data-mec-modal-url')
        self.assertContains(listing, 'Evento Modal')

    def test_ajax_campaign_edit_validation_and_detail(self):
        self.client.force_login(self.user1)
        headers = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}
        url = reverse("municipal_events:campaign_edit", args=[self.campaign.pk])
        self.assertContains(self.client.get(url, **headers), 'data-mec-ajax-form')
        invalid = self.client.post(url, {
            "title": "Navidad", "year": self.campaign.year, "attention_type": self.attention_type.pk,
            "organizing_delegation": self.d1.pk, "opens_on": "2026-12-31",
            "closes_on": "2026-01-01", "edition": "", "status": "OPEN",
        }, **headers)
        self.assertEqual(invalid.status_code, 422)
        self.assertContains(invalid, "fecha de cierre", status_code=422)
        self.assertContains(self.client.get(reverse("municipal_events:campaign_detail", args=[self.campaign.pk]), **headers), "Navidad")

    def test_ajax_review_and_delivery_modal_flow(self):
        child = Beneficiary.objects.create(name="Niño Modal", rut="123456785", birth_date="2017-03-01")
        enrollment = Enrollment.objects.create(campaign=self.campaign, beneficiary=child,
            attention=self.a1, delegation=self.d1, created_by=self.user1)
        self.client.force_login(self.user1)
        headers = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}
        get_detail = self.client.get(reverse("municipal_events:enrollment_detail", args=[enrollment.pk]), **headers)
        self.assertContains(get_detail, 'Niño Modal')
        review = reverse("municipal_events:enrollment_review", args=[enrollment.pk])
        self.assertContains(self.client.get(review, **headers), 'data-mec-ajax-form')
        self.assertEqual(self.client.post(review, {"status": "APPROVED", "reason": "Revisión de prueba"}, **headers).json()["ok"], True)
        deliver = reverse("municipal_events:delivery_create", args=[enrollment.pk])
        self.assertContains(self.client.get(deliver, **headers), 'Niño Modal')
        self.assertEqual(self.client.post(deliver, {"notes": "Constancia"}, **headers).json()["ok"], True)
        # Consultar la constancia necesita el permiso independiente de lectura.
        self.group.permissions.add(Permission.objects.get(content_type__app_label="municipal_events", codename="view_giftdelivery"))
        from django.contrib.auth import get_user_model
        self.client.force_login(get_user_model().objects.get(pk=self.user1.pk))
        self.assertContains(self.client.get(reverse("municipal_events:delivery_detail", args=[enrollment.pk]), **headers), "Constancia")
        self.assertEqual(self.client.post(deliver, {"notes": "Duplicación"}, **headers).status_code, 403)

    def test_ajax_delete_is_restricted_and_protects_related_records(self):
        headers = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}
        event = MunicipalEvent.objects.create(name="Evento protegible", created_by=self.user1)
        self.client.force_login(self.user1)
        url = reverse("municipal_events:event_delete", args=[event.pk])
        self.assertEqual(self.client.get(url, **headers).status_code, 403)
        self.group.permissions.add(Permission.objects.get(content_type__app_label="municipal_events", codename="delete_municipalevent"))
        # Reiniciar permisos cacheados
        from django.contrib.auth import get_user_model
        self.client.force_login(get_user_model().objects.get(pk=self.user1.pk))
        self.assertContains(self.client.get(url, **headers), "Eliminar evento municipal")
        self.assertTrue(self.client.post(url, **headers).json()["ok"])
        self.assertFalse(MunicipalEvent.objects.filter(pk=event.pk).exists())
        protected = MunicipalEvent.objects.create(name="Evento con edición", created_by=self.user1)
        EventEdition.objects.create(event=protected, year=timezone.localdate().year,
            date=timezone.localdate(), place="Sede", delegation=self.d1, responsible=self.user1)
        protected_url = reverse("municipal_events:event_delete", args=[protected.pk])
        self.assertContains(self.client.get(protected_url, **headers), "no se puede eliminar")
        self.assertEqual(self.client.post(protected_url, **headers).status_code, 409)
        self.assertTrue(MunicipalEvent.objects.filter(pk=protected.pk).exists())

    def test_modal_detail_respects_delegation_scope(self):
        other = Beneficiary.objects.create(name="Niño Sur", rut="123456785", birth_date="2017-03-01")
        enrollment = Enrollment.objects.create(campaign=self.campaign, beneficiary=other,
            attention=self.a2, delegation=self.d2, created_by=self.user2)
        self.client.force_login(self.user1)
        response = self.client.get(reverse("municipal_events:enrollment_detail", args=[enrollment.pk]), HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 404)

    def test_events_search_keeps_modal_actions_on_list(self):
        MunicipalEvent.objects.create(name="Navidad Comunitaria", description="Celebración", created_by=self.user1)
        self.client.force_login(self.user1)
        result = self.client.get(reverse("municipal_events:event_list"), {"q": "Navidad"})
        self.assertEqual(result.status_code, 200)
        self.assertContains(result, "Navidad Comunitaria")
        self.assertContains(result, 'data-bs-toggle="collapse"')
        self.assertContains(result, 'data-mec-modal-url')
        filtered = self.client.get(reverse("municipal_events:event_list"), {"q": "xyz-no-existe"})
        self.assertNotContains(filtered, "Navidad Comunitaria")
