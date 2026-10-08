from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from organization.models import (
    Delegation,
    Employee,
    PositionFunction,
)

from .forms import GoalForm, GoalInlineForm, PeriodForm
from .models import Goal, Period
from .views import scoped_goals


class PlanningTests(TestCase):
    def setUp(self):
        self.delegation = Delegation.objects.create(
            name="Norte",
            status="Active",
            scope="Local",
        )

        other_delegation = Delegation.objects.create(
            name="Sur",
            status="Active",
            scope="Local",
        )

        self.position = PositionFunction.objects.create(
            position_name="Technician",
            measurable_items="Items",
            services="Services",
            weightings="Weights",
            validity_start=date(2026, 1, 1),
            validity_end=date(2026, 12, 31),
        )

        self.employee = Employee.objects.create(
            name="Peter",
            delegation=self.delegation,
            position=self.position,
            roles="Staff",
            status="Active",
        )

        self.outside = Employee.objects.create(
            name="Other",
            delegation=other_delegation,
            position=self.position,
            roles="Staff",
            status="Active",
        )

        self.period = Period.objects.create(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            computable_days=200,
            status="Active",
            thresholds="Thresholds",
            parameters_version="1",
        )

        self.form_user = SimpleNamespace(
            is_superuser=False,
            profile=SimpleNamespace(
                delegation_id=self.delegation.pk
            ),
        )

        self.data = {
            "period": self.period.pk,
            "employee": self.employee.pk,
            "item": "Meta",
            "objective_value": "100",
            "unit": "Items",
            "weight": "50",
        }

    def account(self, *codenames, superuser=False):
        user = get_user_model().objects.create_user(
            username="review_user",
            password="Test-password-123",
            is_superuser=superuser,
            is_staff=superuser,
        )

        user.user_permissions.set(
            Permission.objects.filter(
                content_type__app_label="planning_measurements",
                codename__in=codenames,
            )
        )

        UserProfile.objects.create(
            user=user,
            employee_code="TEST-001",
            delegation=self.delegation,
        )

        self.client.force_login(user)
        return user

    def create_goal(self, **changes):
        values = {
            "period": self.period,
            "employee": self.employee,
            "position": self.position,
            "item": "Meta confidencial",
            "objective_value": 100,
            "unit": "Items",
            "weight": 50,
        }

        values.update(changes)
        return Goal.objects.create(**values)

    def period_data(self):
        return {
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "computable_days": 200,
            "status": "Active",
            "thresholds": "Thresholds",
            "parameters_version": "1",
        }

    def inline_data(self):
        data = self.period_data()

        data.update({
            "goals-TOTAL_FORMS": 1,
            "goals-INITIAL_FORMS": 0,
            "goals-MIN_NUM_FORMS": 0,
            "goals-MAX_NUM_FORMS": 1000,
        })

        for field, value in self.data.items():
            if field != "period":
                data["goals-0-" + field] = value

        return data

    def test_create_without_posted_position(self):
        form = GoalForm(self.data, user=self.form_user)

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.save().position_id,
            self.position.pk,
        )

    def test_posted_position_is_ignored(self):
        form = GoalForm(
            {**self.data, "position": "999999"},
            user=self.form_user,
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.save().position_id,
            self.position.pk,
        )

    def test_outside_employee_is_rejected(self):
        form = GoalForm(
            {**self.data, "employee": self.outside.pk},
            user=self.form_user,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("employee", form.errors)

    def test_edit_employee_updates_position(self):
        goal = self.create_goal()

        position = PositionFunction.objects.create(
            position_name="Director",
            measurable_items="Items",
            services="Services",
            weightings="Weights",
            validity_start=date(2026, 1, 1),
            validity_end=date(2026, 12, 31),
        )

        employee = Employee.objects.create(
            name="New",
            delegation=self.delegation,
            position=position,
            roles="Staff",
            status="Active",
        )

        form = GoalForm(
            {**self.data, "employee": employee.pk},
            instance=goal,
            user=self.form_user,
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.save().position_id,
            position.pk,
        )

    def test_inline_uses_automatic_position(self):
        form = GoalInlineForm(
            self.data,
            user=self.form_user,
        )

        form.instance.period = self.period

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.save().position_id,
            self.position.pk,
        )

    def test_archived_position_is_rejected(self):
        self.position.deleted_at = timezone.now()
        self.position.save()

        form = GoalForm(
            self.data,
            user=self.form_user,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("position", form.errors)

    def test_goal_rejects_zero_and_negative_objectives(self):
        for value in ["0", "-1"]:
            with self.subTest(value=value):
                form = GoalForm(
                    {**self.data, "objective_value": value},
                    user=self.form_user,
                )

                self.assertFalse(form.is_valid())
                self.assertIn("objective_value", form.errors)

    def test_goal_rejects_out_of_range_weights(self):
        for value in ["-1", "101"]:
            with self.subTest(value=value):
                form = GoalForm(
                    {**self.data, "weight": value},
                    user=self.form_user,
                )

                self.assertFalse(form.is_valid())
                self.assertIn("weight", form.errors)

    def test_period_rejects_invalid_dates_days_and_status(self):
        cases = [
            ({"end_date": "2025-12-31"}, "end_date"),
            ({"computable_days": "0"}, "computable_days"),
            ({"computable_days": "-1"}, "computable_days"),
            ({"computable_days": "366"}, "computable_days"),
            ({"status": "inventado"}, "status"),
        ]

        for changes, field in cases:
            with self.subTest(changes=changes):
                form = PeriodForm({
                    **self.period_data(),
                    **changes,
                })

                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)

    def test_period_accepts_one_day_and_closed_status(self):
        form = PeriodForm({
            **self.period_data(),
            "end_date": "2026-01-01",
            "computable_days": 1,
            "status": "Closed",
        })

        self.assertTrue(form.is_valid(), form.errors)

    def test_period_view_hides_goals_without_permission(self):
        self.account("view_period")
        self.create_goal()

        response = self.client.get(
            reverse(
                "planning:period_edit",
                args=[self.period.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Meta confidencial")
        self.assertEqual(
            response.context["formset"].queryset.count(),
            0,
        )

    def test_period_view_exposes_authorized_goals(self):
        self.account("view_period", "view_goal")
        self.create_goal()

        response = self.client.get(
            reverse(
                "planning:period_edit",
                args=[self.period.pk],
            )
        )

        self.assertContains(response, "Meta confidencial")

    def test_read_only_user_cannot_post_edits(self):
        self.account("view_goal", "view_period")
        goal = self.create_goal()

        cases = [
            ("goal_edit", goal.pk, self.data),
            ("period_edit", self.period.pk, self.period_data()),
        ]

        for name, pk, data in cases:
            response = self.client.post(
                reverse("planning:" + name, args=[pk]),
                data,
            )

            self.assertEqual(response.status_code, 403)

        goal.refresh_from_db()
        self.assertEqual(goal.item, "Meta confidencial")

    def test_user_without_add_permission_cannot_create(self):
        self.account("view_goal", "view_period")

        response = self.client.post(
            reverse("planning:goal_create"),
            self.data,
        )
        self.assertEqual(response.status_code, 403)

        response = self.client.post(
            reverse("planning:period_create"),
            self.period_data(),
        )
        self.assertEqual(response.status_code, 403)

    def test_other_delegation_goal_returns_404(self):
        self.account("view_goal", "change_goal")
        goal = self.create_goal(employee=self.outside)

        url = reverse(
            "planning:goal_edit",
            args=[goal.pk],
        )

        self.assertEqual(
            self.client.get(url).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(url, self.data).status_code,
            404,
        )

    def test_delete_permission_does_not_bypass_superuser(self):
        self.account(
            "view_goal",
            "delete_goal",
            "view_period",
            "delete_period",
        )

        goal = self.create_goal()

        for name, pk in [
            ("goal_delete", goal.pk),
            ("period_delete", self.period.pk),
        ]:
            response = self.client.post(
                reverse("planning:" + name, args=[pk])
            )

            self.assertEqual(response.status_code, 403)

        goal.refresh_from_db()
        self.assertIsNone(goal.deleted_at)

    def test_archived_period_hides_and_blocks_goals(self):
        user = self.account(
            "view_goal",
            "change_goal",
            superuser=True,
        )

        goal = self.create_goal()
        self.period.deleted_at = timezone.now()
        self.period.save()

        self.assertFalse(
            scoped_goals(user).filter(pk=goal.pk).exists()
        )

        url = reverse(
            "planning:goal_edit",
            args=[goal.pk],
        )

        self.assertEqual(
            self.client.get(url).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(url, self.data).status_code,
            404,
        )

        form = GoalForm(self.data, user=user)

        self.assertFalse(form.is_valid())
        self.assertIn("period", form.errors)

    def test_superuser_archives_period_without_destroying_goals(self):
        user = self.account(superuser=True)
        goal = self.create_goal()

        response = self.client.post(
            reverse(
                "planning:period_delete",
                args=[self.period.pk],
            )
        )

        self.assertEqual(response.status_code, 302)

        self.period.refresh_from_db()
        self.assertIsNotNone(self.period.deleted_at)

        self.assertTrue(
            Goal.objects.filter(pk=goal.pk).exists()
        )

        self.assertFalse(
            scoped_goals(user).filter(pk=goal.pk).exists()
        )

    def test_period_creation_rolls_back_on_goal_save_failure(self):
        self.account(superuser=True)
        original_count = Period.objects.count()

        with patch.object(
            GoalInlineForm,
            "save",
            side_effect=RuntimeError("simulated failure"),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    reverse("planning:period_create"),
                    self.inline_data(),
                )

        self.assertEqual(
            Period.objects.count(),
            original_count,
        )
        self.assertEqual(Goal.objects.count(), 0)

    def test_period_change_without_goal_view_cannot_add_goal(self):
        self.account(
            "view_period",
            "change_period",
            "add_goal",
        )

        response = self.client.post(
            reverse(
                "planning:period_edit",
                args=[self.period.pk],
            ),
            self.inline_data(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Goal.objects.count(), 0)
        self.assertTrue(
            response.context["formset"].non_form_errors()
        )

    def test_model_rejects_goal_for_archived_period(self):
        goal = self.create_goal()

        self.period.deleted_at = timezone.now()
        self.period.save()

        goal.refresh_from_db()

        with self.assertRaises(ValidationError):
            goal.full_clean()
