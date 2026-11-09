"""Regresiones de permisos funcionales de Eventos (sin superusuario)."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from organization.permission_labels import catalog_permission_queryset, permission_label


class EventRolesPermissionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="permisos_eventos_qa", password="qa-fixture")
        self.client.force_login(self.user)

    def perm(self, code):
        return Permission.objects.get(content_type__app_label="municipal_events", codename=code)

    def test_catalog_contains_real_permissions(self):
        required = [
            "view_eventedition", "delete_municipalevent", "delete_eventedition", "delete_campaign",
            "view_eventparticipation", "add_eventparticipation", "change_eventparticipation",
            "evaluate_eventparticipation", "withdraw_eventparticipation", "reactivate_eventparticipation",
        ]
        for codename in required:
            with self.subTest(codename=codename):
                perm = self.perm(codename)
                self.assertTrue(catalog_permission_queryset(Permission.objects.filter(pk=perm.pk)).exists())
        self.assertFalse(catalog_permission_queryset(
            Permission.objects.filter(pk=self.perm("delete_eventparticipation").pk)
        ).exists())

    def test_delete_permission_is_labeled_as_logical_deactivation(self):
        for code in ("delete_municipalevent", "delete_eventedition", "delete_campaign"):
            self.assertIn("Puede desactivar", permission_label(self.perm(code)))

    def test_change_event_does_not_authorize_deactivation(self):
        self.user.user_permissions.add(self.perm("change_municipalevent"))
        res = self.client.get(reverse("municipal_events:event_delete", args=[987654321]))
        self.assertEqual(res.status_code, 403)
        self.user.user_permissions.add(self.perm("delete_municipalevent"))
        res = self.client.get(reverse("municipal_events:event_delete", args=[987654321]))
        self.assertEqual(res.status_code, 404)  # Permiso válido; registro inexistente

    def test_participation_actions_do_not_inherit_edition_change(self):
        self.user.user_permissions.add(self.perm("change_eventedition"))
        actions = {
            "participation_list": "view_eventparticipation",
            "participation_create": "add_eventparticipation",
            "participation_detail": "view_eventparticipation",
            "participation_edit": "change_eventparticipation",
            "participation_review": "evaluate_eventparticipation",
            "participation_withdraw": "withdraw_eventparticipation",
            "participation_reactivate": "reactivate_eventparticipation",
        }
        for url_name, code in actions.items():
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse("municipal_events:" + url_name, args=[987654321]))
                self.assertEqual(response.status_code, 403)
                self.user.user_permissions.add(self.perm(code))
                response = self.client.get(reverse("municipal_events:" + url_name, args=[987654321]))
                self.assertEqual(response.status_code, 404)
                self.user.user_permissions.remove(self.perm(code))
