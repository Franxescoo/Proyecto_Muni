"""Datos ficticios para exhibir el SGR. No se ejecuta sin --aplicar.

Instalar en organization/management/commands y ejecutar en el servidor que
utiliza la BD de demostración. No altera ni borra registros ajenos al prefijo DEMO.
"""
import calendar
import secrets
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import UserProfile
from organization.models import Delegation, Employee, OrganizationRole, PositionFunction
from planning_measurements.models import Goal, MeasurementItem, Period
from registration_validation.models import Activity, ActivityType, AttentionEntry, AttentionType, SubAttention

PREFIX = "DEMO SGR - "
APP_LABELS = (
    "organization", "accounts", "planning_measurements",
    "registration_validation", "monitoring_traceability",
)

# Los nombres de estos seis actores proceden de la sección 3 de la guía SGR.
ROLES = (
    ("Administrador", "Configura usuarios, roles, catálogos y planificación.", "admin", "central"),
    ("Coordinador del sistema", "Supervisa la operación de todas las delegaciones.", "coord", "central"),
    ("Delegado o jefatura", "Supervisa su delegación y sus compromisos.", "delegado", "norte"),
    ("Funcionario", "Registra actividades y atenciones de su delegación.", "funcionario", "norte"),
    ("Verificador", "Revisa y valida evidencias de su delegación.", "verificador", "central"),
    ("Usuario de consulta", "Consulta indicadores e informes sin modificar.", "consulta", "sur"),
)

# Matriz de referencia para demostración, no matriz oficial aprobada por la Municipalidad.
VIEW_COORDINATOR = {
    "organization.view_delegation", "organization.view_employee",
    "organization.view_positionfunction", "planning_measurements.view_measurementitem",
    "planning_measurements.view_period", "planning_measurements.view_goal",
    "registration_validation.view_activity", "registration_validation.view_activitytype",
    "registration_validation.view_attentiontype", "registration_validation.view_subattention",
    "registration_validation.view_attentionentry", "registration_validation.view_evidence",
    "registration_validation.view_validation", "monitoring_traceability.view_indicator",
    "monitoring_traceability.view_commitment",
}
SCOPED_ROLE_PERMS = {
    "coord": VIEW_COORDINATOR | {
        "planning_measurements.add_goal", "planning_measurements.change_goal",
        "planning_measurements.add_period", "planning_measurements.change_period",
        "monitoring_traceability.add_commitment", "monitoring_traceability.change_commitment",
    },
    "delegado": VIEW_COORDINATOR | {
        "monitoring_traceability.add_commitment", "monitoring_traceability.change_commitment",
    },
    "funcionario": {
        "organization.view_delegation", "organization.view_employee",
        "organization.view_positionfunction", "planning_measurements.view_measurementitem",
        "planning_measurements.view_period", "planning_measurements.view_goal",
        "registration_validation.view_activity", "registration_validation.add_activity",
        "registration_validation.change_activity", "registration_validation.view_activitytype",
        "registration_validation.view_attentiontype", "registration_validation.view_subattention",
        "registration_validation.view_attentionentry", "registration_validation.add_attentionentry",
        "registration_validation.view_evidence", "registration_validation.add_evidence",
        "monitoring_traceability.view_indicator", "monitoring_traceability.view_commitment",
    },
    "verificador": {
        "organization.view_delegation", "organization.view_employee",
        "planning_measurements.view_goal", "registration_validation.view_activity",
        "registration_validation.view_evidence", "registration_validation.view_validation",
        "registration_validation.add_validation", "registration_validation.change_validation",
        "monitoring_traceability.view_indicator",
    },
    "consulta": {
        "organization.view_delegation", "organization.view_positionfunction",
        "planning_measurements.view_measurementitem", "planning_measurements.view_period",
        "planning_measurements.view_goal", "monitoring_traceability.view_indicator",
        "monitoring_traceability.view_commitment",
    },
}

