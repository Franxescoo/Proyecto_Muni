from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import UserProfile
from organization.models import Delegation, Employee, PositionFunction
from .models import InstitutionalMessage


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                   DEFAULT_FROM_EMAIL='correo-sgr@example.org')
class InstitutionalMailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        delegation = Delegation.objects.create(
            code='DEMO-MAIL', name='Delegación de Prueba', status='Activa', scope='Gestión',
        )
        position = PositionFunction.objects.create(
            position_name='Funcionario', measurable_items='', services='', weightings='',
            validity_start=date(2026, 1, 1), validity_end=date(2027, 1, 1),
        )
        cls.u1 = User.objects.create_user('autor_sgr', password='testpass123', email='autor@example.org')
        cls.u2 = User.objects.create_user('destino_sgr', password='testpass123', email='destino@example.org')
        cls.u3 = User.objects.create_user('ajeno_sgr', password='testpass123', email='ajeno@example.org')
        cls.u4 = User.objects.create_user('cuarto_sgr', password='testpass123', email='cuarto@example.org')
        cls.ghost = User.objects.create_user('usuario_sin_funcionario', password='testpass123', email='ghost@example.org')
        for i, user in enumerate((cls.u1, cls.u2, cls.u3, cls.u4), start=1):
            employee = Employee.objects.create(name=user.username, delegation=delegation, position=position,
                                               roles='', status='Activo')
            UserProfile.objects.create(user=user, employee=employee, employee_code=f'MAIL-{i}', delegation=delegation)

    def setUp(self):
        self.client.force_login(self.u1)

    def send(self, **values):
        payload = {'recipient': self.u2.pk, 'subject': 'Informe mensual', 'body': 'Favor revisar informe.'}
        payload.update(values)
        return self.client.post(reverse('institutional_mail:send'), payload)

    def test_sending_creates_internal_message_and_real_email(self):
        response = self.send()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(InstitutionalMessage.objects.count(), 1)
        msg = InstitutionalMessage.objects.get()
        self.assertEqual(msg.sender, self.u1)
        self.assertEqual(msg.recipient, self.u2)
        self.assertEqual(msg.notice_status, 'SENT')
        self.assertEqual(mail.outbox[0].to, ['destino@example.org'])

    def test_inbox_and_sent_are_separated(self):
        self.send()
        sent = self.client.get(reverse('institutional_mail:messages'), {'folder':'sent'}).json()
        received = self.client.get(reverse('institutional_mail:messages'), {'folder':'inbox'}).json()
        self.assertEqual(sent['total'], 1)
        self.assertEqual(received['total'], 0)
        self.client.force_login(self.u2)
        received = self.client.get(reverse('institutional_mail:messages'), {'folder':'inbox'}).json()
        self.assertEqual(received['total'], 1)

    def test_message_detail_hidden_from_other_employee(self):
        self.send()
        pk = InstitutionalMessage.objects.get().pk
        self.client.force_login(self.u3)
        self.assertEqual(self.client.get(reverse('institutional_mail:detail',args=[pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('institutional_mail:archive',args=[pk]), {'archive':'1'}).status_code, 404)

    def test_no_access_for_logged_out_and_unlinked_accounts(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('institutional_mail:messages')).status_code, 302)
        self.client.force_login(self.ghost)
        self.assertEqual(self.client.get(reverse('institutional_mail:messages')).status_code, 403)
        self.assertEqual(self.send().status_code, 403)

    def test_read_mark_is_restricted_to_recipient(self):
        self.send()
        msg = InstitutionalMessage.objects.get()
        route = reverse('institutional_mail:read',args=[msg.pk])
        self.assertEqual(self.client.post(route).status_code, 404)
        self.client.force_login(self.u2)
        self.assertEqual(self.client.get(reverse('institutional_mail:unread')).json()['unread'], 1)
        self.assertEqual(self.client.post(route).status_code, 200)
        self.assertEqual(self.client.get(reverse('institutional_mail:unread')).json()['unread'], 0)

    def test_archive_only_affects_current_users_view(self):
        self.send()
        msg = InstitutionalMessage.objects.get()
        self.client.force_login(self.u2)
        self.client.post(reverse('institutional_mail:archive',args=[msg.pk]), {'archive':'1'})
        self.assertEqual(self.client.get(reverse('institutional_mail:messages'),{'folder':'inbox'}).json()['total'], 0)
        self.assertEqual(self.client.get(reverse('institutional_mail:messages'),{'folder':'archive'}).json()['total'], 1)
        self.client.force_login(self.u1)
        self.assertEqual(self.client.get(reverse('institutional_mail:messages'),{'folder':'sent'}).json()['total'], 1)

    def test_reply_to_other_participant(self):
        self.send()
        original = InstitutionalMessage.objects.get()
        self.client.force_login(self.u2)
        reply = self.client.post(reverse('institutional_mail:send'), {
            'recipient':self.u1.pk, 'subject':'Re: Informe mensual', 'body':'Recibido', 'reply_to': original.pk
        })
        self.assertEqual(reply.status_code, 201)
        self.assertEqual(InstitutionalMessage.objects.get(subject='Re: Informe mensual').reply_to_id, original.pk)
        forged = self.client.post(reverse('institutional_mail:send'), {
            'recipient':self.u3.pk, 'subject':'Re: Informe mensual', 'body':'Recibido', 'reply_to': original.pk
        })
        self.assertEqual(forged.status_code, 400)

    def test_cannot_send_to_self_or_unlinked(self):
        self.assertEqual(self.send(recipient=self.u1.pk).status_code, 400)
        self.assertEqual(self.send(recipient=self.ghost.pk).status_code, 400)
        self.assertEqual(InstitutionalMessage.objects.count(), 0)

    def test_failed_email_keeps_internal_message(self):
        with patch('institutional_mail.views.send_mail',side_effect=OSError('SMTP offline')):
            response = self.send()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(InstitutionalMessage.objects.get().notice_status,'FAILED')

    def test_get_does_not_mark_read_and_post_required(self):
        self.send()
        msg = InstitutionalMessage.objects.get()
        self.client.force_login(self.u2)
        self.client.get(reverse('institutional_mail:detail',args=[msg.pk]))
        msg.refresh_from_db()
        self.assertIsNone(msg.read_at)
        self.assertEqual(self.client.get(reverse('institutional_mail:read',args=[msg.pk])).status_code, 405)

    def test_recipients_are_linked_users_only(self):
        data = self.client.get(reverse('institutional_mail:recipients')).json()
        names = {u['name'] for u in data['recipients']}
        self.assertNotIn('usuario_sin_funcionario', names)
        self.assertEqual(len(names), 3)

    def test_base_template_includes_mail_modal_and_button(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'sgrInstitutionalMailModal')
        self.assertContains(response, 'Correo')

    def test_multi_recipient_creates_private_copies_and_one_sent_item(self):
        response = self.client.post(reverse('institutional_mail:send'), {
            'recipients': f'{self.u2.pk},{self.u3.pk}',
            'subject': 'Mensaje conjunto', 'body': 'Saludos a ambos',
        })
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['recipient_count'], 2)
        self.assertEqual(response.json()['sent_emails'], 2)
        copies = list(InstitutionalMessage.objects.filter(subject='Mensaje conjunto').order_by('pk'))
        self.assertEqual(len(copies), 2)
        self.assertEqual(copies[0].batch_id, copies[1].batch_id)
        self.assertEqual({c.recipient_id for c in copies}, {self.u2.pk, self.u3.pk})
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual({m.to[0] for m in mail.outbox}, {'destino@example.org', 'ajeno@example.org'})
        sent = self.client.get(reverse('institutional_mail:messages'), {'folder':'sent'}).json()
        self.assertEqual(sent['total'], 1)
        self.assertEqual(sent['messages'][0]['recipient_count'], 2)
        detail = self.client.get(reverse('institutional_mail:detail', args=[copies[0].pk])).json()['message']
        self.assertEqual(len(detail['recipients']), 2)
        self.client.force_login(self.u2)
        self.assertEqual(self.client.get(reverse('institutional_mail:messages'), {'folder':'inbox'}).json()['total'], 1)
        detail = self.client.get(reverse('institutional_mail:detail', args=[copies[0].pk])).json()['message']
        self.assertEqual(len(detail['recipients']), 1)
        self.assertEqual(self.client.get(reverse('institutional_mail:detail', args=[copies[1].pk])).status_code, 404)

    def test_multi_archive_groups_sent_without_archiving_received(self):
        response = self.client.post(reverse('institutional_mail:send'), {
            'recipients': f'{self.u2.pk},{self.u3.pk}',
            'subject': 'Mensaje conjunto', 'body': 'Saludos a ambos',
        })
        self.assertEqual(response.status_code, 201)
        first = InstitutionalMessage.objects.order_by('pk').first()
        self.client.post(reverse('institutional_mail:archive', args=[first.pk]), {'archive':'1'})
        self.assertEqual(InstitutionalMessage.objects.filter(sender_archived_at__isnull=False).count(), 2)
        self.assertEqual(self.client.get(reverse('institutional_mail:messages'), {'folder':'archive'}).json()['total'], 1)
        self.assertEqual(self.client.get(reverse('institutional_mail:messages'), {'folder':'sent'}).json()['total'], 0)
        self.client.force_login(self.u2)
        self.assertEqual(self.client.get(reverse('institutional_mail:messages'), {'folder':'inbox'}).json()['total'], 1)

    def test_reject_duplicate_nonexistent_and_unlinked_recipients(self):
        for csv in (f'{self.u2.pk},{self.u2.pk}', f'{self.u2.pk},999999',
                    f'{self.u2.pk},{self.ghost.pk}', f'{self.u1.pk},{self.u2.pk}'):
            response = self.client.post(reverse('institutional_mail:send'), {
                'recipients':csv, 'subject':'Prueba', 'body':'Texto de prueba',
            })
            self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(InstitutionalMessage.objects.count(), 0)

    def test_no_arbitrary_address_in_recipients_field(self):
        response = self.client.post(reverse('institutional_mail:send'), {
            'recipients':'destino@example.org', 'subject':'Prueba', 'body':'Texto de prueba',
        })
        self.assertEqual(response.status_code, 400)

    def test_rate_limit_counts_individual_deliveries(self):
        for _ in range(29):
            InstitutionalMessage.objects.create(sender=self.u1, recipient=self.u2,
                subject='Anterior', body='Test')
        response = self.client.post(reverse('institutional_mail:send'), {
            'recipients':f'{self.u2.pk},{self.u3.pk}', 'subject':'Nuevo', 'body':'Texto',
        })
        self.assertEqual(response.status_code, 429)
        self.assertEqual(InstitutionalMessage.objects.count(), 29)

    def test_replies_reject_multiple_recipients(self):
        self.send()
        original = InstitutionalMessage.objects.get()
        self.client.force_login(self.u2)
        response = self.client.post(reverse('institutional_mail:send'), {
            'recipients':f'{self.u1.pk},{self.u3.pk}', 'subject':'Re: test',
            'body':'Respuesta', 'reply_to':original.pk,
        })
        self.assertEqual(response.status_code, 400)
