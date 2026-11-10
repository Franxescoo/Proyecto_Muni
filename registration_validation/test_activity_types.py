from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from .forms import ActivityTypeForm
from .models import ActivityType


class ActivityTypeCrudTests(TestCase):

    def setUp(self):
        self.admin_user = (
            get_user_model().objects.create_superuser(
                username="admin-tipos-actividad",
                password="ClavePrueba123!",
                email="admin@example.test",
            )
        )

        self.client.force_login(self.admin_user)

        self.list_url = reverse(
            "registration:activity_type_list"
        )

        self.create_url = reverse(
            "registration:activity_type_create"
        )

    def test_create_and_list(self):
        response = self.client.post(self.create_url, {
            "code": "ACT-001",
            "name": "Visita a terreno",
            "description": "Inspección",
            "status": "True",
        })

        self.assertRedirects(response, self.list_url)

        self.assertTrue(
            ActivityType.objects.filter(
                code="ACT-001"
            ).exists()
        )

        self.assertContains(
            self.client.get(self.list_url),
            "Visita a terreno",
        )

    def test_empty_name_is_rejected(self):
        response = self.client.post(self.create_url, {
            "code": "ACT-002",
            "name": " ",
            "description": "",
            "status": "True",
        })

        self.assertEqual(response.status_code, 200)

        self.assertFalse(
            ActivityType.objects.filter(
                code="ACT-002"
            ).exists()
        )

    def test_duplicate_code_case_insensitive_is_rejected(self):
        ActivityType.objects.create(
            code="ACT-003",
            name="Original",
        )

        response = self.client.post(self.create_url, {
            "code": "act-003",
            "name": "Duplicado",
            "status": "True",
        })

        self.assertEqual(response.status_code, 200)

        self.assertContains(
            response,
            "Ya existe un tipo de actividad",
        )

        self.assertEqual(
            ActivityType.objects.count(),
            1,
        )

    def test_update(self):
        item = ActivityType.objects.create(
            code="ACT-004",
            name="Anterior",
        )

        response = self.client.post(
            reverse(
                "registration:activity_type_update",
                args=[item.pk],
            ),
            {
                "code": item.code,
                "name": "Actualizado",
                "description": "Nuevo texto",
                "status": "True",
            },
        )

        self.assertRedirects(response, self.list_url)

        item.refresh_from_db()

        self.assertEqual(item.name, "Actualizado")

    def test_deactivate_and_reactivate(self):
        item = ActivityType.objects.create(
            code="ACT-005",
            name="Cambiante",
        )

        url = reverse(
            "registration:activity_type_update",
            args=[item.pk],
        )

        for status, expected in [
            ("False", False),
            ("True", True),
        ]:
            response = self.client.post(url, {
                "code": item.code,
                "name": item.name,
                "status": status,
            })

            self.assertRedirects(response, self.list_url)

            item.refresh_from_db()

            self.assertIs(item.status, expected)

    def test_filter_by_status_and_search(self):
        ActivityType.objects.create(
            code="ACT-006",
            name="Reunión",
            status=True,
        )

        ActivityType.objects.create(
            code="ACT-007",
            name="Archivo",
            status=False,
        )

        self.assertContains(
            self.client.get(
                self.list_url + "?status=active"
            ),
            "Reunión",
        )

        self.assertNotContains(
            self.client.get(
                self.list_url + "?status=active"
            ),
            "Archivo",
        )

        self.assertContains(
            self.client.get(
                self.list_url + "?q=ACT-007"
            ),
            "Archivo",
        )

    def test_delete_is_soft_delete_and_post_only(self):
        item = ActivityType.objects.create(
            code="ACT-008",
            name="Temporal",
        )

        url = reverse(
            "registration:activity_type_delete",
            args=[item.pk],
        )

        self.assertEqual(
            self.client.get(url).status_code,
            405,
        )

        self.assertRedirects(
            self.client.post(url),
            self.list_url,
        )

        item.refresh_from_db()

        self.assertIsNotNone(item.deleted_at)

        self.assertNotContains(
            self.client.get(self.list_url),
            "Temporal",
        )

        self.assertEqual(
            self.client.post(url).status_code,
            404,
        )

    def test_user_without_permissions_is_denied(self):
        user = get_user_model().objects.create_user(
            username="sin-permisos-tipos",
            password="ClavePrueba123!",
        )

        self.client.force_login(user)

        self.assertEqual(
            self.client.get(self.list_url).status_code,
            403,
        )

        self.assertEqual(
            self.client.get(self.create_url).status_code,
            403,
        )

    def test_view_only_cannot_modify(self):
        user = get_user_model().objects.create_user(
            username="solo-lectura-tipos",
            password="ClavePrueba123!",
        )

        user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="registration_validation",
                codename="view_activitytype",
            )
        )

        item = ActivityType.objects.create(
            code="ACT-009",
            name="Consulta",
        )

        self.client.force_login(user)

        self.assertEqual(
            self.client.get(self.list_url).status_code,
            200,
        )

        self.assertNotContains(
            self.client.get(self.list_url),
            "Agregar tipo de actividad",
        )

        response = self.client.post(self.create_url, {
            "code": "ACT-010",
            "name": "No autorizado",
            "status": "True",
        })

        self.assertEqual(response.status_code, 403)

        delete_url = reverse(
            "registration:activity_type_delete",
            args=[item.pk],
        )

        self.assertEqual(
            self.client.post(delete_url).status_code,
            403,
        )

        self.assertIsNone(
            ActivityType.objects.get(pk=item.pk).deleted_at
        )

    def test_form_uses_activity_type_and_validates_data(self):
        form = ActivityTypeForm(data={
            "code": " ACT-011 ",
            "name": " Reunión ",
            "status": "True",
        })

        self.assertTrue(
            form.is_valid(),
            form.errors,
        )

        self.assertEqual(
            form.cleaned_data["code"],
            "ACT-011",
        )

        self.assertEqual(
            form.cleaned_data["name"],
            "Reunión",
        )

    def test_text_limits_are_enforced_server_side_and_in_html(self):
        form = ActivityTypeForm(data={
            "code": "C" * 51,
            "name": "N" * 151,
            "description": "D" * 301,
            "status": "True",
        })

        self.assertFalse(form.is_valid())
        self.assertIn("code", form.errors)
        self.assertIn("name", form.errors)
        self.assertIn("description", form.errors)
        self.assertEqual(form.fields["code"].widget.attrs["maxlength"], 50)
        self.assertEqual(form.fields["name"].widget.attrs["maxlength"], 150)
        self.assertEqual(
            form.fields["description"].widget.attrs["maxlength"],
            300,
        )