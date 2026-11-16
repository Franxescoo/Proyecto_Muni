"""La foto cambiada en Mi perfil también se refleja en Organización / Empleados."""
import base64
import tempfile
from datetime import date
from pathlib import Path
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from accounts.models import UserProfile
from organization.models import Delegation, Employee, PositionFunction

# PNG 1x1 conocido: las imágenes reales se procesan con el mismo ImageField.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGP8z8DAwMDAxMDAwMDAAAANHQEDasKb6QAAAABJRU5ErkJggg=="
)


class ProfilePhotoEmployeeSyncTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.media = override_settings(MEDIA_ROOT=self.tmp.name)
        self.media.enable()
        self.addCleanup(self.media.disable)
        self.delegation = Delegation.objects.create(
            name="Centro", status="Active", scope="Urbano",
        )
        self.position = PositionFunction.objects.create(
            position_name="Atención", measurable_items="Atenciones",
            services="Atención", weightings="100%",
            validity_start=date(2026, 1, 1),
            validity_end=date(2027, 12, 31),
        )
        self.employee = Employee.objects.create(
            name="Empleado", delegation=self.delegation,
            position=self.position, roles="Atenciones", status="Active",
        )
        self.user = get_user_model().objects.create_user(
            username="foto_sync_test", password="test-only-password",
        )
        self.profile = UserProfile.objects.create(
            user=self.user, employee=self.employee,
            employee_code="FOTO-SYNC-1", delegation=self.delegation,
        )
        self.client.force_login(self.user)

    def test_upload_in_my_profile_updates_employee_photo(self):
        response = self.client.post(
            reverse("accounts:profile_photo_update"),
            {"profile_photo": SimpleUploadedFile(
                "perfil.png", PNG, content_type="image/png",
            )},
        )
        self.assertEqual(response.status_code, 302)
        self.profile.refresh_from_db()
        self.employee.refresh_from_db()
        self.assertTrue(self.profile.profile_photo.name)
        self.assertEqual(self.employee.profile_photo.name,
                         self.profile.profile_photo.name)
        self.assertTrue(Path(self.profile.profile_photo.path).exists())
