"""Pruebas del primer ingreso; no dependen de superusuario."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from accounts.models import UserProfile


class FirstLoginPasswordChangeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='sgr_primer_ingreso',
            email='sgr_primer_ingreso@example.invalid',
            password='Temporal#Seguro2026',
        )
        UserProfile.objects.create(
            user=self.user, employee_code='SGR-PRIMER-001',
            must_change_password=True,
        )
        self.url = reverse('accounts:first_login_password_change')

    def test_redirects_to_required_password_change(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('accounts:profile'))
        self.assertRedirects(response, self.url, fetch_redirect_response=False)

    def test_change_screen_is_available(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Cambia tu contraseña temporal')

    def test_wrong_previous_password_does_not_unlock(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {
            'old_password':'Incorrecta#123',
            'new_password1':'Definitiva#Segura2027',
            'new_password2':'Definitiva#Segura2027',
        })
        self.assertEqual(response.status_code, 200)
        self.user.profile.refresh_from_db()
        self.assertTrue(self.user.profile.must_change_password)

    def test_same_password_cannot_be_kept(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {
            'old_password':'Temporal#Seguro2026',
            'new_password1':'Temporal#Seguro2026',
            'new_password2':'Temporal#Seguro2026',
        })
        self.assertEqual(response.status_code, 200)
        self.user.profile.refresh_from_db()
        self.assertTrue(self.user.profile.must_change_password)

    def test_new_password_releases_access_and_keeps_session(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {
            'old_password':'Temporal#Seguro2026',
            'new_password1':'Definitiva#Segura2027',
            'new_password2':'Definitiva#Segura2027',
        })
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Definitiva#Segura2027'))
        self.user.profile.refresh_from_db()
        self.assertFalse(self.user.profile.must_change_password)
        self.assertTrue('_auth_user_id' in self.client.session)

    def test_existing_account_does_not_require_change(self):
        second = get_user_model().objects.create_user(
            username='sgr_usuario_preexistente', password='Existente#2026',
        )
        profile = UserProfile.objects.create(
            user=second, employee_code='SGR-EXISTENTE-002',
        )
        self.assertFalse(profile.must_change_password)
        self.client.force_login(second)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertNotEqual(response.url, self.url)
