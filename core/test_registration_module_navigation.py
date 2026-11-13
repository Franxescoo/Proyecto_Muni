from django.test import SimpleTestCase
from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse

from .modules import MODULES


class RegistrationModuleNavigationTests(SimpleTestCase):
    def test_registration_section_has_one_citizens_access(self):
        registration = next(
            module
            for module in MODULES
            if module["title"] == "Registro y validación"
        )
        citizens = [
            card
            for card in registration["cards"]
            if card["title"] == "Ciudadanos"
        ]

        self.assertEqual(len(citizens), 1)
        self.assertEqual(citizens[0]["url"], "citizen_registry:list")
        self.assertEqual(citizens[0]["perm"], "citizen_registry.view_citizen")


class RegistrationCitizenEntryTests(TestCase):
    def test_home_card_activates_only_registration_tutorial_context(self):
        user = User.objects.create_user(username="inicio", password="demo12345")
        permission = Permission.objects.get(
            content_type__app_label="citizen_registry",
            codename="view_citizen",
        )
        user.user_permissions.add(permission)
        self.client.force_login(user)

        response = self.client.get(reverse("home"))
        citizens_url = reverse("citizen_registry:list")

        self.assertContains(
            response,
            f'href="{citizens_url}?sgr_context=registration_validation"',
        )
        self.assertContains(response, f'href="{citizens_url}"')
