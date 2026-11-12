"""Pruebas nuevas de catálogo, tope, historial y cierre sin efectos colaterales."""
from datetime import date
from django.utils import timezone
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserProfile
from organization.models import Delegation, Employee, PositionFunction
from .calculations import InvalidPeriodWeights, validate_period_weights
from .forms import PeriodForm, MeasurementItemForm
from .measurement_rules import SUPPORTED_PERCENTAGE_FORMULA
from .models import Goal, MeasurementItem, Period, PeriodParameterSnapshot
from .parameter_history import (
    advance_period_parameters_version,
    capture_period_parameters,
    next_parameters_version,
)


class PlanIntegrityTests(TestCase):
    def setUp(self):
        self.delegation = Delegation.objects.create(
            name="Delegación pruebas", scope="Local", status="Active",
        )
        self.position = PositionFunction.objects.create(
            position_name="Administrativo", measurable_items="Items",
            services="Servicios", weightings="Ponderadores",
            validity_start=date(2026, 1, 1), validity_end=date(2026, 12, 31),
        )
        self.juan = Employee.objects.create(
            name="Juan", delegation=self.delegation, position=self.position,
            status="Active", roles="Funcionario",
        )
        self.maria = Employee.objects.create(
            name="María", delegation=self.delegation, position=self.position,
            status="Active", roles="Funcionario",
        )
        self.period = Period.objects.create(
            start_date=date(2026, 11, 2), end_date=date(2026, 11, 30),
            status=Period.Status.ACTIVE, computable_days=20,
            thresholds="Verde: 100, Amarillo: 80, Rojo: 60",
            parameters_version="v1",
        )
        self.user = get_user_model().objects.create_user(
            username="historial-funcional", password="PruebaSegura123!",
        )
        UserProfile.objects.create(
            user=self.user,
            employee_code="HIST-001",
            delegation=self.delegation,
        )

    def item(self, code, name, active=True, percentage=False, formula=""):
        obj = MeasurementItem.objects.create(
            code=code, name=name, unit="Unidades", is_active=active,
            item_type=(MeasurementItem.ItemType.PERCENTAGE if percentage
                       else MeasurementItem.ItemType.QUANTITATIVE),
            formula=formula,
        )
        self.position.catalog_items.add(obj)
        return obj

    def test_parameter_version_increments_only_supported_numeric_suffix(self):
        self.assertEqual(next_parameters_version("SGR050-v1"), "SGR050-v2")
        self.assertEqual(next_parameters_version("v1"), "v2")
        self.assertEqual(next_parameters_version("1"), "2")
        self.assertEqual(next_parameters_version("initial"), "initial")

    def test_parameter_version_update_is_persisted_in_transaction(self):
        with transaction.atomic():
            locked = advance_period_parameters_version(self.period)
            capture_period_parameters(
                self.period,
                actor=self.user,
                event=PeriodParameterSnapshot.Event.CONFIGURED,
            )

        self.period.refresh_from_db()
        self.assertEqual(self.period.parameters_version, "v2")
        self.assertEqual(
            self.period.parameter_snapshots.get().content["parameters_version"],
            "v2",
        )

    def goal(self, employee, item, weight, *, name=None):
        return Goal.objects.create(
            period=self.period, employee=employee, position=self.position,
            measurement_item=item, item=name or item.name,
            unit=item.unit, objective_value=Decimal("10"),
            weight=Decimal(str(weight)),
        )

    def _new_period(self, start, end, *, status=Period.Status.ACTIVE):
        return Period(
            start_date=start, end_date=end, computable_days=5,
            status=status,
            thresholds="Verde: 100, Amarillo: 80, Rojo: 60",
            parameters_version="v1",
        )

    def test_period_model_rejects_overlapping_range(self):
        candidate = self._new_period(date(2026, 11, 30), date(2026, 12, 4))
        with self.assertRaises(ValidationError) as caught:
            candidate.full_clean()
        self.assertIn("start_date", caught.exception.message_dict)

    def test_period_form_rejects_overlap_even_with_closed_period(self):
        self.period.status = Period.Status.CLOSED
        self.period.save(update_fields=["status"])
        form = PeriodForm(data={
            "start_date": "2026-11-15", "end_date": "2026-12-04",
            "computable_days": "", "status": Period.Status.ACTIVE,
            "thresholds": "Verde: 100, Amarillo: 80, Rojo: 60",
            "parameters_version": "v1", "compliance_cap": "150",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("start_date", form.errors)

    def test_period_model_accepts_adjacent_dates(self):
        candidate = self._new_period(date(2026, 12, 1), date(2026, 12, 7))
        candidate.full_clean()

    def test_period_model_ignores_archived_periods(self):
        self.period.deleted_at = timezone.now()
        self.period.save(update_fields=["deleted_at"])
        candidate = self._new_period(date(2026, 11, 2), date(2026, 11, 30))
        candidate.full_clean()

    def test_period_model_ignores_own_dates_when_editing(self):
        self.period.full_clean()
        self.period.parameters_version = "v2"
        self.period.full_clean()

    def test_archiving_item_captures_history_without_deleting_goals(self):
        item = self.item("HIST01", "Atenciones")
        goal = self.goal(self.juan, item, 100)
        with transaction.atomic():
            first = capture_period_parameters(
                self.period, actor=self.user,
                event=PeriodParameterSnapshot.Event.CONFIGURED,
            )
        self.user.user_permissions.add(Permission.objects.get(
            content_type__app_label="planning_measurements",
            codename="delete_measurementitem",
        ))
        self.client.force_login(self.user)
        response = self.client.post(reverse("planning:item_delete", args=[item.pk]))
        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertFalse(item.is_active)
        self.assertIsNotNone(item.deleted_at)
        self.assertTrue(Goal.objects.filter(pk=goal.pk, deleted_at__isnull=True).exists())
        snapshots = list(self.period.parameter_snapshots.order_by("revision"))
        self.assertEqual(len(snapshots), 2)
        self.assertEqual(snapshots[0].pk, first.pk)
        self.assertEqual(snapshots[1].revision, 2)
        self.assertEqual(snapshots[1].event, PeriodParameterSnapshot.Event.CATALOG_UPDATED)
        self.assertEqual(snapshots[1].actor, self.user)
        self.assertEqual(len(snapshots[0].content["positions"][0]["catalog"]), 1)
        self.assertEqual(len(snapshots[1].content["positions"][0]["catalog"]), 0)
        self.assertEqual(snapshots[1].content["goals"][0]["goal_id"], goal.pk)

    def test_archiving_item_does_not_change_closed_period_history(self):
        item = self.item("HIST02", "Atenciones")
        self.goal(self.juan, item, 100)
        self.period.status = Period.Status.CLOSED
        self.period.save(update_fields=["status"])
        with transaction.atomic():
            first = capture_period_parameters(
                self.period, actor=self.user,
                event=PeriodParameterSnapshot.Event.CLOSED,
            )
        self.user.user_permissions.add(Permission.objects.get(
            content_type__app_label="planning_measurements",
            codename="delete_measurementitem",
        ))
        self.client.force_login(self.user)
        response = self.client.post(reverse("planning:item_delete", args=[item.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.period.parameter_snapshots.count(), 1)
        first.refresh_from_db()
        self.assertEqual(first.content["positions"][0]["catalog"][0]["code"], "HIST02")

    def test_new_catalog_item_does_not_require_an_additional_goal(self):
        # El período ya tiene sus metas y ponderaciones completos.
        a = self.item("C001", "Atenciones")
        b = self.item("C002", "Informes")
        self.goal(self.juan, a, 60)
        self.goal(self.juan, b, 40)

        # Un ítem agregado posteriormente al cargo no crea una nueva meta.
        nuevo = self.item("C018", "Visitas a terreno")
        self.assertFalse(Goal.objects.filter(
            period=self.period, measurement_item=nuevo,
        ).exists())
        self.assertIsNone(validate_period_weights(self.period))

    def test_new_catalog_item_does_not_affect_complete_employees(self):
        a = self.item("C019", "Atenciones")
        b = self.item("C020", "Informes")
        for employee in (self.juan, self.maria):
            self.goal(employee, a, 60)
            self.goal(employee, b, 40)
        self.item("C021", "Ítem posterior")
        self.assertIsNone(validate_period_weights(self.period))

    def test_goal_with_item_outside_its_position_catalog_is_rejected(self):
        a = self.item("C022", "Atenciones")
        ajeno = MeasurementItem.objects.create(
            code="C023", name="Ítem ajeno", unit="Unidades", is_active=True,
        )
        self.goal(self.juan, a, 60)
        self.goal(self.juan, ajeno, 40)
        with self.assertRaisesRegex(InvalidPeriodWeights, "no pertenecen"):
            validate_period_weights(self.period)

    def test_all_catalog_items_counted_by_id(self):
        a = self.item("C003", "Servicio")
        b = self.item("C004", "Servicio")  # nombre idéntico, ID distinto
        self.goal(self.juan, a, 40)
        self.goal(self.juan, b, 60)
        self.assertIsNone(validate_period_weights(self.period))

    def test_each_participating_employee_must_have_catalog_items(self):
        a = self.item("C005", "Atenciones")
        b = self.item("C006", "Informes")
        self.goal(self.juan, a, 40)
        self.goal(self.juan, b, 60)
        self.goal(self.maria, a, 40)
        with self.assertRaisesRegex(InvalidPeriodWeights, "María"):
            validate_period_weights(self.period)

    def test_inactive_item_not_required_for_new_closure(self):
        active = self.item("C007", "Vigente")
        self.item("C008", "Inactivo", active=False)
        self.goal(self.juan, active, 100)
        self.assertIsNone(validate_period_weights(self.period))

    def test_old_text_only_goals_remain_compatible(self):
        Goal.objects.create(
            period=self.period, employee=self.juan, position=self.position,
            item="Antiguo", objective_value=5, unit="u", weight=100,
        )
        self.assertIsNone(validate_period_weights(self.period))

    def test_incompatible_percentage_formula_blocked_at_close(self):
        item = self.item("C009", "Porcentaje", percentage=True, formula="(A / B) * 100")
        self.goal(self.juan, item, 100)
        with self.assertRaisesRegex(InvalidPeriodWeights, "fórmula"):
            validate_period_weights(self.period)

    def test_valid_percentage_formula_allowed_at_close(self):
        item = self.item("C010", "Porcentaje", percentage=True,
                         formula=SUPPORTED_PERCENTAGE_FORMULA)
        self.goal(self.juan, item, 100)
        self.assertIsNone(validate_period_weights(self.period))

    def test_percentage_form_rejects_unsupported_formula(self):
        form = MeasurementItemForm({
            "code": "C011", "name": "Otro porcentaje", "item_type": "percentage",
            "unit": "%", "formula": "(Casos / Población) * 100",
            "description": "", "is_active": "on",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("formula", form.errors)

    def test_percentage_form_accepts_canonical_formula(self):
        form = MeasurementItemForm({
            "code": "C012", "name": "Porcentaje válido", "item_type": "percentage",
            "unit": "%", "formula": SUPPORTED_PERCENTAGE_FORMULA,
            "description": "", "is_active": "on",
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_cap_is_explicit_without_changing_monitoring_code(self):
        data = {
            "start_date": "2026-11-02", "end_date": "2026-11-30",
            "status": "Active", "computable_days": "",
            "thresholds": "Verde: 100, Amarillo: 80, Rojo: 60",
            "parameters_version": "v2", "compliance_cap": "180",
        }
        form = PeriodForm(data=data, instance=self.period)
        self.assertTrue(form.is_valid(), form.errors)
        updated = form.save()
        self.assertIn("Tope: 180.00", updated.thresholds)

    def test_period_form_rejects_invalid_parameter_version(self):
        data = {
            "start_date": "2026-11-02", "end_date": "2026-11-30",
            "status": "Active", "computable_days": "",
            "thresholds": "Verde: 100, Amarillo: 80, Rojo: 60",
            "parameters_version": "v1.0.lalala", "compliance_cap": "150",
        }
        form = PeriodForm(data=data, instance=Period())
        self.assertFalse(form.is_valid())
        self.assertIn("parameters_version", form.errors)

    def test_period_form_accepts_multicomponent_parameter_version(self):
        data = {
            "start_date": "2026-11-02", "end_date": "2026-11-30",
            "status": "Active", "computable_days": "",
            "thresholds": "Verde: 100, Amarillo: 80, Rojo: 60",
            "parameters_version": "SGR044-v1.3", "compliance_cap": "150",
        }
        form = PeriodForm(data=data, instance=self.period)
        self.assertTrue(form.is_valid(), form.errors)

    def test_existing_period_version_is_read_only(self):
        form = PeriodForm(instance=self.period)
        self.assertTrue(form.fields["parameters_version"].disabled)
        self.assertEqual(
            form.initial["parameters_version"],
            self.period.parameters_version,
        )

    def test_post_cannot_change_existing_period_version(self):
        self.user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="planning_measurements",
            codename__in=("view_period", "change_period"),
        ))
        self.client.force_login(self.user)
        self.period.thresholds = (
            "Verde: 100, Amarillo: 80, Rojo: 60, Tope: 150.00"
        )
        self.period.computable_days = 21
        self.period.save(update_fields=["thresholds", "computable_days"])
        data = self._period_post_data(Period.Status.ACTIVE)
        data["thresholds"] = self.period.thresholds
        data["parameters_version"] = "v999"

        response = self.client.post(
            reverse("planning:period_edit", args=[self.period.pk]),
            data=data,
        )

        self.assertEqual(response.status_code, 302)
        self.period.refresh_from_db()
        self.assertEqual(self.period.parameters_version, "v1")

    def test_snapshot_is_append_only_and_preserves_previous_values(self):
        a = self.item("C013", "Atenciones")
        self.goal(self.juan, a, 100)
        with transaction.atomic():
            first = capture_period_parameters(
                self.period, actor=self.user,
                event=PeriodParameterSnapshot.Event.CONFIGURED,
            )
        self.assertEqual(first.revision, 1)
        self.assertEqual(Decimal(first.content["goals"][0]["weight"]), Decimal("100"))
        self.period.thresholds = "Verde: 90, Amarillo: 80, Rojo: 60, Tope: 180"
        self.period.save(update_fields=["thresholds"])
        with transaction.atomic():
            second = capture_period_parameters(
                self.period, actor=self.user,
                event=PeriodParameterSnapshot.Event.CONFIGURED,
            )
        self.assertEqual(second.revision, 2)
        first.refresh_from_db()
        self.assertEqual(first.content["compliance_cap"], "150")
        self.assertEqual(second.content["compliance_cap"], "180")
        with self.assertRaises(ValidationError):
            first.save()
        with self.assertRaises(ValidationError):
            first.delete()

    def test_history_view_requires_permission(self):
        self.client.force_login(self.user)
        url = reverse("planning:period_parameter_history", args=[self.period.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.user.user_permissions.add(Permission.objects.get(
            content_type__app_label="planning_measurements", codename="view_period",
        ))
        self.assertEqual(self.client.get(url).status_code, 200)

    def _period_post_data(self, status):
        return {
            "start_date": "2026-11-02", "end_date": "2026-11-30",
            "computable_days": "", "status": status,
            "thresholds": "Verde: 100, Amarillo: 80, Rojo: 60",
            "parameters_version": "v1", "compliance_cap": "150",
            "goals-TOTAL_FORMS": "0", "goals-INITIAL_FORMS": "0",
            "goals-MIN_NUM_FORMS": "0", "goals-MAX_NUM_FORMS": "1000",
        }

    def test_close_creates_snapshot_transactionally(self):
        a = self.item("C014", "Atenciones")
        self.goal(self.juan, a, 100)
        # Aunque ahora el cargo tenga otro ítem, no se exige una meta nueva.
        self.item("C024", "Ítem agregado después de configurar las metas")
        # La vista de edición requiere ambos permisos: consultar y modificar.
        self.user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="planning_measurements",
            codename__in=("view_period", "change_period"),
        ))
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("planning:period_edit", args=[self.period.pk]),
            data=self._period_post_data(Period.Status.CLOSED),
        )
        self.assertEqual(response.status_code, 302)
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, Period.Status.CLOSED)
        snap = self.period.parameter_snapshots.get()
        self.assertEqual(snap.event, "CLOSED")
        self.assertEqual(snap.content["goals"][0]["item"], "Atenciones")

    def test_changing_compliance_cap_increments_version_and_history(self):
        self.user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="planning_measurements",
            codename__in=("view_period", "change_period"),
        ))
        self.client.force_login(self.user)
        data = self._period_post_data(Period.Status.ACTIVE)
        data["compliance_cap"] = "130"

        response = self.client.post(
            reverse("planning:period_edit", args=[self.period.pk]),
            data=data,
        )

        self.assertEqual(response.status_code, 302)
        self.period.refresh_from_db()
        self.assertEqual(self.period.parameters_version, "v2")
        self.assertIn("Tope: 130.00", self.period.thresholds)
        snapshot = self.period.parameter_snapshots.get()
        self.assertEqual(snapshot.content["compliance_cap"], "130.00")

        response = self.client.post(
            reverse("planning:period_edit", args=[self.period.pk]),
            data=data,
        )

        self.assertEqual(response.status_code, 302)
        self.period.refresh_from_db()
        self.assertEqual(self.period.parameters_version, "v2")
        self.assertEqual(self.period.parameter_snapshots.count(), 1)

    def test_edit_rejects_goal_with_unauthorized_measurement_item(self):
        source_period = self._new_period(
            date(2026, 10, 1),
            date(2026, 10, 31),
        )
        source_period.save()
        item = self.item("C099", "Ítem no autorizado")
        source_goal = self.goal(self.juan, item, 100)
        source_goal.period = source_period
        source_goal.save(update_fields=["period"])
        self.position.catalog_items.remove(item)

        self.user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="planning_measurements",
            codename__in=(
                "view_period", "change_period", "view_goal", "add_goal",
            ),
        ))
        self.client.force_login(self.user)
        data = self._period_post_data(Period.Status.ACTIVE)
        data["existing_goal_ids"] = [str(source_goal.pk)]

        response = self.client.post(
            reverse("planning:period_edit", args=[self.period.pk]),
            data=data,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].non_field_errors())
        self.assertEqual(
            " ".join(
                str(error)
                for error in response.context["form"].non_field_errors()
            ),
            "No se puede copiar la meta porque el ítem de medición "
            "no está autorizado para el cargo.",
        )
        self.assertFalse(
            Goal.objects.filter(
                period=self.period,
                employee=self.juan,
                measurement_item=item,
            ).exists()
        )
        self.period.refresh_from_db()
        self.assertEqual(self.period.parameters_version, "v1")

    def test_failed_close_keeps_status_and_creates_no_snapshot(self):
        a = self.item("C015", "Atenciones")
        self.goal(self.juan, a, 50)
        # La vista de edición requiere ambos permisos: consultar y modificar.
        self.user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="planning_measurements",
            codename__in=("view_period", "change_period"),
        ))
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("planning:period_edit", args=[self.period.pk]),
            data=self._period_post_data(Period.Status.CLOSED),
        )
        self.assertEqual(response.status_code, 200)
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, Period.Status.ACTIVE)
        self.assertFalse(self.period.parameter_snapshots.exists())

    def test_history_does_not_expose_goals_without_view_goal(self):
        a = self.item("C016", "Atenciones secretas")
        self.goal(self.juan, a, 100)
        with transaction.atomic():
            capture_period_parameters(
                self.period, actor=self.user,
                event=PeriodParameterSnapshot.Event.CONFIGURED,
            )
        self.user.user_permissions.add(Permission.objects.get(
            content_type__app_label="planning_measurements", codename="view_period",
        ))
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("planning:period_parameter_history", args=[self.period.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Atenciones secretas")

    def test_cannot_modify_formula_used_in_closed_period(self):
        item = self.item("C017", "Ítem histórico")
        self.goal(self.juan, item, 100)
        self.period.status = Period.Status.CLOSED
        self.period.save(update_fields=["status"])
        self.user.user_permissions.add(Permission.objects.get(
            content_type__app_label="planning_measurements",
            codename="change_measurementitem",
        ))
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("planning:item_edit", args=[item.pk]),
            {
                "code": item.code, "name": "Nombre nuevo",
                "item_type": item.item_type, "unit": item.unit,
                "formula": item.formula, "description": "", "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.name, "Ítem histórico")
