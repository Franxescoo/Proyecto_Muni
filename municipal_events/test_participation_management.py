# SGR_PERMISOS_EVENTOS_V2
"""Gestión de participantes: permisos normales, cupos, auditoría y límites de texto."""
from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from municipal_events.tests import CampaignWorkflowTests
from .forms import (CampaignForm, DeliveryForm, EditionForm, EnrollmentForm,
                    EventForm, EventParticipationEditForm, EventParticipationForm,
                    EventParticipationReviewForm, ReviewForm)
from .models import EventActionAudit, EventEdition, EventParticipation, MunicipalEvent


def valid_rut(base):
    digits = str(base)
    total = sum(int(x) * (2 + i % 6) for i, x in enumerate(reversed(digits)))
    remainder = 11 - total % 11
    return digits + ('0' if remainder == 11 else 'K' if remainder == 10 else str(remainder))


class ParticipationManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CampaignWorkflowTests.setUpTestData.__func__(cls)
        cls.group.permissions.add(*Permission.objects.filter(
            content_type__app_label='municipal_events', codename__in=[
                'view_eventedition', 'change_eventedition', 'change_municipalevent',
                'view_eventparticipation', 'add_eventparticipation', 'change_eventparticipation',
                'evaluate_eventparticipation', 'withdraw_eventparticipation',
                'reactivate_eventparticipation',
            ]))

    def setUp(self):
        self.client.force_login(self.user1)
        today = timezone.localdate()
        self.event = MunicipalEvent.objects.create(name='Verbena Pruebas', created_by=self.user1)
        self.edition = EventEdition.objects.create(
            event=self.event, year=today.year, date=today, place='La Serena',
            delegation=self.d1, responsible=self.user1,
            participation_mode='APPLICATION', participation_capacity=1)
        self.participant = EventParticipation.objects.create(
            edition=self.edition, full_name='Participante Uno', rut=valid_rut(12345678),
            email='uno@example.com', status='ACCEPTED', created_by=self.user1)

    def test_edit_does_not_change_rut_or_edition_and_registers_audit(self):
        url = reverse('municipal_events:participation_edit', args=[self.participant.pk])
        response = self.client.post(url, {
            'full_name': 'Nombre Corregido', 'email': 'nuevo@example.com',
            'description': 'Antecedentes corregidos', 'rut': valid_rut(11111111),
            'edition': 9000, 'status': 'REJECTED',
        })
        self.assertEqual(response.status_code, 302)
        self.participant.refresh_from_db()
        self.assertEqual(self.participant.rut, valid_rut(12345678))
        self.assertEqual(self.participant.edition, self.edition)
        self.assertEqual(self.participant.status, 'ACCEPTED')
        self.assertEqual(self.participant.full_name, 'Nombre Corregido')
        self.assertTrue(EventActionAudit.objects.filter(participation=self.participant, action='MODIFICADO').exists())

    def test_withdraw_list_reactivate_keep_same_pk_and_history(self):
        withdraw = reverse('municipal_events:participation_withdraw', args=[self.participant.pk])
        restore = reverse('municipal_events:participation_reactivate', args=[self.participant.pk])
        list_url = reverse('municipal_events:participation_list', args=[self.edition.pk])
        self.assertEqual(self.client.post(withdraw, {'reason': 'Desistió'}).status_code, 302)
        self.participant.refresh_from_db()
        self.assertIsNotNone(self.participant.withdrawn_at)
        self.assertNotContains(self.client.get(list_url), 'Participante Uno')
        self.assertContains(self.client.get(list_url+'?state=withdrawn'), 'Participante Uno')
        self.assertEqual(self.client.post(restore, {'reason': 'Regresó'}).status_code, 302)
        self.participant.refresh_from_db()
        self.assertIsNone(self.participant.withdrawn_at)
        self.assertEqual(EventParticipation.objects.filter(edition=self.edition).count(), 1)
        self.assertEqual(list(EventActionAudit.objects.filter(participation=self.participant).values_list('action', flat=True)), ['REACTIVADO', 'RETIRADO'])
        self.assertContains(self.client.get(reverse('municipal_events:participation_detail', args=[self.participant.pk])), 'Desistió')

    def test_restore_cannot_overbook(self):
        self.client.post(reverse('municipal_events:participation_withdraw', args=[self.participant.pk]), {'reason': 'Salir'})
        EventParticipation.objects.create(edition=self.edition, full_name='Otro',
            rut=valid_rut(11111111), email='otro@example.com',
            status='ACCEPTED', created_by=self.user1)
        restore = reverse('municipal_events:participation_reactivate', args=[self.participant.pk])
        response = self.client.post(restore, {'reason': 'Volver'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 409)
        self.participant.refresh_from_db()
        self.assertIsNotNone(self.participant.withdrawn_at)

    def test_withdrawn_participant_is_not_evaluated_or_edited(self):
        self.participant.status = 'PENDING'
        self.participant.save(update_fields=['status'])
        self.client.post(reverse('municipal_events:participation_withdraw', args=[self.participant.pk]), {'reason': 'Salir'})
        self.assertEqual(self.client.get(reverse('municipal_events:participation_edit', args=[self.participant.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse('municipal_events:participation_review', args=[self.participant.pk]), {'decision': 'ACCEPTED', 'reason': 'OK'}).status_code, 403)

    def test_reason_500_limit_is_checked_in_server(self):
        response = self.client.post(reverse('municipal_events:participation_withdraw', args=[self.participant.pk]), {'reason': 'x'*501}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 409)
        self.participant.refresh_from_db()
        self.assertIsNone(self.participant.withdrawn_at)

    def test_view_only_does_not_grant_change(self):
        self.group.permissions.remove(Permission.objects.get(content_type__app_label='municipal_events', codename='withdraw_eventparticipation'))
        self.user1 = User.objects.get(pk=self.user1.pk)
        self.client.force_login(self.user1)
        self.assertEqual(self.client.get(reverse('municipal_events:participation_detail', args=[self.participant.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('municipal_events:participation_withdraw', args=[self.participant.pk])).status_code, 403)

    def test_text_fields_have_maxlength_and_server_validation(self):
        for form in (EventForm(), EditionForm(), CampaignForm(), EnrollmentForm(),
                     ReviewForm(), DeliveryForm(), EventParticipationForm(),
                     EventParticipationEditForm(), EventParticipationReviewForm()):
            for name, field in form.fields.items():
                from django import forms
                if isinstance(field, forms.CharField):
                    self.assertIsNotNone(field.max_length, f'{type(form).__name__}.{name}')
                    self.assertEqual(str(field.max_length), field.widget.attrs.get('maxlength'), f'{type(form).__name__}.{name}')
        form = EventForm({'name': 'Evento', 'description': 'x'*2001})
        self.assertFalse(form.is_valid())
        self.assertIn('description', form.errors)
        edit = EventParticipationEditForm({'full_name': 'Persona', 'email':'uno@example.com', 'description':'x'*1201})
        self.assertFalse(edit.is_valid())
        self.assertIn('description', edit.errors)
