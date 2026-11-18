"""Pruebas de regresión de catálogo y restricción de permisos sensibles."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase

from .forms import OrganizationRoleForm
from .permission_labels import catalog_permission_queryset, permission_label


class MonitoringRolePermissionsTests(TestCase):
    def test_catalogo_muestra_ajustes_y_configuracion(self):
        permissions = catalog_permission_queryset(
            Permission.objects.filter(content_type__app_label="monitoring_traceability")
        ).select_related("content_type")
        visible = {p.codename for p in permissions}
        self.assertIn("view_indicator", visible)
        self.assertIn("change_indicator", visible)
        self.assertIn("change_monitoringsettings", visible)
        sensitive = {
            p.codename: permission_label(p)
            for p in permissions
            if p.codename in ("change_indicator", "change_monitoringsettings")
        }
        self.assertEqual(sensitive["change_indicator"], "Puede ajustar indicadores")
        self.assertEqual(
            sensitive["change_monitoringsettings"],
            "Puede configurar alertas y ajustes de Monitoreo",
        )

    def test_administrador_limitado_no_puede_asignar_permisos_especiales(self):
        manager = get_user_model().objects.create_user(username="admin_limitado_permisos_monitor", password="demo-123-pass")
        form = OrganizationRoleForm(actor=manager)
        shown = {p.codename for p in form.fields["permissions"].queryset}
        self.assertNotIn("change_indicator", shown)
        self.assertNotIn("change_monitoringsettings", shown)

        restricted = Permission.objects.get(
            content_type__app_label="monitoring_traceability",
            codename="change_monitoringsettings",
        )
        forged = OrganizationRoleForm(
            actor=manager,
            data={
                "name": "Rol de ataque de prueba",
                "description": "Intento de permiso no autorizado",
                "permissions": [str(restricted.pk)],
            },
        )
        self.assertFalse(forged.is_valid())
        self.assertIn("permissions", forged.errors)

    def test_administrador_autorizado_si_puede_seleccionarlos(self):
        manager = get_user_model().objects.create_user(username="admin_monitor_autorizado", password="demo-123-pass")
        perms = Permission.objects.filter(
            content_type__app_label="monitoring_traceability",
            codename__in=("change_indicator", "change_monitoringsettings"),
        )
        manager.user_permissions.add(*perms)
        manager = get_user_model().objects.get(pk=manager.pk)
        form = OrganizationRoleForm(actor=manager)
        shown = {p.codename for p in form.fields["permissions"].queryset}
        self.assertIn("change_indicator", shown)
        self.assertIn("change_monitoringsettings", shown)
