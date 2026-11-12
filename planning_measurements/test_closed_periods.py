from datetime import date
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse
from .models import Period, PeriodArchiveLog


class ClosedPeriodArchiveTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("archivo-períodos", password="Seguro2026!clave")
        self.user.user_permissions.add(Permission.objects.get(
            content_type__app_label="planning_measurements", codename="delete_period",
        ))
        self.period = Period.objects.create(
            start_date=date(2026, 1, 1), end_date=date(2026, 1, 31),
            computable_days=21, thresholds="70%,80%", parameters_version="v1",
            status=Period.Status.CLOSED,
        )
        self.client.force_login(self.user)

    def test_closed_period_cannot_be_archived_without_special_permission(self):
        url = reverse("planning:period_delete", kwargs={"period_id": self.period.pk})
        self.assertEqual(self.client.post(url).status_code, 403)
        self.period.refresh_from_db()
        self.assertIsNone(self.period.deleted_at)
        special = Permission.objects.get(
            content_type__app_label="planning_measurements", codename="delete_closed_period",
        )
        self.user.user_permissions.add(special)
        result = self.client.post(url)
        self.assertEqual(result.status_code, 403)
        self.period.refresh_from_db()
        self.assertIsNone(self.period.deleted_at)

    def test_closed_period_cannot_be_archived_with_special_permission_in_role(self):
        self.user.user_permissions.add(Permission.objects.get(
            content_type__app_label="planning_measurements",
            codename="delete_period",
        ))
        role = Group.objects.create(name="Rol archivado")
        role.permissions.add(Permission.objects.get(
            content_type__app_label="planning_measurements",
            codename="delete_closed_period",
        ))
        self.user.groups.add(role)

        response = self.client.post(
            reverse("planning:period_delete", kwargs={"period_id": self.period.pk})
        )

        self.assertEqual(response.status_code, 403)
        self.period.refresh_from_db()
        self.assertIsNone(self.period.deleted_at)

    def test_period_list_shows_closed_archive_action_for_role_permission(self):
        self.user.user_permissions.add(Permission.objects.get(
            content_type__app_label="planning_measurements",
            codename="view_period",
        ))
        role = Group.objects.create(name="Rol visible")
        role.permissions.add(
            Permission.objects.get(
                content_type__app_label="planning_measurements",
                codename="delete_closed_period",
            )
        )
        self.user.groups.add(role)

        response = self.client.get(reverse("planning:period_list"))

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("can_archive_closed_period", response.context)

    def test_period_list_hides_closed_archive_action_without_special_permission(self):
        self.user.user_permissions.add(Permission.objects.get(
            content_type__app_label="planning_measurements",
            codename="view_period",
        ))

        response = self.client.get(reverse("planning:period_list"))

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("can_archive_closed_period", response.context)
        self.assertNotContains(response, 'data-swal-delete="período"')

    def test_period_list_hides_closed_archive_action_with_special_permission(self):
        self.user.user_permissions.add(Permission.objects.get(
            content_type__app_label="planning_measurements",
            codename="view_period",
        ))
        self.user.user_permissions.add(Permission.objects.get(
            content_type__app_label="planning_measurements",
            codename="delete_closed_period",
        ))

        response = self.client.get(reverse("planning:period_list"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'data-swal-delete="período"')

    def test_closed_special_permission_does_not_replace_delete_period(self):
        self.user.user_permissions.remove(Permission.objects.get(
            content_type__app_label="planning_measurements",
            codename="delete_period",
        ))
        role = Group.objects.create(name="Rol sin eliminación normal")
        role.permissions.add(Permission.objects.get(
            content_type__app_label="planning_measurements",
            codename="delete_closed_period",
        ))
        self.user.groups.add(role)

        response = self.client.post(
            reverse("planning:period_delete", kwargs={"period_id": self.period.pk})
        )

        self.assertEqual(response.status_code, 403)
        self.period.refresh_from_db()
        self.assertIsNone(self.period.deleted_at)

    def test_active_period_without_goals_is_archived_logically(self):
        active = Period.objects.create(
            start_date=date(2026, 2, 1), end_date=date(2026, 2, 28),
            computable_days=20, thresholds="70%,80%", parameters_version="v1",
            status=Period.Status.ACTIVE,
        )
        response = self.client.post(
            reverse("planning:period_delete", kwargs={"period_id": active.pk})
        )

        self.assertEqual(response.status_code, 302)
        active.refresh_from_db()
        self.assertIsNotNone(active.deleted_at)
        self.assertTrue(PeriodArchiveLog.objects.filter(
            period=active, user=self.user, was_closed=False,
        ).exists())

    def test_bulk_delete_rejects_closed_period_without_goals(self):
        self.user.user_permissions.add(Permission.objects.get(
            content_type__app_label="planning_measurements",
            codename="view_period",
        ))
        response = self.client.post(
            reverse("planning:period_list"),
            {
                "action": "delete_selected",
                "_selected_action": [str(self.period.pk)],
            },
        )

        self.assertEqual(response.status_code, 403)
        self.period.refresh_from_db()
        self.assertIsNone(self.period.deleted_at)
