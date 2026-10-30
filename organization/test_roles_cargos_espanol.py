"""Pruebas de presentación española, catálogo global y permisos sin superusuario."""
from datetime import date
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse
from accounts.models import UserProfile
from organization.forms import OrganizationRoleForm
from organization.models import Delegation, OrganizationRole, PositionFunction
from organization.permission_labels import permission_label


class PruebasRolesYCatalogoSinSuperusuario(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.delegation = Delegation.objects.create(
            name="Delegación de prueba", code="PR-100", status="Active", scope="Urbano"
        )
        cls.foreign_delegation = Delegation.objects.create(
            name="Delegación ajena", code="PR-200", status="Active", scope="Rural"
        )
        cls.position = PositionFunction.objects.create(
            position_name="Cargo sin empleados", services="Atención", measurable_items="Registro",
            weightings="100%", validity_start=date(2026, 1, 1), validity_end=date(2026, 12, 31)
        )
        cls.actor = get_user_model().objects.create_user(username="lector", password="Prueba-123!!")
        cls.profile = UserProfile.objects.create(
            user=cls.actor, employee_code="PR-LC-01", delegation=cls.delegation
        )
        cls.profile.authorized_delegations.add(cls.delegation)
        cls.group = Group.objects.create(name="Consulta de prueba")
        cls.role = OrganizationRole.objects.create(group=cls.group, delegation=cls.delegation)
        cls.role.application_delegations.add(cls.delegation)
        cls.actor.groups.add(cls.group)

    def grant(self, *codenames):
        self.group.permissions.set(Permission.objects.filter(codename__in=codenames))
        self.actor = get_user_model().objects.get(pk=self.actor.pk)

    def test_cargos_globales_con_permiso_y_sin_empleados(self):
        self.grant("view_positionfunction")
        self.client.force_login(self.actor)
        r = self.client.get(reverse("organization:position_list"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Cargo sin empleados")
        self.assertNotContains(r, "Nuevo cargo")
        self.assertEqual(r.context["total_positions"], 1)

    def test_no_crear_cargo_solo_con_lectura(self):
        self.grant("view_positionfunction")
        self.client.force_login(self.actor)
        r = self.client.get(reverse("organization:position_list"), {"modal": "create"})
        self.assertEqual(r.status_code, 403)

    def test_rol_visible_para_cuenta_normal_con_permiso(self):
        self.grant("view_organizationrole", "view_positionfunction")
        self.client.force_login(self.actor)
        r = self.client.get(reverse("organization:role_list"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Consulta de prueba")
        self.assertNotContains(r, "Crear rol")
        self.assertNotContains(r, "Editar permisos")
        self.assertNotContains(r, "Eliminar</button>")
        r2 = self.client.get(reverse("organization:role_list"), {"modal": "view", "id": self.group.pk})
        self.assertEqual(r2.status_code, 200)
        self.assertContains(r2, "Organización | Cargos y funciones | Puede consultar cargos y funciones")

    def test_rol_creacion_exige_permiso_explicito(self):
        self.grant("view_organizationrole")
        self.client.force_login(self.actor)
        r = self.client.post(reverse("organization:role_list"), {
            "action": "create", "name": "Rol inválido", "description": "Ejemplo",
            "delegations": [self.delegation.pk], "permissions": [],
        })
        self.assertEqual(r.status_code, 403)
        self.assertFalse(Group.objects.filter(name="Rol inválido").exists())

    def test_admin_normal_puede_crear_rol_con_permisos_propios(self):
        self.grant("view_organizationrole", "add_organizationrole", "change_organizationrole", "view_positionfunction")
        self.client.force_login(self.actor)
        permission = Permission.objects.get(content_type__app_label="organization", codename="view_positionfunction")
        r = self.client.post(reverse("organization:role_list"), {
            "action": "create", "name": "Nueva consulta", "description": "Sin superusuario",
            "delegations": [self.delegation.pk], "permissions": [permission.pk],
        })
        self.assertEqual(r.status_code, 302, r.context["form"].errors if r.status_code == 200 else "")
        created = Group.objects.get(name="Nueva consulta")
        self.assertFalse(self.actor.is_superuser)
        self.assertEqual(list(created.permissions.values_list("pk", flat=True)), [permission.pk])

    def test_admin_normal_puede_otorgar_cualquier_permiso_del_catalogo(self):
        self.grant("view_organizationrole", "add_organizationrole")
        self.client.force_login(self.actor)
        permission = Permission.objects.get(content_type__app_label="organization", codename="delete_employee")
        r = self.client.post(reverse("organization:role_list"), {
            "action": "create", "name": "Intento de escalamiento", "description": "Prueba",
            "delegations": [self.delegation.pk], "permissions": [permission.pk],
        })
        self.assertEqual(r.status_code, 302)
        created = Group.objects.get(name="Intento de escalamiento")
        self.assertTrue(created.permissions.filter(pk=permission.pk).exists())

    def test_role_ajeno_no_visible_ni_editable(self):
        foreign = Group.objects.create(name="Rol de otra delegación")
        foreign_role = OrganizationRole.objects.create(group=foreign, delegation=self.foreign_delegation)
        foreign_role.application_delegations.add(self.foreign_delegation)
        self.grant("view_organizationrole", "change_organizationrole")
        self.client.force_login(self.actor)
        r = self.client.get(reverse("organization:role_list"))
        self.assertNotContains(r, "Rol de otra delegación")
        r2 = self.client.get(reverse("organization:role_list"), {"modal": "edit", "id": foreign.pk})
        self.assertEqual(r2.status_code, 404)

    def test_etiqueta_permiso_espanol_no_cambia_codename(self):
        permission = Permission.objects.get(content_type__app_label="organization", codename="view_delegationresponsibilitylog")
        before = (permission.codename, permission.name)
        self.assertIn("Historial de responsables de delegación", permission_label(permission))
        self.assertIn("Puede consultar", permission_label(permission))
        self.assertEqual((permission.codename, permission.name), before)
        field = OrganizationRoleForm().fields["permissions"]
        self.assertIn("Organización", field.label_from_instance(permission))

    def test_usuario_solo_lectura_no_puede_modificar_cuentas(self):
        self.grant("view_userprofile")
        self.client.force_login(self.actor)
        r = self.client.get(reverse("organization:user_list"))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "Crear usuario")
        r2 = self.client.get(reverse("organization:user_list"), {"modal": "create"})
        self.assertEqual(r2.status_code, 403)

    def test_administrador_normal_gestiona_usuarios_sin_superusuario(self):
        self.grant("view_userprofile", "add_userprofile", "view_organizationrole")
        self.client.force_login(self.actor)
        r = self.client.get(reverse("organization:user_list"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Crear usuario")
        r = self.client.get(reverse("organization:user_list"), {"modal": "create"})
        self.assertEqual(r.status_code, 200)
        role_option = Group.objects.create(name="Solo consulta")
        role = OrganizationRole.objects.create(group=role_option, delegation=self.delegation)
        role.application_delegations.add(self.delegation)
        r = self.client.post(reverse("organization:user_list"), {
            "action": "create", "username": "nuevo_lector", "first_name": "Nuevo",
            "last_name": "Lector", "email": "nuevolector@example.com",
            "employee_code": "NEW-LECTOR-001",
            "authorized_delegations": [self.delegation.pk], "groups": [role_option.pk],
            "password1": "Clave-Segura-9271!", "password2": "Clave-Segura-9271!",
        })
        self.assertEqual(r.status_code, 302, r.context["form"].errors if r.status_code == 200 else "")
        user = get_user_model().objects.get(username="nuevo_lector")
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.profile.delegation_id, self.delegation.pk)

    def test_no_concede_delegaciones_ajenas_al_crear_usuarios(self):
        self.grant("view_userprofile", "add_userprofile")
        self.client.force_login(self.actor)
        role_option = Group.objects.create(name="Consulta ajena")
        role = OrganizationRole.objects.create(group=role_option, delegation=self.foreign_delegation)
        role.application_delegations.add(self.foreign_delegation)
        r = self.client.post(reverse("organization:user_list"), {
            "action": "create", "username": "usuario_ajeno", "email": "ajeno@example.com",
            "employee_code": "NEW-OTHER-001", "authorized_delegations": [self.foreign_delegation.pk],
            "groups": [role_option.pk], "password1": "Clave-Segura-9271!", "password2": "Clave-Segura-9271!",
        })
        self.assertEqual(r.status_code, 200)
        self.assertIn("authorized_delegations", r.context["form"].errors)
        self.assertFalse(get_user_model().objects.filter(username="usuario_ajeno").exists())
