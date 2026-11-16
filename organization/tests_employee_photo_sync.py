"""Fotos de Empleados y Usuarios integradas en la misma ficha."""
from datetime import date
from types import SimpleNamespace
from django.contrib.auth import get_user_model
from django.test import TestCase
from organization.models import Delegation, Employee, PositionFunction
from accounts.models import UserProfile
from organization.views import _sync_employee_account


class EmployeePhotoIntegrationTests(TestCase):
    def setUp(self):
        self.delegation = Delegation.objects.create(
            name="Delegación fotográfica", scope="Urbano", status="Active"
        )
        self.position = PositionFunction.objects.create(
            position_name="Atención fotográfica", measurable_items="Atenciones",
            services="Atención", weightings="100%",
            validity_start=date(2026, 1, 1), validity_end=date(2027, 12, 31),
        )
        self.employee = Employee.objects.create(
            name="Empleado de prueba", delegation=self.delegation,
            position=self.position, roles="Atención", status="Active",
        )

    def sync(self):
        form = SimpleNamespace(cleaned_data={
            "username": "empleado_foto", "email": "empleado@example.test",
            "password1": "", "employee_code": "FOTO-001",
            "authorized_delegations": [self.delegation],
        })
        _sync_employee_account(self.employee, form)
        return UserProfile.objects.get(employee=self.employee)

    def test_new_employee_photo_is_shared_with_its_account(self):
        self.employee.profile_photo = "profile_photos/employee.jpg"
        self.employee.save(update_fields=["profile_photo", "updated_at"])
        profile = self.sync()
        self.assertEqual(profile.profile_photo.name, "profile_photos/employee.jpg")

    def test_legacy_account_photo_is_reused_in_employee(self):
        user = get_user_model().objects.create_user(username="empleado_foto")
        profile = UserProfile.objects.create(
            user=user, employee=self.employee, employee_code="FOTO-001",
            delegation=self.delegation, profile_photo="profile_photos/legacy.jpg",
        )
        profile.authorized_delegations.add(self.delegation)
        self.sync()
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.profile_photo.name, "profile_photos/legacy.jpg")

    def test_new_employee_photo_replaces_old_account_photo(self):
        user = get_user_model().objects.create_user(username="empleado_foto")
        profile = UserProfile.objects.create(
            user=user, employee=self.employee, employee_code="FOTO-001",
            delegation=self.delegation, profile_photo="profile_photos/old.jpg",
        )
        profile.authorized_delegations.add(self.delegation)
        self.employee.profile_photo = "profile_photos/new.jpg"
        self.employee.save(update_fields=["profile_photo", "updated_at"])
        profile = self.sync()
        self.assertEqual(profile.profile_photo.name, "profile_photos/new.jpg")
