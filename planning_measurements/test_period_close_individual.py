"""Pruebas de integridad de ponderadores al cerrar períodos.

No se necesita una migración: la comprobación usa Goal existentes.
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from organization.models import Delegation, Employee, PositionFunction
from .calculations import InvalidPeriodWeights, validate_period_weights
from .models import Goal, Period


class PeriodCloseIndividualWeightTests(TestCase):
    def setUp(self):
        self.delegation = Delegation.objects.create(
            name="Delegación Norte", status="Active", scope="Local",
        )
        self.position = self.make_position("Administrativo")
        self.juan = self.make_employee("Juan", self.position)
        self.maria = self.make_employee("María", self.position)
        self.period = Period.objects.create(
            start_date=date(2026, 11, 2),
            end_date=date(2026, 11, 30),
            computable_days=20,
            status=Period.Status.ACTIVE,
            thresholds="Verde: 100, Amarillo: 80, Rojo: 60",
            parameters_version="1",
        )

    def make_position(self, name):
        return PositionFunction.objects.create(
            position_name=name,
            measurable_items="Items",
            services="Services",
            weightings="Weights",
            validity_start=date(2026, 1, 1),
            validity_end=date(2026, 12, 31),
        )

    def make_employee(self, name, position):
        return Employee.objects.create(
            name=name,
            delegation=self.delegation,
            position=position,
            roles="Funcionario",
            status="Active",
        )

    def goal(self, employee, item, weight):
        return Goal.objects.create(
            period=self.period,
            employee=employee,
            position=employee.position,
            item=item,
            objective_value=Decimal("10"),
            unit="unidades",
            weight=Decimal(str(weight)),
        )

    def test_two_complete_employees_same_position_can_close(self):
        for employee in (self.juan, self.maria):
            self.goal(employee, "Atenciones", 40)
            self.goal(employee, "Informes", 60)
        self.assertIsNone(validate_period_weights(self.period))

    def test_one_employee_missing_an_item_blocks_closure(self):
        self.goal(self.juan, "Atenciones", 40)
        self.goal(self.juan, "Informes", 60)
        self.goal(self.maria, "Atenciones", 40)
        with self.assertRaises(InvalidPeriodWeights) as error:
            validate_period_weights(self.period)
        self.assertIn("María", str(error.exception))
        self.assertIn("Informes", str(error.exception))
        self.assertIn("Administrativo", str(error.exception))

    def test_one_employee_can_have_multiple_goals_totalling_100(self):
        self.goal(self.juan, "Atenciones", 40)
        self.goal(self.juan, "Informes", 60)
        self.assertIsNone(validate_period_weights(self.period))

    def test_person_without_any_goal_does_not_block_closure(self):
        # No se presume que todos los empleados de la organización
        # participen en todos los períodos.
        self.goal(self.juan, "Atenciones", 100)
        self.assertIsNone(validate_period_weights(self.period))

    def test_goal_deleted_logically_does_not_complete_employee(self):
        self.goal(self.juan, "Atenciones", 40)
        self.goal(self.juan, "Informes", 60)
        self.goal(self.maria, "Atenciones", 40)
        removed = self.goal(self.maria, "Informes", 60)
        removed.deleted_at = timezone.now()
        removed.save(update_fields=["deleted_at"])
        with self.assertRaisesRegex(InvalidPeriodWeights, "María"):
            validate_period_weights(self.period)

    def test_different_positions_may_have_different_goal_sets(self):
        other_position = self.make_position("Social")
        employee = self.make_employee("Pedro", other_position)
        self.goal(self.juan, "Atenciones", 100)
        self.goal(employee, "Visitas", 70)
        self.goal(employee, "Gestiones", 30)
        self.assertIsNone(validate_period_weights(self.period))

    def test_same_item_different_weights_is_rejected(self):
        self.goal(self.juan, "Atenciones", 100)
        self.goal(self.maria, "Atenciones", 90)
        with self.assertRaisesRegex(InvalidPeriodWeights, "ponderadores diferentes"):
            validate_period_weights(self.period)

    def test_empty_period_cannot_close(self):
        with self.assertRaisesRegex(InvalidPeriodWeights, "sin metas"):
            validate_period_weights(self.period)

    def test_same_employee_duplicate_text_item_is_rejected(self):
        self.goal(self.juan, "Atenciones", 100)
        self.goal(self.juan, " ATENCIONES ", 100)
        with self.assertRaisesRegex(InvalidPeriodWeights, "duplicado"):
            validate_period_weights(self.period)

    def test_missing_item_with_zero_weight_still_blocks_closure(self):
        self.goal(self.juan, "Atenciones", 100)
        self.goal(self.juan, "Control", 0)
        self.goal(self.maria, "Atenciones", 100)
        with self.assertRaisesRegex(InvalidPeriodWeights, "Control"):
            validate_period_weights(self.period)