DELEGATIONS = (
    ("central", "DEMOSGR-D01", "Delegación Demo Centro", "La Serena", "Urbano"),
    ("norte", "DEMOSGR-D02", "Delegación Demo Norte", "La Serena", "Urbano"),
    ("sur", "DEMOSGR-D03", "Delegación Demo Sur", "La Serena", "Rural"),
)

class Command(BaseCommand):
    help = "Carga datos ficticios SGR de forma explícita, segura y sin superusuarios."

    def add_arguments(self, parser):
        parser.add_argument(
            "--aplicar", action="store_true", help="Confirmar inserción en la BD configurada."
        )

    def handle(self, *args, **options):
        from django.conf import settings
        alias = "default"
        engine = settings.DATABASES[alias]["ENGINE"].split(".")[-1]
        name = str(settings.DATABASES[alias]["NAME"])
        self.stdout.write(f"Base configurada: motor={engine}, nombre={name}")
        self.stdout.write("Se usarán SOLO datos ficticios con prefijo DEMO/DEMOSGR.")
        self.stdout.write("Se crearán 3 delegaciones, 3 cargos, 6 empleados, 6 roles,")
        self.stdout.write("6 cuentas, 5 ítems, 3 tipos de atención, 6 subatenciones,")
        self.stdout.write("6 atenciones y un período con metas y actividades de demostración.")
        if not options["aplicar"]:
            self.stdout.write(self.style.WARNING(
                "SIMULACIÓN. No se modificó nada. Ejecuta con --aplicar únicamente tras hacer respaldo."
            ))
            return

        demo_names = [PREFIX + name for name, *_ in ROLES]
        usernames = ["demo_sgr_" + slug for _name, _desc, slug, _dep in ROLES]
        existing_roles = set(Group.objects.filter(name__in=demo_names).values_list("name", flat=True))
        existing_users = set(get_user_model().objects.filter(username__in=usernames).values_list("username", flat=True))
        if existing_roles or existing_users:
            # Nunca reemplazar contraseñas, relaciones o permisos existentes.
            if len(existing_roles) == len(demo_names) and len(existing_users) == len(usernames):
                self.stdout.write(self.style.WARNING(
                    "Los seis roles y usuarios DEMO ya existen. No se alteraron datos ni contraseñas."
                ))
                return
            raise CommandError(
                "Hay registros DEMO parciales o nombres ocupados. "
                "No se sobrescribió nada. Revísalos antes de reintentar."
            )

        if Delegation.objects.filter(code__in=[d[1] for d in DELEGATIONS]).exists():
            raise CommandError("Ya hay delegaciones DEMO: no se modificó nada.")
        if PositionFunction.objects.filter(position_name__startswith=PREFIX).exists():
            raise CommandError("Ya hay cargos DEMO: no se modificó nada.")
        if MeasurementItem.objects.filter(code__startswith="DEMOSGR-").exists():
            raise CommandError("Ya hay ítems DEMO: no se modificó nada.")
        if AttentionType.objects.filter(code__startswith="DEMOSGR-").exists():
            raise CommandError("Ya hay tipos de atención DEMO: no se modificó nada.")

        with transaction.atomic():
            delegations = {}
            for slug, code, title, commune, scope in DELEGATIONS:
                delegations[slug] = Delegation.objects.create(
                    code=code, name=title, address="Dirección ficticia de demostración",
                    commune=commune, scope=scope, status="Active",
                )

            today = timezone.localdate()
            positions = {}
            for slug, title in (
                ("gestion", "Gestión y coordinación"),
                ("territorio", "Atención territorial"),
                ("revision", "Revisión y validación"),
            ):
                positions[slug] = PositionFunction.objects.create(
                    position_name=PREFIX + title,
                    measurable_items="Ítems de demostración SGR",
                    services="Atención y seguimiento (datos ficticios)",
                    weightings="Definidas para la demostración",
                    validity_start=date(today.year - 1, 1, 1),
                    validity_end=date(today.year + 1, 12, 31),
                )

            # Solo permisos de aplicaciones del proyecto. No usar is_superuser ni is_staff.
            available = {
                f"{p.content_type.app_label}.{p.codename}": p
                for p in Permission.objects.select_related("content_type").filter(
                    content_type__app_label__in=APP_LABELS
                )
            }
            # No entregar un permiso excepcional a TODOS por pertenecer a un rol.
            exceptional = "planning_measurements.delete_closed_period"
            admin_permissions = {
                key for key in available if key != exceptional
                # Los historiales de auditoría son solo consulta.
                and not (key.startswith("organization.add_delegationresponsibilitylog")
                         or key.startswith("organization.change_delegationresponsibilitylog")
                         or key.startswith("organization.delete_delegationresponsibilitylog")
                         or key.startswith("monitoring_traceability.add_audit")
                         or key.startswith("monitoring_traceability.change_audit")
                         or key.startswith("monitoring_traceability.delete_audit"))
            }
            required = set().union(*SCOPED_ROLE_PERMS.values())
            missing = required - available.keys()
            if missing:
                raise CommandError("Faltan permisos esperados tras migrar: " + ", ".join(sorted(missing)))

            accounts = {}
            employees = {}
            one_time_passwords = {}
            User = get_user_model()
            for display_name, description, slug, home in ROLES:
                group = Group.objects.create(name=PREFIX + display_name)
                wanted = admin_permissions if slug == "admin" else SCOPED_ROLE_PERMS[slug]
                group.permissions.set([available[key] for key in wanted])
                scopes = list(delegations.values()) if slug in ("admin", "coord") else [delegations[home]]
                org_role = OrganizationRole.objects.create(
                    group=group,
                    delegation=delegations[home],
                    description="Rol de demostración según el actor SGR: " + description,
                )
                org_role.application_delegations.set(scopes)
                position = (
                    positions["gestion"] if slug in ("admin", "coord")
                    else positions["revision"] if slug == "verificador"
                    else positions["territorio"]
                )
                employee = Employee.objects.create(
                    name="Persona ficticia - " + display_name,
                    delegation=delegations[home], position=position,
                    roles=display_name, status="Active",
                )
                employee.assigned_groups.add(group)
                employees[slug] = employee
                username = "demo_sgr_" + slug
                password = secrets.token_urlsafe(18)
                account = User(username=username, email=f"{username}@example.invalid")
                account.is_active = True
                account.is_staff = False
                account.is_superuser = False
                account.set_password(password)
                account.save()
                account.groups.add(group)
                if slug == "admin" and exceptional in available:
                    # Permiso individual, como exige la regla del proyecto.
                    account.user_permissions.add(available[exceptional])
                profile = UserProfile.objects.create(
                    user=account, employee_code="DEMOSGR-" + slug.upper(),
                    delegation=delegations[home], employee=employee,
                )
                profile.authorized_delegations.set(scopes)
                accounts[slug] = account
                one_time_passwords[username] = password

            # La jefatura demo es responsable de la delegación Norte.
            delegations["norte"].responsible = employees["delegado"]
            delegations["norte"].save(update_fields=["responsible"])

            items = []
            for code, name, unit, kind in (
                ("DEMOSGR-I01", "Atenciones registradas", "atenciones", "quantitative"),
                ("DEMOSGR-I02", "Solicitudes atendidas", "solicitudes", "quantitative"),
                ("DEMOSGR-I03", "Visitas territoriales", "visitas", "quantitative"),
                ("DEMOSGR-I04", "Actividades ejecutadas", "actividades", "quantitative"),
                ("DEMOSGR-I05", "Cumplimiento de compromisos", "%", "percentage"),
            ):
                item = MeasurementItem(
                    code=code, name=name, description="Ítem ficticio para evaluación académica",
                    item_type=kind, unit=unit,
                    formula="(compromisos cumplidos / compromisos registrados) × 100"
                    if kind == "percentage" else "",
                )
                item.full_clean()
                item.save()
                items.append(item)
            positions["gestion"].catalog_items.add(items[0], items[3], items[4])
            positions["territorio"].catalog_items.add(items[0], items[1], items[2])
            positions["revision"].catalog_items.add(items[3], items[4])

            attention_pairs = []
            for number, (kind, sub_names) in enumerate((
                ("Información y orientación", ("Consulta general", "Orientación de trámites")),
                ("Atención comunitaria", ("Solicitud territorial", "Seguimiento comunitario")),
                ("Apoyo y servicios", ("Información de servicios", "Derivación interna")),
            ), start=1):
                attention_type = AttentionType.objects.create(
                    code=f"DEMOSGR-T{number:02}", name=kind,
                    description="Categoría de demostración académica", status=True,
                )
                for part, sub_name in enumerate(sub_names, start=1):
                    sub = SubAttention.objects.create(
                        code=f"DEMOSGR-S{number:02}{part}", name=sub_name,
                        attention_type=attention_type, status=True,
                    )
                    attention_pairs.append((attention_type, sub))

            for index, (slug, _name, _desc, _commune, _scope) in enumerate(DELEGATIONS):
                primary = {"central": "coord", "norte": "funcionario", "sur": "consulta"}[slug]
                # Dos atenciones ficticias por delegación.
                for ix in (0, 1):
                    att_type, sub = attention_pairs[(index * 2 + ix) % len(attention_pairs)]
                    obj = AttentionEntry(
                        requester=f"Persona ficticia {index + 1}-{ix + 1}",
                        attention_type=att_type, sub_attention=sub,
                        description="Consulta ficticia para demostrar el registro de atención.",
                        delegation=delegations[slug],
                        responsible_employee=employees[primary],
                        registered_by=accounts[primary],
                    )
                    obj.full_clean()
                    obj.save()

            # Período y registros mínimos de planificación para una demostración.
            _, days = calendar.monthrange(today.year, today.month)
            begin = date(today.year, today.month, 1)
            finish = date(today.year, today.month, days)
            import holidays
            chilean_holidays = holidays.country_holidays("CL", years=[today.year])
            computable = sum(
                1 for day in range(1, days + 1)
                if (d := date(today.year, today.month, day)).weekday() < 5
                and d not in chilean_holidays
            )
            period = Period(
                start_date=begin, end_date=finish, computable_days=computable,
                status="Active", thresholds="Parámetros de demostración sin validación institucional",
                parameters_version=f"demo-{today.year}",
            )
            period.full_clean()
            period.save()
            demo_activity_type = ActivityType.objects.create(
                code="DEMOSGR-A01", name="Actividad de atención de prueba",
                description="Clasificación ficticia de una actividad", status=True,
            )
            for i, (slug, _desc, _home) in enumerate(
                [(r[2], r[1], r[3]) for r in ROLES if r[2] in ("funcionario", "coord", "delegado")]
            ):
                employee = employees[slug]
                item = items[i]
                goal = Goal(
                    period=period, employee=employee, position=employee.position,
                    measurement_item=item, item=item.name,
                    objective_value=Decimal("20.00"), required_evidence_count=2,
                    unit=item.unit, weight=Decimal("100.00"),
                )
                goal.full_clean()
                goal.save()
                activity = Activity(
                    goal=goal, author=employee, activity_type=demo_activity_type,
                    date=today, request_problem="Solicitud ficticia de demostración",
                    action="Atención y registro de prueba", contact="Persona ficticia",
                    phone="000000000", status="Completed",
                )
                activity.full_clean()
                activity.save()

        self.stdout.write(self.style.SUCCESS("Carga DEMO realizada correctamente. Sin superusuarios."))
        self.stdout.write("CREDENCIALES TEMPORALES (se muestran solo en esta ejecución):")
        for username, password in one_time_passwords.items():
            self.stdout.write(f"  {username} : {password}")
        self.stdout.write(self.style.WARNING(
            "Guarda las credenciales en lugar seguro y cámbialas/desactívalas tras la evaluación. "
            "No copies estas contraseñas al repositorio ni a capturas públicas."
        ))
