"""Pruebas del diseño y de los filtros unificados de los seis mantenedores."""
from io import BytesIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from accounts.models import UserProfile
from organization.models import Delegation, OrganizationRole
from planning_measurements.models import MeasurementItem
from registration_validation.models import AttentionType, SubAttention


class UnifiedCatalogTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser(
            username="catalog-admin", password="testing-secure-2026"
        )
        cls.north = Delegation.objects.create(
            name="Norte", code="N01", commune="La Serena", status="Active", scope="Urbano"
        )
        cls.south = Delegation.objects.create(
            name="Sur", code="S01", commune="Ovalle", status="Inactive", scope="Rural"
        )
        cls.group = Group.objects.create(name="Rol del Norte")
        cls.role = OrganizationRole.objects.create(
            group=cls.group, delegation=cls.north, description="Acceso Norte"
        )
        cls.role.application_delegations.add(cls.north)
        cls.alice = get_user_model().objects.create_user(
            username="alice", email="alice@example.com", password="testing-secure-2026"
        )
        cls.profile = UserProfile.objects.create(user=cls.alice, employee_code="EMP-ALICE", delegation=cls.north)
        cls.profile.authorized_delegations.add(cls.north)
        cls.alice.groups.add(cls.group)
        cls.attention_type = AttentionType.objects.create(
            code="AT-001", name="Atención General", status=True
        )
        cls.other_attention_type = AttentionType.objects.create(
            code="AT-002", name="Atención Secundaria", status=False
        )
        cls.subattention = SubAttention.objects.create(
            code="SA-01", name="Consulta", attention_type=cls.attention_type, status=True
        )
        cls.item = MeasurementItem.objects.create(
            code="IT-01", name="Ítem Indicador", description="Medición", item_type="quantitative", is_active=True
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def test_all_six_catalogs_have_same_buttons_and_page_size(self):
        for name in (
            "organization:delegation_list", "organization:role_list", "organization:user_list",
            "planning:item_list", "registration:attention_type_list", "registration:sub_attention_list"
        ):
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Guardar preferencia")
                self.assertContains(response, "Filtrar")
                self.assertContains(response, "Limpiar")
                self.assertContains(response, "1 / 1")
                self.assertContains(response, "Exportar Excel")

    def test_delegation_filters_by_commune_and_status(self):
        response = self.client.get(reverse("organization:delegation_list"), {
            "commune": "La Serena", "status": "Active"
        })
        self.assertEqual(list(response.context["delegations"].object_list), [self.north])

    def test_role_filter_uses_multiple_delegations(self):
        url = reverse("organization:role_list")
        response = self.client.get(url, {"delegation": str(self.north.pk)})
        self.assertIn(self.group, response.context["roles"].object_list)
        response = self.client.get(url, {"delegation": str(self.south.pk)})
        self.assertNotIn(self.group, response.context["roles"].object_list)

    def test_user_filters_delegation_role_and_status(self):
        response = self.client.get(reverse("organization:user_list"), {
            "delegation": str(self.north.pk), "role": str(self.group.pk), "status": "active"
        })
        self.assertEqual(list(response.context["users"].object_list), [self.alice])

    def test_org_page_size_saved_and_filters_kept(self):
        url = reverse("organization:role_list")
        next_url = url + "?q=Norte&delegation=" + str(self.north.pk)
        response = self.client.post(reverse("organization:set_page_size"), {
            "page_size": "10", "next": next_url
        })
        self.assertRedirects(response, next_url)
        self.assertEqual(self.client.get(next_url).context["roles"].paginator.per_page, 10)
        response = self.client.post(reverse("organization:set_page_size"), {
            "page_size": "999", "next": next_url
        })
        self.assertRedirects(response, next_url)
        self.assertEqual(self.client.get(next_url).context["roles"].paginator.per_page, 10)

    def test_page_links_preserve_filtered_commune(self):
        Delegation.objects.bulk_create([
            Delegation(name=f"Norte {i}", status="Active", scope="Urbano", commune="La Serena")
            for i in range(26)
        ])
        self.client.post(reverse("organization:set_page_size"), {
            "page_size": "10", "next": reverse("organization:delegation_list")
        })
        response = self.client.get(reverse("organization:delegation_list"), {"commune": "La Serena"})
        self.assertEqual(response.context["delegations"].paginator.per_page, 10)
        self.assertTrue(response.context["delegations"].has_next())
        self.assertContains(response, "commune=La+Serena")
        self.assertContains(response, "page=2")

    def test_subattention_type_filter(self):
        response = self.client.get(reverse("registration:sub_attention_list"), {
            "attention_type": str(self.other_attention_type.pk)
        })
        self.assertEqual(list(response.context["page_obj"].object_list), [])
        response = self.client.get(reverse("registration:sub_attention_list"), {
            "attention_type": str(self.attention_type.pk)
        })
        self.assertEqual(list(response.context["page_obj"].object_list), [self.subattention])

    def test_excel_exports_have_correct_filtered_rows(self):
        samples = (
            ("organization:delegation_export", {"commune": "La Serena"}, "N01", "S01"),
            ("organization:role_export", {"delegation": str(self.north.pk)}, "Rol del Norte", "NO-SUCH-ROLE"),
            ("organization:user_export", {"role": str(self.group.pk)}, "alice", "NO-SUCH-USER"),
            ("planning:item_export", {"status": "active"}, "IT-01", "NO-SUCH-ITEM"),
            ("registration:attention_type_export", {"status": "active"}, "AT-001", "AT-002"),
            ("registration:sub_attention_export", {"attention_type": str(self.attention_type.pk)}, "SA-01", "NO-SUCH-SUB"),
        )
        for name, filters, included, excluded in samples:
            with self.subTest(name=name):
                response = self.client.get(reverse(name), filters)
                self.assertEqual(response.status_code, 200)
                workbook = load_workbook(BytesIO(response.content), read_only=True)
                contents = "\n".join(str(cell) for row in workbook.active.values for cell in row)
                self.assertIn(included, contents)
                self.assertNotIn(excluded, contents)

    def test_direct_unauthorized_export_is_denied(self):
        self.client.force_login(self.alice)
        for name in (
            "organization:role_export", "organization:user_export",
            "planning:item_export", "registration:sub_attention_export"
        ):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)
