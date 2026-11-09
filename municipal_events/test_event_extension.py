# SGR_PERMISOS_EVENTOS_V2
"""Pruebas de borrado lógico y participación configurada sin superusuario."""
from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from municipal_events.tests import CampaignWorkflowTests
from .models import (MunicipalEvent, EventEdition, Campaign, Beneficiary,
                     Enrollment, EventParticipation, EventActionAudit)


def rut_for(base):
    digits = str(base)
    total = sum(int(x) * (2 + i % 6) for i, x in enumerate(reversed(digits)))
    n = 11 - (total % 11)
    return digits + ('0' if n == 11 else 'K' if n == 10 else str(n))


class EventExtensionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CampaignWorkflowTests.setUpTestData.__func__(cls)
        cls.group.permissions.add(*Permission.objects.filter(
            content_type__app_label='municipal_events', codename__in=[
                'change_municipalevent', 'view_eventedition', 'change_eventedition',
                'change_campaign', 'delete_municipalevent', 'delete_eventedition', 'delete_campaign',
                'view_eventparticipation', 'add_eventparticipation', 'change_eventparticipation',
                'evaluate_eventparticipation', 'withdraw_eventparticipation',
                'reactivate_eventparticipation',
            ]))

    def setUp(self):
        self.client.force_login(self.user1)
        self.event = MunicipalEvent.objects.create(name='Verbena', created_by=self.user1)
        d = timezone.localdate()
        self.edition = EventEdition.objects.create(event=self.event, year=d.year, date=d,
            place='La Serena', delegation=self.d1, responsible=self.user1,
            participation_mode='APPLICATION', participation_capacity=1)

    def test_event_soft_delete_and_reactivation_keep_same_pk_and_audit(self):
        self.edition.deleted_at = timezone.now()
        self.edition.save(update_fields=['deleted_at'])
        url = reverse('municipal_events:event_delete', args=[self.event.pk])
        self.assertEqual(self.client.post(url, {'reason': 'Prueba'}).status_code, 302)
        self.event.refresh_from_db()
        self.assertIsNotNone(self.event.deleted_at)
        self.assertEqual(MunicipalEvent.objects.filter(pk=self.event.pk).count(), 1)
        self.assertNotContains(self.client.get(reverse('municipal_events:event_list')), 'Verbena')
        self.assertContains(self.client.get(reverse('municipal_events:event_list')+'?record_state=inactive'), 'Verbena')
        url = reverse('municipal_events:event_reactivate', args=[self.event.pk])
        self.assertEqual(self.client.post(url, {'reason': 'Retomar'}).status_code, 302)
        self.event.refresh_from_db()
        self.assertIsNone(self.event.deleted_at)
        self.assertEqual(EventActionAudit.objects.filter(event=self.event).count(), 2)

    def test_parent_cannot_deactivate_with_active_edition(self):
        result = self.client.post(reverse('municipal_events:event_delete', args=[self.event.pk]),
            {'reason': 'No se debe'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(result.status_code, 409)
        self.event.refresh_from_db()
        self.assertIsNone(self.event.deleted_at)

    def test_edition_soft_delete_and_reactivation(self):
        delete = reverse('municipal_events:edition_delete', args=[self.edition.pk])
        self.assertEqual(self.client.post(delete, {'reason': 'Sin actividad'}).status_code, 302)
        self.edition.refresh_from_db()
        self.assertIsNotNone(self.edition.deleted_at)
        self.assertEqual(self.client.post(reverse('municipal_events:edition_reactivate', args=[self.edition.pk]),
            {'reason':'Recuperar'}).status_code, 302)
        self.edition.refresh_from_db()
        self.assertIsNone(self.edition.deleted_at)

    def test_campaign_with_enrollments_cannot_deactivate(self):
        child = Beneficiary.objects.create(name='Niño de prueba', rut=rut_for(12345678), birth_date='2017-03-01')
        Enrollment.objects.create(campaign=self.campaign, beneficiary=child, attention=self.a1,
                                  delegation=self.d1, created_by=self.user1)
        response = self.client.post(reverse('municipal_events:campaign_delete', args=[self.campaign.pk]),
            {'reason':'Prueba'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 409)
        self.campaign.refresh_from_db()
        self.assertIsNone(self.campaign.deleted_at)

    def test_closed_campaign_with_historical_rejected_enrollment_can_deactivate(self):
        child = Beneficiary.objects.create(name='Niña histórica', rut=rut_for(12345678), birth_date='2017-03-01')
        Enrollment.objects.create(campaign=self.campaign, beneficiary=child, attention=self.a1,
            delegation=self.d1, created_by=self.user1, status='REJECTED')
        self.campaign.status = 'CLOSED'
        self.campaign.save(update_fields=['status'])
        resp = self.client.post(reverse('municipal_events:campaign_delete', args=[self.campaign.pk]),
            {'reason': 'Campaña terminada'})
        self.assertEqual(resp.status_code, 302)
        self.campaign.refresh_from_db()
        self.assertIsNotNone(self.campaign.deleted_at)
        self.assertEqual(self.campaign.enrollments.count(), 1)
        self.assertTrue(EventActionAudit.objects.filter(campaign=self.campaign, action='DESACTIVADO').exists())

    def test_inactive_campaign_does_not_reactivate_historical_inscription(self):
        child = Beneficiary.objects.create(name='Niño retirado', rut=rut_for(12345678), birth_date='2017-03-01')
        enrollment = Enrollment.objects.create(campaign=self.campaign, beneficiary=child,
            attention=self.a1, delegation=self.d1, created_by=self.user1,
            status='REJECTED', deleted_at=timezone.now())
        self.campaign.status = 'CLOSED'
        self.campaign.save(update_fields=['status'])
        self.assertEqual(self.client.post(reverse('municipal_events:campaign_delete', args=[self.campaign.pk]),
            {'reason': 'Terminada'}).status_code, 302)
        res = self.client.post(reverse('municipal_events:enrollment_reactivate', args=[enrollment.pk]),
            {'reason': 'No debe permitirse'})
        self.assertEqual(res.status_code, 403)
        enrollment.refresh_from_db()
        self.assertIsNotNone(enrollment.deleted_at)

    def test_closed_campaign_with_completed_delivery_can_deactivate(self):
        from .models import GiftDelivery
        child = Beneficiary.objects.create(name='Niño entregado', rut=rut_for(12345678), birth_date='2017-03-01')
        item = Enrollment.objects.create(campaign=self.campaign, beneficiary=child, attention=self.a1,
            delegation=self.d1, created_by=self.user1, status='APPROVED')
        GiftDelivery.objects.create(enrollment=item, delivered_by=self.user1, notes='Entregado')
        self.campaign.status = 'CLOSED'
        self.campaign.save(update_fields=['status'])
        res = self.client.post(reverse('municipal_events:campaign_delete', args=[self.campaign.pk]),
            {'reason': 'Cierre de campaña'})
        self.assertEqual(res.status_code, 302)
        self.campaign.refresh_from_db()
        self.assertIsNotNone(self.campaign.deleted_at)
        self.assertTrue(GiftDelivery.objects.filter(enrollment=item).exists())

    def test_campaign_filters_reuse_enrollment_delivery_and_audit(self):
        from .models import CampaignAudit, GiftDelivery
        child = Beneficiary.objects.create(name='Beneficiario filtro', rut=rut_for(12345678), birth_date='2017-03-01')
        item = Enrollment.objects.create(campaign=self.campaign, beneficiary=child, attention=self.a1,
            delegation=self.d1, created_by=self.user1, status='APPROVED')
        GiftDelivery.objects.create(enrollment=item, delivered_by=self.user1)
        CampaignAudit.objects.create(enrollment=item, action='ENTREGADO', actor=self.user1)
        perm = Permission.objects.get(content_type__app_label='municipal_events', codename='view_giftdelivery')
        self.group.permissions.add(perm)
        self.client.force_login(self.user1)
        url1 = reverse('municipal_events:enrollment_list') + '?campaign=' + str(self.campaign.pk)
        url2 = reverse('municipal_events:delivery_list') + '?campaign=' + str(self.campaign.pk)
        url3 = reverse('municipal_events:history_list') + '?campaign=' + str(self.campaign.pk)
        self.assertContains(self.client.get(url1), 'Beneficiario filtro')
        self.assertContains(self.client.get(url2), 'Beneficiario filtro')
        self.assertContains(self.client.get(url3), 'Beneficiario filtro')
        self.assertEqual(Enrollment.objects.filter(pk=item.pk).count(), 1)
        self.assertEqual(GiftDelivery.objects.filter(enrollment=item).count(), 1)

    def test_closed_campaign_with_pending_delivery_remains_active(self):
        child = Beneficiary.objects.create(name='Niño pendiente', rut=rut_for(12345678), birth_date='2017-03-01')
        Enrollment.objects.create(campaign=self.campaign, beneficiary=child, attention=self.a1,
            delegation=self.d1, created_by=self.user1, status='APPROVED')
        self.campaign.status = 'CLOSED'
        self.campaign.save(update_fields=['status'])
        res = self.client.post(reverse('municipal_events:campaign_delete', args=[self.campaign.pk]),
            {'reason': 'No corresponde'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(res.status_code, 409)
        self.campaign.refresh_from_db()
        self.assertIsNone(self.campaign.deleted_at)

    def test_edition_can_deactivate_with_only_withdrawn_participants(self):
        EventParticipation.objects.create(edition=self.edition, full_name='Participante retirado',
            rut=rut_for(12345678), email='retirado@example.com', created_by=self.user1,
            withdrawn_at=timezone.now())
        res = self.client.post(reverse('municipal_events:edition_delete', args=[self.edition.pk]),
            {'reason': 'Edición finalizada'})
        self.assertEqual(res.status_code, 302)
        self.edition.refresh_from_db()
        self.assertIsNotNone(self.edition.deleted_at)
        self.assertEqual(self.edition.participations.count(), 1)

    def test_application_review_capacity_and_duplicates(self):
        reg = reverse('municipal_events:participation_create', args=[self.edition.pk])
        data = {'full_name': 'Expositor Uno', 'rut': rut_for(12345678), 'email':'uno@example.com'}
        result = self.client.post(reg, data)
        self.assertEqual(result.status_code, 302)
        item = EventParticipation.objects.get()
        self.assertEqual(item.status, 'PENDING')
        self.assertEqual(self.client.post(reg, data).status_code, 200)
        self.assertEqual(EventParticipation.objects.count(), 1)
        self.assertEqual(self.client.post(reverse('municipal_events:participation_review', args=[item.pk]),
            {'decision':'ACCEPTED', 'reason':'Cumple requisitos'}).status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.status, 'ACCEPTED')
        second = {'full_name':'Expositor Dos', 'rut':rut_for(11111111), 'email':'dos@example.com'}
        self.assertEqual(self.client.post(reg, second).status_code, 302)
        pending = EventParticipation.objects.get(rut=second['rut'])
        res = self.client.post(reverse('municipal_events:participation_review', args=[pending.pk]),
            {'decision':'ACCEPTED', 'reason':'Sin cupo'})
        self.assertEqual(res.status_code, 200)
        pending.refresh_from_db()
        self.assertEqual(pending.status,'PENDING')

    def test_direct_registration_cannot_exceed_capacity(self):
        self.edition.participation_mode = 'REGISTRATION'
        self.edition.save(update_fields=['participation_mode'])
        reg = reverse('municipal_events:participation_create', args=[self.edition.pk])
        first = {'full_name':'Corredor Uno', 'rut':rut_for(12345678), 'email':'uno@example.com'}
        self.assertEqual(self.client.post(reg, first).status_code, 302)
        item=EventParticipation.objects.get()
        self.assertEqual(item.status,'REGISTERED')
        second = {'full_name':'Corredor Dos', 'rut':rut_for(11111111), 'email':'dos@example.com'}
        self.assertEqual(self.client.post(reg, second).status_code, 200)
        self.assertEqual(EventParticipation.objects.count(), 1)

    def test_public_cannot_register_event_participants(self):
        self.client.logout()
        self.assertEqual(self.client.post(reverse('municipal_events:participation_create', args=[self.edition.pk]),
            {'full_name':'No autorizado', 'rut':rut_for(12345678), 'email':'x@example.com'}).status_code, 302)
        user = User.objects.create_user('sin_permiso_evento', password='test')
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('municipal_events:participation_list', args=[self.edition.pk])).status_code, 403)
        self.assertEqual(EventParticipation.objects.count(), 0)
