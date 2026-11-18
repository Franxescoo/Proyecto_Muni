"""Regresión: editar un período no debe invalidar metas históricas intactas."""
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from organization.models import Delegation, Employee, PositionFunction
from planning_measurements.models import Goal, MeasurementItem, Period


class GoalLegacyDuplicatesTest(TestCase):
    def setUp(self):
        self.delegation = Delegation.objects.create(
            name="Delegación duplicados históricos", status="Active", scope="Local",
        )
        self.position = PositionFunction.objects.create(
            position_name="Pruebas de metas históricas",
            measurable_items="Items", services="Servicios", weightings="Ponderadores",
            validity_start=date(2026, 1, 1), validity_end=date(2026, 12, 31),
        )
        self.employee = Employee.objects.create(
            name="Funcionario de prueba", delegation=self.delegation,
            position=self.position, roles="Funcionario", status="Active",
        )
        self.period = Period.objects.create(
            start_date=date(2026, 11, 1), end_date=date(2026, 11, 30),
            computable_days=20, status=Period.Status.ACTIVE,
            thresholds="Verde: 100, Amarillo: 80, Rojo: 60",
            parameters_version="v1",
        )
        self.item = MeasurementItem.objects.create(
            code="LEG-DUP-001", name="Ítem de regresión", unit="Unidades",
            item_type=MeasurementItem.ItemType.QUANTITATIVE,
            is_active=True,
        )
        self.position.catalog_items.add(self.item)

    def goal_values(self):
        return dict(
            period=self.period, employee=self.employee,
            position=self.position, measurement_item=self.item,
            item=self.item.name, unit=self.item.unit,
            objective_value=Decimal("10"), weight=Decimal("40"),
            required_evidence_count=5,
        )

    def test_duplicate_preexisting_goal_can_be_validated_unchanged(self):
        first = Goal.objects.create(**self.goal_values())
        second = Goal.objects.create(**self.goal_values())
        # Se validan tal como hace el formset cuando se edita solo el período.
        first.full_clean()
        second.full_clean()

    def test_new_duplicate_goal_still_rejected(self):
        Goal.objects.create(**self.goal_values())
        with self.assertRaises(ValidationError) as result:
            Goal(**self.goal_values()).full_clean()
        self.assertIn("Ya existe una meta", str(result.exception))

    def test_changed_existing_goal_to_duplicate_still_rejected(self):
        first = Goal.objects.create(**self.goal_values())
        second = Goal.objects.create(**self.goal_values())
        # Simular que existían dos metas diferentes y se intenta igualarlas.
        second.measurement_item = MeasurementItem.objects.create(
            code="LEG-DUP-002", name="Segundo ítem", unit="Unidades",
            item_type=MeasurementItem.ItemType.QUANTITATIVE,
            is_active=True,
        )
        self.position.catalog_items.add(second.measurement_item)
        second.item = second.measurement_item.name
        second.save(update_fields=["measurement_item", "item"])
        second.measurement_item = self.item
        second.item = self.item.name
        with self.assertRaises(ValidationError) as result:
            second.full_clean()
        self.assertIn("Ya existe una meta", str(result.exception))
